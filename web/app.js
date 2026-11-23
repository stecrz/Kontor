/* Kontor -- Oberflaeche. Keine Fremdbibliotheken, alles laeuft gegen /api/ auf demselben Rechner. */
'use strict';

// ---------------------------------------------------------------- Sprache (alle Texte in web/i18n.js: Schluessel -> [Deutsch, Englisch])
// what this device keeps for Kontor (theme, language, views, the panel): read and written only here -- the demo (DEMO_PAGE) reads it
// but keeps what it writes in the page's memory, so nothing of it stays on the device
const LS = {demo: null,
  get: k => LS.demo && LS.demo.has(k) ? LS.demo.get(k) : localStorage.getItem(k),
  set: (k, v) => LS.demo ? LS.demo.set(k, String(v)) : localStorage.setItem(k, v),
  del: k => LS.demo ? LS.demo.set(k, null) : localStorage.removeItem(k)};
const LANGS = [['de', 'Deutsch'], ['en', 'English']];      // Auswahl überall als Liste (weitere Sprachen: hier und in i18n.js ergänzen)
const langOk = l => LANGS.some(([v]) => v === l) ? l : 'de';
let LANG = 'de';
try { LANG = langOk(LS.get('kontor.lang')); } catch (e) {}
const langOpts = () => LANGS.map(([v, n]) => `<option value="${v}" ${LANG === v ? 'selected' : ''}>${n}</option>`).join('');
function t(k, ...a) {
  const e = I18N[k], s = e ? (LANG === 'en' && e[1] != null ? e[1] : e[0]) : k;
  return a.length ? s.replace(/\{(\d+)\}/g, (m, i) => String(a[+i])) : s;
}
function setLang(l, pending) {
  // Sprache wechseln: merken und Oberflaeche neu laden (alle Texte, Formate und Monatsnamen einheitlich)
  l = langOk(l);
  try { LS.set('kontor.lang', l); if (pending) LS.set('kontor.lang.pending', '1'); } catch (e) {}
  if (l !== LANG) location.reload();
}
// Kontor's own Mac app (mac_app.swift) around this page: it has no words of its own -- its menu's come from here (sent once
// the texts are there, below) -- and its window follows the theme
const SHELL = (() => { try { return !!window.webkit.messageHandlers.kontor; } catch (e) { return false; } })();
function shellPost(m) {
  if (!SHELL) return Promise.resolve(null);
  try { return Promise.resolve(window.webkit.messageHandlers.kontor.postMessage(m)).catch(() => null); } catch (e) { return Promise.resolve(null); }
}
const SHELL_MENU = {about: 'mac_m_ueber', settings: 'mac_m_einstellungen', hide: 'mac_m_ausblenden', hideOthers: 'mac_m_andere', showAll: 'mac_m_alle',
  quit: 'mac_m_beenden', file: 'mac_m_ablage', close: 'mac_m_schliessen', print: 'mac_m_drucken', edit: 'bearbeiten', undo: 'mac_m_widerrufen',
  redo: 'mac_m_wiederholen', cut: 'mac_m_ausschneiden', copy: 'kopieren', paste: 'mac_m_einsetzen', selectAll: 'mac_m_alles', view: 'mac_m_darstellung',
  reload: 'mac_m_neu_laden', actualSize: 'mac_m_original', zoomIn: 'mac_m_groesser', zoomOut: 'mac_m_kleiner', fullScreen: 'mac_m_vollbild', window: 'mac_m_fenster',
  minimize: 'mac_m_dock', zoom: 'mac_m_zoomen', help: 'hilfe', kontorHelp: 'mac_m_kontor_hilfe', ok: 'mac_ok', cancel: 'abbrechen', find: 'mac_m_suchen_menu'};
shellPost({labels: Object.fromEntries(Object.entries(SHELL_MENU).map(([k, v]) => [k, t(v)]))});
// its window has no title bar of its own: the page as in the browser, the window buttons small in the top left corner (above
// Kontor's name), and the strip at the top moves the window -- the app says how high it is and where the buttons are (tb, tl,
// ly, lb: right end, middle, bottom; this page's px, 0 in full screen), the page tells it where it has something to click in
// that strip (those spots stay clicks)
const CHROME = {tb: 0, tl: 0, ly: 0, lb: 0, sent: ''};
const CHROME_CLICK = 'button, a[href], input, select, textarea, label, summary, [role=button], [tabindex]:not([tabindex="-1"]), .seg, .hq';
function chromeApply(c) {
  if (!c || typeof c !== 'object') return;
  for (const k of ['tb', 'tl', 'ly', 'lb']) { CHROME[k] = Math.max(0, +c[k] || 0); document.documentElement.style.setProperty('--' + k, CHROME[k] + 'px'); }
  document.body.classList.toggle('mac-chrome', CHROME.tb > 0);
  chromeHoles();
}
function chromeHoles() {
  const holes = [];
  if (CHROME.tb > 0) for (const box of document.querySelectorAll('.topbar, .side, #assist.open .as-head, #drawer.open, .ctx')) for (const el of box.querySelectorAll(CHROME_CLICK + ', .brand')) {
    const r = el.getBoundingClientRect();
    if (r.width && r.height && r.top < CHROME.tb && r.bottom > 0 && r.right > 0 && r.left < innerWidth) holes.push([r.left, r.top, r.width, r.height].map(v => Math.round(v)));
  }
  const s = JSON.stringify(holes);
  if (s !== CHROME.sent) { CHROME.sent = s; shellPost({drag: holes}); }
}
if (SHELL) {
  let frame = 0;
  const later = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; chromeHoles(); }); };
  new MutationObserver(later).observe(document.body, {subtree: true, childList: true, attributes: true, attributeFilter: ['class', 'hidden', 'style']});
  addEventListener('resize', later); addEventListener('transitionend', later);
  addEventListener('kontorchrome', e => chromeApply(e.detail));
  shellPost({chrome: 1}).then(chromeApply);
}
// pages not fully tested yet: usable, but marked "Alpha" in the menu and next to the page title
const ALPHA_TABS = new Set(['planning', 'properties', 'tax', 'transactions']);
const alphaTag = (cls = 'alpha-tag') => `<em class="${cls}" title="${t('alpha_tip')}">${t('alpha')}</em>`;
// appearance, per device: dark (the default), light, or like the system
const themeGet = () => { try { return ['light', 'auto'].includes(LS.get('kontor.theme')) ? LS.get('kontor.theme') : 'dark'; } catch (e) { return 'dark'; } };
function applyTheme(v) {
  const sys = window.matchMedia ? matchMedia('(prefers-color-scheme: dark)') : null;
  const dark = v === 'light' ? false : v === 'auto' ? !!(sys && sys.matches) : true;
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  const m = document.querySelector('meta[name="theme-color"]'); if (m) m.content = dark ? '#000000' : '#f5f5f7';
  shellPost({theme: ['light', 'auto'].includes(v) ? v : 'dark'});          // the setting: "auto" lets the Mac app's window follow macOS
}
applyTheme(themeGet());
try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (themeGet() === 'auto') { applyTheme('auto'); if (S.csrf) route(); } }); } catch (e) {}
function applyStatic() {
  document.documentElement.lang = LANG;
  $$('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  $$('#nav a').forEach(a => { if (ALPHA_TABS.has(a.getAttribute('href').slice(1)) && !a.querySelector('.alpha-tag')) { a.classList.add('alpha'); a.querySelector('span').insertAdjacentHTML('afterend', alphaTag()); } });
  $$('[data-i18n-ph]').forEach(el => { el.placeholder = t(el.dataset.i18nPh); });
  $$('[data-i18n-aria]').forEach(el => el.setAttribute('aria-label', t(el.dataset.i18nAria)));
  const ls = $('#lang-sel'); if (ls) ls.innerHTML = langOpts();
}
async function syncLang() {
  // nach der Anmeldung: Auswahl auf der Anmeldeseite an den Dienst geben, sonst die gespeicherte Sprache uebernehmen
  let pending = false; try { pending = LS.get('kontor.lang.pending') === '1'; LS.del('kontor.lang.pending'); } catch (e) {}
  const cfg = ((S.CFG || {}).ui || {}).language || 'de';
  if (pending && cfg !== LANG && !OFFLINE.mode) { try { const r = await api('/api/language', {language: LANG}); S.CFG.ui = Object.assign(S.CFG.ui || {}, {language: r.language}); } catch (e) {} return; }
  if (cfg !== LANG) setLang(cfg);
}
function tn(k, n, ...a) { const f = t(k, n, ...a).split('|'); return f.length > 1 ? f[n === 1 ? 0 : 1] : f[0]; }   // Einzahl|Mehrzahl


// ---------------------------------------------------------------- Grundlagen
const LOCALE = LANG === 'en' ? 'en-GB' : 'de-DE';
const fmt = new Intl.NumberFormat(LOCALE, {minimumFractionDigits: 2, maximumFractionDigits: 2});
const fmt0 = new Intl.NumberFormat(LOCALE, {maximumFractionDigits: 0});
const F = v => (v == null || isNaN(v) ? '–' : fmt.format(v));
const F0 = v => (v == null || isNaN(v) ? '–' : fmt0.format(v));
const FN = (v, d = 2) => (v == null || isNaN(v) ? '–' : (+v).toLocaleString(LOCALE, {minimumFractionDigits: d, maximumFractionDigits: d}));
// a path of categories or accounts as shown: "Wohnen › Strom/Gas" (a slash may be part of a name; the key keeps " / ")
const CP = p => String(p || '').split(' / ').join(' › ');
const DEC = (fmt.formatToParts(1.5).find(p => p.type === 'decimal') || {value: ','}).value, GRP = (fmt.formatToParts(12345).find(p => p.type === 'group') || {value: '.'}).value;
// a figure in a table: its cents small beside the euros -- there when you look for them, otherwise out of the way
const FC = v => { const s = F(v), i = s.lastIndexOf(DEC); return i < 0 ? s : `${s.slice(0, i)}<small class="ct">${s.slice(i)}</small>`; };
// what you typed, as a number -- in the notation of the language (1.234,56 or 1,234.56). null: nothing typed; NaN: no number.
// The sign that groups thousands is one only before exactly three digits; where it cannot be that ("12.5" in German) it can
// only be the decimal sign. Nothing is read two ways.
const numIn = s => {
  s = String(s == null ? '' : s).replace(/[\s\u00a0\u202f€]/g, ''); if (!s) return null;
  const neg = s[0] === '-'; s = s.replace(/^[+-]/, '');
  const g = GRP.trim() || (DEC === ',' ? '.' : ',');
  let [int, frac, ...more] = s.split(DEC);
  if (more.length || !/^\d*$/.test(frac || '')) return NaN;
  const parts = int.split(g);
  if (parts.length > 1) {
    if (/^[1-9]\d{0,2}$/.test(parts[0]) && parts.slice(1).every(x => /^\d{3}$/.test(x))) int = parts.join('');
    else if (parts.length === 2 && frac == null && /^\d+$/.test(parts[0]) && /^\d+$/.test(parts[1])) [int, frac] = parts;
    else return NaN;
  }
  if (!/^\d*$/.test(int) || (!int && !frac)) return NaN;
  const v = Number((int || '0') + (frac ? '.' + frac : ''));
  return isFinite(v) ? (neg ? -v : v) : NaN;
};
// amounts on axes: short where space is tight (T / M, English k / M), long on wide charts (Tsd. / Mio.);
// ref = largest tick of the axis, so that all ticks share one unit (5T, 10T, 15T instead of 5.000, 10T, 15T)
const Fk = (v, long, ref = v) => {
  if (v == null || isNaN(v)) return '–';
  if (Math.abs(v) < 1e-9) return '0';
  const a = Math.abs(ref), f = (x, d) => x.toLocaleString(LOCALE, {maximumFractionDigits: d}), u = k => t(k + (long ? '_lang' : '_kurz'));
  return a >= 1e9 ? f(v / 1e9, 2) + u('mrd') : a >= 1e6 ? f(v / 1e6, 2) + u('mio') : a >= 1e4 ? f(v / 1e3, a < 1e5 ? 1 : 0) + u('tsd') : F0(v);
};
// short amounts in charts: one decimal at most (12,4M; 10,8T), none from 100T on -- the exact figure is in the tooltip
const Fs = (v, tDec) => { const a = Math.abs(v), f = (x, d) => x.toLocaleString(LOCALE, {maximumFractionDigits: d});
  return a >= 1e9 ? f(v / 1e9, 1) + t('mrd_kurz') : a >= 1e6 ? f(v / 1e6, 1) + t('mio_kurz') : a >= 1e4 ? f(v / 1e3, tDec ?? (a < 1e5 ? 1 : 0)) + t('tsd_kurz') : F0(v); };
// ticks of an axis as [tick, largest tick] (an array of ticks or the arguments of niceTicks)
const textW = (s, px = 11) => { const c = textW.c || (textW.c = document.createElement('canvas').getContext('2d')); c.font = `${px}px ${getComputedStyle(document.body).fontFamily}`; return c.measureText(s).width; };
const axisTicks = (...a) => { const ts = Array.isArray(a[0]) ? a[0] : niceTicks(...a), r = Math.max(...ts.map(Math.abs)); return ts.map(v => [v, r]); };
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const MONATE = LANG === 'en' ? ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'] : ['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'];
const ML = m => MONATE[+m.slice(5) - 1] + ' ' + m.slice(2, 4);
const MLL = m => new Date(+m.slice(0, 4), +m.slice(5) - 1, 1).toLocaleDateString(LOCALE, {month: 'long', year: 'numeric'});          // "November 2025"
const FD = d => (d && d.length >= 10) ? [d.slice(8, 10), d.slice(5, 7), d.slice(0, 4)].join(LANG === 'en' ? '/' : '.') : (d || '');
const FDT = d => FD(d) + (d && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(d) ? t('um_0_uhr', d.slice(11, 16)) : '');      // date, with time if known (changelog headings)
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const ROLE = {cash: [t('pos_bankguthaben'), 'var(--c-liq)'], securities: [t('pos_wertpapiere'), 'var(--c-anl)'], term_investments: [t('pos_gebundene_anlagen'), 'var(--c-fest)'], real_estate: [t('immobilien'), 'var(--c-immo)'],
              participations: [t('beteiligungen'), 'var(--c-bet)'], tangibles: [t('sachwerte'), '#8e8e93'], receivables: [t('pos_forderungen'), 'var(--c-ford)'], other: [t('sonstiges'), '#636366'], liabilities: [t('pos_verbindlichkeiten'), 'var(--c-verb)'],
              contingent: [t('role_eventual'), '#a8a29e'], ignore: [t('nicht_bilanzieren'), '#c7c7cc']};
const ROLE_OPTS = [['cash', t('pos_bankguthaben')], ['securities', t('pos_wertpapiere')], ['term_investments', t('pos_gebundene_anlagen')], ['real_estate', t('immobilien')], ['participations', t('beteiligungen')], ['tangibles', t('sachwerte')], ['receivables', t('pos_forderungen')], ['other', t('sonstiges')], ['liabilities', t('pos_verbindlichkeiten')], ['contingent', t('avale_buergschaften_nicht_im_nettoverm')], ['ignore', t('nicht_bilanzieren')]];
// Hilfetexte (Tooltips). Schluessel werden mit hq('schluessel') eingeblendet.
const H = {
  als_app: t('h_als_app'),
  area: t('ein_bereich_ist_eine_menge'),
  main_area: t('es_gibt_genau_einen_hauptbereich'),
  share: t('dein_anteil_an_dieser_gesellschaft'),
  gruppenwahl: t('eine_gruppe_waehlen_heisst_alle'),
  anzeige: t('nach_aktivitaet_standard_blendet_ein'),
  position_kurz: t('wo_das_konto_in_der'),
  verlauf_kurz: t('woher_die_monatsstaende_kommen_umsaetz'),
  berechtigung: t('wofuer_kontor_liest_ueber_die'),
  position: t('die_bilanzposition_eines_kontos_sie'),
  history_source: t('umsaetze_saldo_am_monatsende_heutiger'),
  zuordnen: t('hier_landen_alle_umsaetze_die'),
  regeln_mm: t('regeln_mm_tip'),
  verlauf_import: t('datei_mit_monats_oder_tagesstaenden'),
  inactive: t('gilt_fuer_konten_mit_anzeige'),
  mmhist: t('sicherheit_die_datei_bleibt_verschlues'),
  depotverlauf: t('moneymoney_stellt_ueber_seine_schnitts'),
  ab_art: t('wird_von_moneymoney_bei_bank'),
  touchid: t('eingeschaltet_die_anmeldung_am_mac'),
  bilanz_tabelle: t('klick_auf_eine_position_klappt'),
  abgleich: t('datenstand_in_zwei_stufen_banken'),
  fern: t('fern_tip'),
  fern_was: t('fern_was_tip'),
  timemachine: t('timemachine_tip'),
  datenschluessel: t('datenschluessel_tip'),
  diagnose: t('diagnose_tip'),
  port: t('port_tip'),
  update_quelle: t('update_quelle_tip'),
  einrichtung_knoepfe: t('einrichtung_knoepfe_tip'),
  position_kat: t('position_kat_tip'),
  cf_operativ: t('cf_operativ_tip'), cf_invest: t('cf_invest_tip'), cf_finanz: t('cf_finanz_tip'), cf_bruecke: t('cf_bruecke_tip'), cf_verm_bruecke: t('cf_verm_bruecke_tip'), cf_je_monat_t: t('cf_je_monat_tip'), cf_herkunft_verwendung: t('cf_herkunft_verwendung_tip'),
  cf_ausgaben_kuchen: t('cf_ausgaben_kuchen_tip'), cf_heatmap: t('cf_heatmap_tip'),
  cf_unklar: t('cf_unklar_tip'), cf_wert: t('cf_wert_tip'), cf_fcf: t('cf_fcf_tip'), cf_bank: t('cf_bank_tip'), cf_umsch: t('cf_umschichtungen_tip'), cf_nv: t('cf_nv_tip'), cf_abgleich_bank: t('cf_abgleich_bank_tip'),
  cf_abgleich_nv: t('cf_abgleich_nv_tip'),
  zielkonto: t('zielkonto_tip'), anl_empfaenger: t('anl_tip'), sicherung: t('sicherung_tip'),
  voll_lesen: t('voll_lesen_tip'),
  sync_knoepfe: t('sync_knoepfe_tip'),
  kz_eingetragen: t('kz_eingetragen_tip'),
  belege_ordner: t('belege_werden_als_normale_dateien'),
  belege_sub: t('platzhalter_jahr_monat_entitaet_bereic'),
  months_back: t('wie_viele_monate_historie_gelesen'),
  bind: t('auf_diesem_mac_ist_die'),
  tls: t('optional_zertifikat_schluessel_pem_fue'),
  updates: t('einzige_netzverbindung_von_kontor_einm'),
  assistent: t('h_assistent'), ki_abschirmung: t('h_ki_abschirmung'), ki_kontext: t('h_ki_kontext'), ki_leerlauf: t('h_ki_leerlauf'),
  ki_eintragen: t('h_ki_eintragen'), ki_eigenes: t('h_ki_eigenes'), ki_diktat: t('h_ki_diktat'), ki_bedeutung: t('h_ki_bedeutung'), ki_sp_start: t('h_ki_sp_start'), ki_mikrofilter: t('h_ki_mikrofilter'), ki_speichern: t('h_ki_speichern'), ki_internet: t('h_ki_internet'), ki_tavily: t('h_ki_tavily'), ki_vertraut: t('h_ki_vertraut'), ki_websites: t('h_ki_websites'),
  ki_gedaechtnis: t('h_ki_gedaechtnis'),
  ki_programm: t('h_ki_programm'), ki_auto_suchen: t('h_ki_auto_suchen'), ki_modelle: t('h_ki_modelle'), ki_ablage: t('h_ki_ablage'),
  darlehen_iban: t('die_rate_wird_am_gegenkonto'),
  darlehen_konto: t('das_manuell_gefuehrte_darlehenskonto_i'),
  darlehen_quelle: t('das_konto_von_dem_die'),
  zinsmodell: t('jahresbasis_zins_satz_stand_am'),
  rate_list: t('zinssaetze_mit_gueltigkeitsbeginn_z_b'),
  base_override: t('erzwingt_die_zinsbasis_fuer_ein'),
  regel_darlehen_h: t('regel_darlehen_h'), regel_gesellschaften_h: t('regel_gesellschaften_h'),
  h_l_name: t('h_l_name'), h_l_aktiv: t('h_l_aktiv'), h_l_art: t('h_l_art'), h_l_text: t('h_l_text'), h_l_excl: t('h_l_excl'), h_l_zinstag: t('h_l_zinstag'),
  h_l_ab: t('h_l_ab'), h_l_gp: t('h_l_gp'), h_l_kt: t('h_l_kt'), h_l_kz: t('h_l_kz'),
  h_co_anteil: t('h_co_anteil'), h_co_bet: t('h_co_bet'), h_co_gk: t('h_co_gk'), h_co_rueck: t('h_co_rueck'), h_co_takt: t('h_co_takt'), h_gk_rueck: t('h_gk_rueck'), h_co_schwelle: t('h_co_schwelle'), h_co_gp: t('h_co_gp'),
  method: t('12_6_monate_durchschnitt_der'), plan_modell: t('h_plan_modell'),
  inflation: t('ausgaben_steigen_standardmaessig_mit_d'),
  steig_ein: t('jaehrliche_steigerung_der_einnahmen_z'),
  rendite: t('jaehrliche_wertentwicklung_fuer_wertpa'),
  event: t('einmalige_oder_wiederkehrende_planerei'),
  wert_bereich: t('beteiligungskonto_an_das_nettovermoege'),
  immo_uebergang: t('erster_monat_mit_nutzen_und'),
  immo_nk: t('grunderwerbsteuer_notar_nur_kaufvertra'),
  immo_geb: t('anteil_des_gebaeudes_am_kaufpreis'),
  immo_afa: t('afa_satz_p_a_2'),
  immo_index: t('indexmiete_erhoehung_zum_jahresbeginn'),
  immo_kosten: t('nicht_umlagefaehige_kosten_p_a'),
  immo_ruecklage: t('ruecklage_fuer_sonderumlagen_instandha'),
  immo_darlehen_art: t('annuitaet_feste_monatsrate_zins_tilgun'),
  immo_abrechnung: t('monatlich_zins_auf_den_laufenden'),
  immo_sonder: t('laufende_sondertilgung_je_monat_ab'),
  immo_zinsbindung: t('nach_ende_der_zinsbindung_gilt'),
  immo_faellig: t('endfaellige_darlehen_bei_faelligkeit_z'),
  immo_abziehbar: t('zinsen_nicht_abziehbarer_darlehen_z'),
  immo_ges: t('gesellschafter_mit_gewinnanteil_und_pe'),
  immo_aussch: t('bei_positivem_ergebnis_schuettet_die'),
  immo_wert: t('angenommene_wertentwicklung_des_objekt'),
  immo_verkauf: t('optional_verkaufsjahr_fuer_die_irr'),
  immo_planung: t('uebernimmt_miete_kosten_zinsen_tilgung'),
  immo_kategorie: t('vermietungskategorie_des_objekts_in_mo'),
  immo_objektkonto: t('das_offline_konto_das_den'),
  immo_darlehen_konten: t('zuordnung_der_darlehen_der_kalkulation'),
  documents: t('verknuepfungen_zu_dateien_auf_dem'),
  offline: t('als_app_auf_dem_iphone'),
  package: t('einstellungspaket_regeln_bereiche_posi'),
  bch: t('bch_hinweis'),
  geld_unterwegs: t('geld_unterwegs_tip'),
};
const HELP_AT = {als_app: 'app', berechtigung: 'setup', immo_abrechnung: 'properties', immo_abziehbar: 'properties', immo_afa: 'properties', immo_aussch: 'properties', immo_darlehen_art: 'properties', immo_darlehen_konten: 'properties', immo_faellig: 'properties', immo_geb: 'properties', immo_ges: 'properties', immo_index: 'properties', immo_kategorie: 'properties', immo_kosten: 'properties', immo_nk: 'properties', immo_objektkonto: 'properties', immo_ruecklage: 'properties', immo_sonder: 'properties', immo_uebergang: 'properties', immo_verkauf: 'properties', immo_wert: 'properties', immo_zinsbindung: 'properties',
  area: 'areas', main_area: 'areas', share: 'areas', gruppenwahl: 'areas', anzeige: 'accounts', position_kurz: 'accounts', position: 'accounts',
  inactive: 'accounts', verlauf_kurz: 'history', history_source: 'history', verlauf_import: 'history', depotverlauf: 'history', mmhist: 'balances',
  zuordnen: 'categories', regeln_mm: 'categories-rules', kz_eingetragen: 'categories-write-back', position_kat: 'categories-positions', zielkonto: 'positions-recipients', anl_empfaenger: 'positions-recipients', sicherung: 'backup',
  cf_operativ: 'cash-flow', cf_invest: 'cash-flow', cf_finanz: 'cash-flow', cf_unklar: 'cash-flow', cf_wert: 'cash-flow',
  cf_bank: 'cash-flow', cf_umsch: 'cash-flow', cf_fcf: 'cash-flow', cf_nv: 'cash-flow', cf_abgleich_bank: 'cash-flow', cf_abgleich_nv: 'cash-flow', cf_bruecke: 'cash-flow-bridge', cf_verm_bruecke: 'cash-flow-wealth', cf_je_monat_t: 'cash-flow-months', cf_herkunft_verwendung: 'cash-flow-total',
  cf_ausgaben_kuchen: 'cash-flow-ring', cf_heatmap: 'cash-flow-heatmap',
  abgleich: 'sync', ab_art: 'sync', voll_lesen: 'sync', sync_knoepfe: 'sync', months_back: 'sync',
  bch: 'balance-sheet-chart', bilanz_tabelle: 'balance-sheet-table', geld_unterwegs: 'balance-sheet-table', regel_darlehen_h: 'rules-loans', regel_gesellschaften_h: 'rules-companies',
  darlehen_iban: 'rules-loans', darlehen_konto: 'rules-loans', darlehen_quelle: 'rules-loans', zinsmodell: 'rules-loans', rate_list: 'rules-loans', base_override: 'rules-loans',
  h_l_name: 'rules-loans', h_l_aktiv: 'rules-loans', h_l_art: 'rules-loans', h_l_text: 'rules-loans', h_l_excl: 'rules-loans', h_l_zinstag: 'rules-loans', h_l_ab: 'rules-loans',
  h_l_gp: 'rules-loans', h_l_kt: 'rules-loans', h_l_kz: 'rules-loans', h_co_anteil: 'areas', h_co_bet: 'rules-companies', h_co_gk: 'rules-mirrors', h_gk_rueck: 'rules-mirrors',
  h_co_rueck: 'rules-back', h_co_takt: 'rules-companies', h_co_schwelle: 'rules-companies', h_co_gp: 'rules-companies', method: 'planning', plan_modell: 'planning', inflation: 'planning', steig_ein: 'planning',
  rendite: 'planning', event: 'planning', wert_bereich: 'planning', fern: 'iphone', fern_was: 'iphone', offline: 'iphone', bind: 'iphone', tls: 'iphone',
  port: 'iphone', touchid: 'security', package: 'backup', timemachine: 'backup', datenschluessel: 'security', diagnose: 'troubleshooting', einrichtung_knoepfe: 'setup', updates: 'updates',
  update_quelle: 'updates', belege_ordner: 'receipts', belege_sub: 'receipts', documents: 'properties', assistent: 'assistant', ki_diktat: 'assistant-dictation', ki_bedeutung: 'assistant-memory', ki_sp_start: 'assistant-dictation', ki_mikrofilter: 'assistant-dictation', ki_abschirmung: 'assistant-safety', ki_kontext: 'assistant-setup', ki_leerlauf: 'assistant-setup', ki_auto_suchen: 'assistant-setup', ki_eintragen: 'assistant-rights', ki_eigenes: 'assistant-setup', ki_speichern: 'assistant', ki_programm: 'assistant-setup', ki_modelle: 'assistant-setup', ki_ablage: 'assistant-setup', ki_internet: 'assistant-internet', ki_tavily: 'assistant-internet', ki_vertraut: 'assistant-internet', ki_websites: 'assistant-internet'};
const more = id => ` <a href="#help/${id}" class="more">${t('mehr_in_der_hilfe')}</a>`;   // Verweis auf einen Abschnitt der Hilfe
// beside a page's title: what the page does in a line, a click opens its part of the help (settings and Konten & Regeln: per tab)
const PAGE_HELP = {overview: 'overview', balance: 'balance-sheet', cashflow: 'cash-flow', planning: 'planning', properties: 'properties', tax: 'tax',
  transactions: 'receipts', categories: 'categories', 'categories/rules': 'categories-rules', 'categories/written': 'categories-write-back', bookings: 'auto-bookings',
  setup: 'setup', accounts: 'accounts', 'accounts/areas': 'areas', 'accounts/history': 'balances', 'accounts/positions': 'categories-positions', 'accounts/rules': 'rules',
  'accounts/tax': 'tax', settings: '', 'settings/moneymoney': 'sync', 'settings/access': 'iphone', 'settings/receipts': 'receipts', 'settings/updates': 'updates',
  'settings/backup': 'backup', 'settings/assistant': 'assistant-setup', assistant: 'assistant', log: 'log'};
// pages with tabs: the title stays, so the line names the tab it is about ("Belege: …")
const SUB_LABEL = {settings: {'': 'allgemein', moneymoney: 'einst_mm', access: 'zugang', receipts: 'belege', assistant: 'ki_assistent_lang', updates: 'updates', backup: 'sichern_zuruecksetzen'},
  accounts: {'': 'mod_accounts', areas: 'mod_areas', history: 'kontostaende_tab', positions: 'cashflow_positionen', rules: 'nav_auto_regeln', tax: 'steuer'},
  categories: {'': 'kz_tab_offen', rules: 'regeln_fuer_moneymoney', written: 'kz_tab_eingetragen'}};
const pageHq = (tab, sub) => { const k = (tab + '/' + sub) in PAGE_HELP ? tab + '/' + sub : tab, id = PAGE_HELP[k]; if (id == null) return '';
  const lab = (SUB_LABEL[tab] || {})[sub || ''], txt = t(`page_${k.replace('/', '_')}`);
  return `<span class="hq page-hq" tabindex="0" data-tip="${esc(lab ? t('tab_zu', t(lab), txt) : txt)}"${id ? ` data-help="${id}"` : ''}>?</span>`; };
const ICON = {
  pencil: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L19 9l-4-4L4 16v4zM14 6l4 4"/></svg>',
  check: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  gear: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></svg>',
  bolt: '<svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><path d="M13.5 2 4 13.5h6.5L9.5 22 20 9.5h-6.6z"/></svg>',
  hand: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V11m0-6.5v-.5a1.5 1.5 0 0 1 3 0V11m0-5.5a1.5 1.5 0 0 1 3 0V12m0-3.5a1.5 1.5 0 0 1 3 0V15a7 7 0 0 1-7 7h-1.2a7 7 0 0 1-5.6-2.8L3.4 15a1.6 1.6 0 0 1 2.4-2.1L8 15"/></svg>',
  expand: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg>',
  pin: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17v5M9 3h6l-1 7 4 4H6l4-4-1-7z"/></svg>',
  reset: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>',
  eye: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
  eyeOff: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3 3.9M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/><path d="M3 3l18 18"/></svg>',
  compose: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/><path d="M17.5 3.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4z"/></svg>',
  history: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 2.6-6.4L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/></svg>',
  trash: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>'};
// In the web app (Safari: "Add to Dock", iPhone: Home Screen) there is no back and forward -- the menu leads everywhere: a page
// replaces the one before in the history, so a two-finger swipe has nothing to go back to. In a browser tab each page stays
// an entry (back works as usual).
const APP_MODE = SHELL || (() => { try { return matchMedia('(display-mode: standalone)').matches || navigator.standalone === true; } catch (e) { return false; } })();
// Kontor as an app of its own: Safari makes it itself ("Add to Dock" on the Mac, "Add to Home Screen" on the iPhone) -- no page
// can do that for it, so the way is shown; Chrome and Edge offer it to the page (beforeinstallprompt), then a button does it
const IS_IOS = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const IS_SAFARI = /safari/i.test(navigator.userAgent) && !/chrome|chromium|crios|fxios|edg|opr|android/i.test(navigator.userAgent);
let INSTALL_PROMPT = null;
window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); INSTALL_PROMPT = e; webappDraw(); });
window.addEventListener('appinstalled', () => { INSTALL_PROMPT = null; webappSeen(); webappDraw(); });
const go = h => { if (APP_MODE) location.replace(h); else location.hash = h; };
document.addEventListener('click', e => {
  if (!APP_MODE || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const a = e.target.closest && e.target.closest('a[href^="#"]'); if (!a || a.target) return;
  e.preventDefault(); if (a.getAttribute('href') !== location.hash) go(a.getAttribute('href'));
});
HELP_AT.ki_gedaechtnis = 'assistant-memory';
const hq = k => H[k] ? `<span class="hq" tabindex="0" data-tip="${esc(H[k])}"${HELP_AT[k] ? ` data-help="${HELP_AT[k]}"` : ''}>?</span>` : '';
document.addEventListener('click', e => {
  // with a mouse a click on "?" opens the matching help section; on touch devices the first tap shows the tip, the second opens the help
  const q = e.target.closest('.hq[data-help]'); if (!q || !matchMedia('(hover: hover)').matches) return;
  e.preventDefault(); e.stopPropagation(); go('#help/' + q.dataset.help);
}, true);
// Tooltip als eigenes Element: unterhalb, wenn oben kein Platz ist; nie ueber den Fensterrand hinaus (for "?" and other .tipped elements)
const TIP = {hide: () => {}};
(function tooltips() {
  let tip = null, cur = null, shownAt = 0, wait = null, next = null;
  const hide = () => { clearTimeout(wait); next = null; if (tip) tip.remove(); tip = null; cur = null; };
  TIP.hide = hide;
  const show = el => {
    hide(); cur = el; shownAt = Date.now();
    tip = document.createElement('div'); tip.className = 'tip'; tip.textContent = el.dataset.tip; document.body.appendChild(tip);
    const r = el.getBoundingClientRect(), w = Math.min(340, window.innerWidth - 16); tip.style.maxWidth = w + 'px';
    const tr = tip.getBoundingClientRect();
    let left = r.left + r.width / 2 - tr.width / 2; left = Math.max(8, Math.min(left, window.innerWidth - tr.width - 8));
    let top = r.top - tr.height - 8; if (top < 8) top = r.bottom + 8;
    if (top + tr.height > window.innerHeight - 8) top = Math.max(8, window.innerHeight - tr.height - 8);
    tip.style.left = left + 'px'; tip.style.top = top + 'px';
  };
  let touch = false;                        // after a tap the browser also sends mouse events; those must not hide the tip again
  document.addEventListener('pointerdown', e => { touch = e.pointerType === 'touch'; }, true);
  // a figure in a table: after a moment (moving over the table does not flash a tip at every cell)
  const later = el => { clearTimeout(wait); next = el; wait = setTimeout(() => { if (next === el && el.isConnected && el.matches(':hover')) show(el); }, 450); };
  document.addEventListener('mouseover', e => { if (touch) return; const el = e.target.closest && e.target.closest('.hq, .tipped'); if (el && el !== cur && el !== next) { if (el.tagName === 'TD') later(el); else show(el); } });
  document.addEventListener('mouseout', e => { if (touch) return; const el = e.target.closest && e.target.closest('.hq, .tipped'); if (el && (el === cur || el === next) && !(e.relatedTarget && el.contains(e.relatedTarget))) hide(); });
  document.addEventListener('focusin', e => { const el = e.target.closest && e.target.closest('.hq, .tipped'); if (el) show(el); });
  document.addEventListener('focusout', e => { if (e.target.closest && e.target.closest('.hq, .tipped')) hide(); });
  document.addEventListener('click', e => {
    const el = e.target.closest && e.target.closest('.hq, .tipped'); if (!el) { hide(); return; }
    e.preventDefault();
    if (cur === el && tip && Date.now() - shownAt > 400) { hide(); if (el.dataset.help) go('#help/' + el.dataset.help); }   // second tap
    else if (cur !== el || !tip) show(el);
  });
  window.addEventListener('scroll', () => { if (tip) hide(); }, true); window.addEventListener('resize', hide);          // (a tip about to show waits: it shows only where the pointer still is)
})();

const DEMO_OFF = new Set(['setup', 'settings', 'log']);          // pages the demo does not have (about this Mac and the real Kontor)
const S = { tab: 'overview', mode: 'months', plan: true, real: false, all: false, collapsed: {}, csrf: null, area: null, cfEbene: 0, planEbene: 2, cfTog: {'s:operating': true},          /* at the start: main lines, income and expenses open (a level clicked: exactly that level) */ cfZeit: '12m', cfVon: null, cfBis: null, cfPieArt: 'aus',
            DATA: null, CFG: null, KONTEN: [], KATS: [], STATUS: null, steuerJahr: null, steuerEnt: null, proposal: false,
            uf: {entity: '', year: '', account: '', q: '', ohne_beleg: false, uncategorized_flag: false, direction: '', kats: null, date_from: '', date_to: '', title: '', est: false, mitOhne: false, katsLabel: '', rChart: false, ids: null, cfRows: null}, sel: new Set() };

function choose(msg, opts) {
  // Rückfrage mit mehreren Antworten (statt confirm): opts = [[wert, text, klasse], ...]; Abbrechen, Escape oder daneben -> null
  return new Promise(res => {
    const bg = document.createElement('div'); bg.className = 'dlg-back';
    bg.innerHTML = `<div class="dlg" role="dialog" aria-modal="true"><div class="dlg-t">${msg}</div><div class="actions">${opts.map(([v, l, c]) => `<button data-v="${esc(v)}" class="${c || ''}">${l}</button>`).join('')}<button data-v="" class="secondary">${t('abbrechen')}</button></div></div>`;
    const key = e => { if (e.key === 'Escape') { e.stopPropagation(); done(''); } };
    const done = v => { bg.remove(); document.removeEventListener('keydown', key, true); res(v || null); };
    bg.addEventListener('click', e => { const b = e.target.closest('button[data-v]'); if (b) done(b.dataset.v); else if (e.target === bg) done(''); });
    document.addEventListener('keydown', key, true);
    document.body.appendChild(bg); const f = bg.querySelector('button'); if (f) f.focus();
  });
}
function askPassword(msg) {
  // Passwort im Dialog abfragen (nicht per prompt(): dort waere es lesbar); Abbrechen -> null
  return new Promise(res => {
    const bg = document.createElement('div'); bg.className = 'dlg-back';
    bg.innerHTML = `<form class="dlg" role="dialog" aria-modal="true"><div class="dlg-t">${msg}</div><input type="password" class="dlg-pw" autocomplete="off" style="width:100%;margin-bottom:12px"><div class="actions"><button type="submit">${t('weiter')}</button><button type="button" data-x class="secondary">${t('abbrechen')}</button></div></form>`;
    const done = v => { bg.remove(); res(v || null); };
    bg.querySelector('form').addEventListener('submit', e => { e.preventDefault(); done(bg.querySelector('.dlg-pw').value); });
    bg.querySelector('[data-x]').addEventListener('click', () => done(''));
    bg.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); done(''); } });
    document.body.appendChild(bg); bg.querySelector('.dlg-pw').focus();
  });
}
function saveJson(obj, name) {
  // Antwort als Datei speichern (Download ohne Umweg ueber eine Adresse)
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 1)], {type: 'application/json'})); a.download = name;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}
function toast(msg, ms = 2600) { const t = $('#toast'); t.textContent = msg; t.classList.remove('hidden'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add('hidden'), ms); t._until = Date.now() + ms; }
// a note that may wait: not over one still being read (e.g. the result of a sync when the report follows quickly)
function toastQuiet(msg, ms) { const t = $('#toast'); if (!t._until || Date.now() > t._until) toast(msg, ms); }
// what the installed version found in the files of an available update (empty: it installs as always, without a word)
// an update's findings that need your approval: all but those Kontor judged plain (only stricter, or behind a card in the chat) --
// one without a level (not judged) counts; the plain ones, for one quiet line
const upFinds = u => ((u && u.newer && u.review && u.review.findings) || []).filter(f => f.level !== 'plain');
const upPlain = u => ((u && u.newer && u.review && u.review.findings) || []).filter(f => f.level === 'plain');
function banner(msg, kind = '') { const b = $('#banner'); if (!msg) { b.classList.add('hidden'); return; } b.textContent = msg; b.className = 'banner ' + kind; }

// Am Mac selbst gibt es keine Offline-Ansicht: der Dienst ist erreichbar oder nicht (Tests können das Gerät als "entfernt" markieren)
let IS_LOCAL = ['127.0.0.1', 'localhost', '::1', '[::1]'].includes(location.hostname);
try { if (LS.get('kontor.testRemote') === '1') IS_LOCAL = false; } catch (e) {}
// the last time you touched the page: requests made later than a minute after it (status poll, progress) do not keep the
// session open -- the idle lock comes after the set minutes even with the window open
let USER_ACT = Date.now();
for (const ev of ['pointerdown', 'pointermove', 'keydown', 'touchstart', 'wheel', 'dragover', 'drop']) document.addEventListener(ev, () => { USER_ACT = Date.now(); }, {passive: true, capture: true});
async function api(path, body, method, netMode, renewed) {
  const opts = { method: method || (body === undefined ? 'GET' : 'POST'), headers: {}, credentials: 'same-origin' };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  if (S.csrf) opts.headers['X-CSRF-Token'] = S.csrf;
  if (Date.now() - USER_ACT > 60000) opts.headers['X-Kontor-Background'] = '1';      // not touched for a minute: no activity (idle lock)
  const mode = netMode || (IS_LOCAL ? 'direct' : (OFFLINE.mode && opts.method === 'GET' ? 'cache' : ''));
  if (mode) opts.headers['X-Kontor-Net'] = mode;
  let ctl = null;
  if (mode === 'direct' && !IS_LOCAL) { ctl = new AbortController(); opts.signal = ctl.signal; setTimeout(() => ctl.abort(), 20000); }
  let r;
  try { r = await fetch(path, opts); } catch (e) { throw new Error(IS_LOCAL ? t('err_dienst_lokal') : t('err_mac_weg')); }
  if (r.headers.get('X-Kontor-Offline') === '1' && opts.method === 'GET' && !OFFLINE.mode && !IS_LOCAL && mode !== 'direct' && path !== '/api/session') {
    // Zwischengespeicherte Antwort, obwohl wir online waren: Server nur langsam? Gegenprobe ohne Zeitlimit
    try { return await api(path, body, method, 'direct'); }
    catch (e) { OFFLINE.mode = true; offlineBanner(); }
  }
  let data = null;
  if (r.headers.get('X-Kontor-Enc') === '1') {          // the stored copy: only readable with the key the password unlocks
    if (!OFFKEY) { S.csrf = null; OFFLINE.mode = true; showLogin(); throw new Error(t('err_offline_passwort')); }
    try { data = await offOpen(await r.arrayBuffer()); } catch (e) { data = {}; }
  } else { try { data = await r.json(); } catch (e) { data = {}; } }
  if (r.headers.get('X-Kontor-Offline') === '1') {
    const at = r.headers.get('X-Kontor-Cached-At'); if (at) OFFLINE.as_of = at;
    if (IS_LOCAL) throw new Error(t('err_dienst_antwortet_nicht'));
  } else if (OFFLINE.mode && opts.method === 'GET' && r.ok && path !== '/api/session') { OFFLINE.mode = false; OFFLINE.as_of = null; offlineBanner(); }
  if (r.ok && !r.headers.get('X-Kontor-Offline') && (r.headers.get('X-Kontor-Demo') === '1') !== DEMO_PAGE && !$('#shell').classList.contains('hidden')) {
    history.replaceState(null, '', location.pathname); location.reload();          // the demo began or ended in another window: this page anew
    throw new Error(t('seite_wird_neu_geladen').trim());
  }
  if (r.status === 401 && ['/api/login', '/api/touchid'].includes(path)) { const e = new Error(data.error || t('nicht_angemeldet')); e.status = 401; throw e; }      // a sign-in that failed: why (wrong password)
  if (r.status === 401 && path !== '/api/session') { S.csrf = null; if (OFFLINE.mode) { OFFLINE.mode = false; OFFLINE.as_of = null; checkSession(); } else showLogin(); const e = new Error(t('nicht_angemeldet')); e.status = 401; throw e; }
  if (r.status === 403 && data.csrf === 'invalid' && !renewed) {
    // signed in again meanwhile (e.g. in another window): the token of this page is old -- take the current one, try once more
    try { const s = await fetch('/api/session', {credentials: 'same-origin'}).then(x => x.json()); if (s.signed_in && s.csrf) { S.csrf = s.csrf; return await api(path, body, method, netMode, true); } } catch (e) {}
  }
  if (!r.ok) { const e = new Error(data.error || (t('fehler') + r.status)); e.data = data; e.status = r.status; throw e; }
  if (opts.method !== 'GET' && data && data.report === 'requested') afterRebuild(data);
  return data;
}
// a file from Kontor itself: only one of its own addresses (/api/...), never another place
function download(url) { if (!/^\/(?!\/)/.test(String(url))) return; const a = document.createElement('a'); a.href = url; a.download = ''; document.body.appendChild(a); a.click(); a.remove(); }
const xlsxBtn = (was, extra = '') => `<button class="xlsx small" data-xlsx="${was}" ${extra}>Excel</button>`;

// ---------------------------------------------------------------- Offline (PWA am iPhone, Mac nicht erreichbar)
const OFFLINE = {mode: false, as_of: null, idle: null};
// ---------------------------------------------------------------- Drucken (⌘P, or a chart's own menu): the page as shown
// A line on top names what is printed (page, area, period), Kontor's version, when it was printed and the state of the data from
// MoneyMoney. Nothing is drawn anew for the paper: the page is scaled to the page width (a wide table prints what is in view).
const PRINT = {on: false, off: null, theme: null};
const fmtStamp = ts => ts ? FD(ts) + (ts.length >= 16 ? ' ' + ts.slice(11, 16) : '') : '–';
function printHead() {
  const st = S.STATUS || {}, m = st.moneymoney || {}, ttl = $('#page-title'), area = $('#bereich-seg:not(.hidden) button.on');
  let what = `<b>${esc(ttl && ttl.firstChild ? ttl.firstChild.textContent.trim() : '')}</b>` + (area ? ' · ' + esc(area.textContent) : '');
  const D = B(); if (S.tab === 'cashflow' && D) { const [cur] = cfMonths(D, S.cfZeit); if (cur && cur.length) what += ' · ' + esc(cfSpanLabel(cur)) + ' (' + esc(spanText(cur.length)) + ')'; }
  const now = new Date(), stamp = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0') + ' ' + String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');
  return `<span>${what}</span><span>Kontor ${esc(PAGE_VERSION)} · ${esc(t('druck_am', fmtStamp(stamp)))} · ${esc(t('druck_mm_stand', fmtStamp(m.as_of)))}</span>`;
}
// colours a chart computed from the theme (account shades, the flow's bands): drawn again in the theme now (light on paper)
function printRecolor() {
  ACC_CACHE.clear();
  try {
    if (S.tab === 'balance') {
      const D = B();
      if (BCH.d) { BCH.d = bchData(D); bchDraw(); }
      const pr = lcPosRole(D); if (pr && LC.pos && $('.lc[data-lc="pos"]')) { lcInit('pos', D, null, ROLE[pr][0], ROLE[pr][1], pr); lcDraw('pos'); }
      $$('#main i.pos-dot[data-sh]').forEach(i => { const [c, n, j] = i.dataset.sh.split('|'); let sh = accShade(c, +n); if (j) sh = accShade(sh.color, +j); i.style.cssText = swatch(sh.color, sh.hatch); });
    }
    if (S.tab === 'cashflow') cfDrawFlow();
  } catch (e) {}
}
window.addEventListener('beforeprint', () => {
  if (PRINT.on) return;          // once per print (the Mac app sends it too)
  PRINT.on = true;
  PRINT.theme = document.documentElement.dataset.theme; document.documentElement.dataset.theme = 'light';          // on paper: always light
  if (PRINT.theme !== 'light') printRecolor();
  const main = $('#main'); if (!main) return;
  document.documentElement.style.setProperty('--print-zoom', String(Math.min(1, 1040 / Math.max(1, main.getBoundingClientRect().width))));
  let h = $('#print-head'); if (!h) { h = document.createElement('div'); h.id = 'print-head'; main.parentNode.insertBefore(h, main); }
  h.innerHTML = printHead();
});
window.addEventListener('afterprint', () => {
  if (!PRINT.on) return;
  PRINT.on = false; document.documentElement.style.removeProperty('--print-zoom');
  const was = PRINT.theme; if (was) document.documentElement.dataset.theme = was; PRINT.theme = null; if (was && was !== 'light') printRecolor();
  const h = $('#print-head'); if (h) h.remove();
  (PRINT.off || []).forEach(x => x.classList.remove('print-off', 'print-path')); PRINT.off = null; document.body.classList.remove('print-one');
});
// one chart alone: everything beside its way up to the page is left out while printing
function printOne(card) {
  const marked = [];
  for (let el = card; el && el.parentElement && el !== document.body; el = el.parentElement) {
    if (el !== card) { el.classList.add('print-path'); marked.push(el); }
    for (const sib of el.parentElement.children) if (sib !== el) { sib.classList.add('print-off'); marked.push(sib); }
  }
  const name = card.closest('#drawer') && $('#drawer > h2'); if (name) name.classList.remove('print-off');          // a chart of the side window: with its name
  PRINT.off = marked; document.body.classList.add('print-one'); window.print();
}
// a small menu of its own at the pointer (a right click, see below)
function ctxMenu(x, y, items) {          // items: [label, action], '-' (a line between groups) or {head} (a group's name)
  const old = $('#ctx'); if (old) old.remove();
  const m = document.createElement('div'); m.id = 'ctx'; m.className = 'ctx'; m.setAttribute('role', 'menu');
  m.innerHTML = items.map((it, i) => it === '-' ? '<hr>' : it.head ? `<div class="ctx-h" role="presentation">${esc(it.head)}</div>` : `<button role="menuitem" data-i="${i}">${esc(it[0])}</button>`).join(''); document.body.appendChild(m);
  const r = m.getBoundingClientRect(); m.style.left = Math.min(x, innerWidth - r.width - 8) + 'px'; m.style.top = Math.min(y, innerHeight - r.height - 8) + 'px';
  const t0 = performance.now(), scrolled = () => { if (performance.now() - t0 > 250) close(); };          // a scroll still on its way from before the click: not one
  const close = () => { m.remove(); document.removeEventListener('pointerdown', away, true); document.removeEventListener('keydown', esc_, true); window.removeEventListener('scroll', scrolled); $('main').removeEventListener('scroll', scrolled); };
  const away = e => { if (!m.contains(e.target)) close(); }, esc_ = e => { if (e.key === 'Escape') close(); };
  document.addEventListener('pointerdown', away, true); document.addEventListener('keydown', esc_, true); window.addEventListener('scroll', scrolled); $('main').addEventListener('scroll', scrolled);          // the page scrolled (not a table inside it)
  m.addEventListener('click', e => { const b = e.target.closest('button[data-i]'); if (!b) return; close(); items[+b.dataset.i][1](); });
  $('button', m).focus();
}
// a right click (or ctrl-click) on the page: the assistant explains what is under the pointer at once, or it goes into the chat
// for a question; copy it (a figure, a row, a column, a selected text); print a chart alone -- with shift: the browser's own menu
// what was selected just before a right click (or ctrl-click): Safari and the Mac app select the word under the pointer with the
// click itself -- read before that (capture, before the browser acts), so a reference is never just that word without its place
const REFSEL = {text: ''};
document.addEventListener('pointerdown', e => { if (e.button === 2 || (e.button === 0 && e.ctrlKey)) { const s = getSelection(); REFSEL.text = s && !s.isCollapsed ? s.toString() : ''; } }, true);
document.addEventListener('contextmenu', e => {
  if (e.defaultPrevented || e.shiftKey || !e.target.closest || e.target.closest('input, textarea, select, a, .ctx, .as-pop')) return;          // a long touch that opened a row: nothing more
  const card = e.target.closest(REF_CHARTS), ref = refAt(e), items = [];
  const s = getSelection(); if (ref && s && !s.isCollapsed && s.toString() !== REFSEL.text) s.removeAllRanges();          // the word the click itself selected: not left marked
  REFSEL.text = '';
  if (ref && asOn()) items.push({head: t('ki_assistent_lang')}, [t('ki_kurz'), () => asQuick(ref, e.clientX, e.clientY)], [t('ki_im_chat'), () => asAskAbout(ref)]);
  const more = [];
  if (ref && ref.copy) more.push([t(ref.copyKey || 'kopieren'), () => copyText(ref.copy)]);
  if (card) more.push([t('grafik_drucken'), () => printOne(card)]);
  if (more.length) items.push(...(items.length ? ['-'] : []), ...more);
  if (!items.length) return;
  e.preventDefault(); ctxMenu(e.clientX, e.clientY, items);
});
async function copyText(s) {          // to the clipboard -- the old way where the browser has no clipboard for scripts
  try { await navigator.clipboard.writeText(s); return; } catch (e) {}
  const ta = document.createElement('textarea'); ta.value = s; ta.style.cssText = 'position:fixed;opacity:0'; document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); } catch (e) {} ta.remove();
}
function offlineBanner() {
  if (OFFLINE.mode) { const b = $('#banner'); b.innerHTML = `${t('offline_ansicht_der_mac_ist', OFFLINE.as_of ? new Date(OFFLINE.as_of).toLocaleString(LOCALE, {dateStyle: 'short', timeStyle: 'short'}) : t('unbekannt'), hq('offline'))}`; b.className = 'banner info'; }
  else if (S.DATA) banner('');
  idleReset();
}
function idleReset() {
  clearTimeout(OFFLINE.idle);
  if (OFFLINE.mode && S.csrf) OFFLINE.idle = setTimeout(() => { S.csrf = null; OFFKEY = null; showLogin(); }, Math.max(1, ((S.CFG && S.CFG.ui) || {}).lock_minutes || 15) * 60000);
}
for (const ev of ['pointerdown', 'keydown', 'touchstart']) document.addEventListener(ev, idleReset, {passive: true});
async function offlinePing() {
  // Im Offline-Modus alle 30 s prüfen, ob der Mac wieder da ist (Sitzung ist nie zwischengespeichert)
  if (!OFFLINE.mode || document.hidden) return;
  try { const s = await api('/api/session'); if (!s.offline) await revalidate(); } catch (e) {}
}
setInterval(() => { if (!S.bye) offlinePing(); }, 30000);
// The offline copy on this device is encrypted (see sw.js): a key pair per device; the public key encrypts every stored
// answer, the private key lies on the device only encrypted with a key from the Kontor password (PBKDF2) and is unlocked
// into memory at a password sign-in -- never stored readable, gone when the page locks or closes.
let OFFKEY = null;
const OFF_ROUNDS = 400000;
function offIdb(fn) {
  return new Promise((res, rej) => {
    const o = indexedDB.open('kontor-off', 1);
    o.onupgradeneeded = () => o.result.createObjectStore('k');
    o.onerror = () => rej(o.error);
    o.onsuccess = () => { const tx = o.result.transaction('k', 'readwrite'), st = tx.objectStore('k'), q = fn(st); tx.oncomplete = () => res(q && q.result); tx.onerror = () => rej(tx.error); };
  });
}
async function offKek(pw, salt) {
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({name: 'PBKDF2', hash: 'SHA-256', salt, iterations: OFF_ROUNDS}, base, {name: 'AES-GCM', length: 256}, false, ['encrypt', 'decrypt']);
}
async function offUnlock(pw) {
  // the private key of this device, unlocked with the password; null: no key pair, false: wrong password
  const rec = await offIdb(st => st.get('pair')).catch(() => null); if (!rec) return null;
  try {
    const pk = await crypto.subtle.decrypt({name: 'AES-GCM', iv: rec.iv}, await offKek(pw, rec.salt), rec.wrapped);
    return await crypto.subtle.importKey('pkcs8', pk, {name: 'RSA-OAEP', hash: 'SHA-256'}, false, ['decrypt']);
  } catch (e) { return false; }
}
async function offKeyEnsure(pw) {
  // at a password sign-in with the Mac: unlock this device's key, or (first time, or a new password) make a new pair
  if (IS_LOCAL || !(window.crypto && crypto.subtle) || !window.indexedDB || !(SESSION && SESSION.offline_copy !== false)) return;
  try {
    const k = await offUnlock(pw); if (k) { OFFKEY = k; return; }
    const pair = await crypto.subtle.generateKey({name: 'RSA-OAEP', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256'}, true, ['encrypt', 'decrypt']);
    const salt = crypto.getRandomValues(new Uint8Array(16)), iv = crypto.getRandomValues(new Uint8Array(12));
    const pk = await crypto.subtle.exportKey('pkcs8', pair.privateKey);
    const wrapped = await crypto.subtle.encrypt({name: 'AES-GCM', iv}, await offKek(pw, salt), pk);
    const spki = await crypto.subtle.exportKey('spki', pair.publicKey);
    await offIdb(st => st.put({spki, salt, iv, wrapped}, 'pair'));
    OFFKEY = await crypto.subtle.importKey('pkcs8', pk, {name: 'RSA-OAEP', hash: 'SHA-256'}, false, ['decrypt']);
    if (navigator.serviceWorker && navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage('key-changed');
  } catch (e) { OFFKEY = null; }
}
async function offForget() {
  // the stored copy and the key pair of this device gone
  OFFKEY = null;
  try { await offIdb(st => st.delete('pair')); } catch (e) {}
  try { const ks = await caches.keys(); await Promise.all(ks.filter(k => k.startsWith('kontor-data')).map(k => caches.delete(k))); } catch (e) {}
}
async function offOpen(buf) {
  const b = new Uint8Array(buf), n = (b[0] << 8) | b[1];
  const raw = await crypto.subtle.decrypt({name: 'RSA-OAEP'}, OFFKEY, b.slice(2, 2 + n));
  const aes = await crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['decrypt']);
  const pt = await crypto.subtle.decrypt({name: 'AES-GCM', iv: b.slice(2 + n, 14 + n)}, aes, b.slice(14 + n));
  return JSON.parse(new TextDecoder().decode(pt));
}
async function offlineLogin(pw) {
  if (!(window.crypto && crypto.subtle) || !window.indexedDB) throw new Error(t('err_offline_https'));
  const k = await offUnlock(pw);
  if (k === null) throw new Error(t('err_keine_offline_kopie'));
  if (k === false) throw new Error(t('err_passwort_falsch'));
  OFFKEY = k;
  try { const v = await api('/api/offline/verifier'); if (S.CFG) S.CFG.ui = Object.assign(S.CFG.ui || {}, {lock_minutes: v.lock_minutes}); } catch (e) {}
  return true;
}
function swApply(allowed) {
  if (!('serviceWorker' in navigator)) return;
  if (allowed) { navigator.serviceWorker.register('/sw.js').catch(() => {}); return; }
  navigator.serviceWorker.getRegistrations().then(rs => rs.forEach(r => r.unregister())).catch(() => {});
  try { caches.keys().then(ks => ks.filter(k => k.startsWith('kontor-')).forEach(k => caches.delete(k))); } catch (e) {}
  if (!IS_LOCAL) offForget();
}

// ---------------------------------------------------------------- Anmeldung
let SESSION = null;
// the version of the files this page runs (index.html): the service runs a newer one -> load the page again, also when the
// service restarted while the window was in the background (a new sign-in alone keeps the old files)
const PAGE_VERSION = ((document.querySelector('meta[name="kontor-version"]') || {}).content || '').replace(/^__.*/, '');
function checkVersion(v) {
  if (!v || !PAGE_VERSION || v === PAGE_VERSION) return false;
  let n = 0;
  try {             // the new files did not come (yet): not again and again
    const r = JSON.parse(sessionStorage.getItem('kontor.reload') || '{}');
    n = r.v === v && Date.now() - r.at < 60000 ? r.n : 0;
    sessionStorage.setItem('kontor.reload', JSON.stringify({v, at: Date.now(), n: n + 1}));
  } catch (e) {}
  if (n >= 3) return false;
  if (!checkVersion.on) { checkVersion.on = true; toast(t('neue_version') + v + t('seite_wird_neu_geladen'), 3000); setTimeout(() => location.reload(), 800); }
  return true;
}
// the service restarts (an update): reload only once it answers again -- a reload while it is away leaves an error page
// (in the web app in the Dock only ⌘R helped then); newVersion: wait until it runs another version than this page
async function waitAndReload(newVersion) {
  if (waitAndReload.on) return;
  waitAndReload.on = true;
  const until = Date.now() + 180000;
  while (Date.now() < until) {
    await new Promise(r => setTimeout(r, 1500));
    let s = null;
    try { const r = await fetch('/api/session', {credentials: 'same-origin', cache: 'no-store'}); if (r.ok) s = await r.json(); } catch (e) {}
    if (s && s.version && !s.offline && (!newVersion || !PAGE_VERSION || s.version !== PAGE_VERSION)) break;
  }
  location.reload();
}
async function checkSession() {
  try { SESSION = await api('/api/session'); } catch (e) { $('#login').classList.remove('hidden'); $('#login-err').textContent = e.message + t('neuer_versuch_in_5_s'); setTimeout(checkSession, 5000); return; }
  if (!SESSION.demo) swApply(!IS_LOCAL && SESSION.offline_copy !== false);     // the offline copy is for the iPhone; on the Mac it would only leave stale pages behind (e.g. after a port change) -- the demo leaves it as it is (keeps nothing in it)
  if (!SESSION.offline && checkVersion(SESSION.version)) return;
  $('#ver').textContent = 'v' + (PAGE_VERSION || SESSION.version || '');
  if (SESSION.offline && IS_LOCAL) { $('#login').classList.remove('hidden'); $('#login-err').textContent = t('der_kontor_dienst_antwortet_nicht'); setTimeout(checkSession, 5000); return; }
  if (SESSION.offline) { OFFLINE.mode = true; showLogin(); return; }
  OFFLINE.mode = false;
  if (SESSION.signed_in) { S.csrf = SESSION.csrf; await enterApp(); } else showLogin();
}
function showLogin() {
  if (DEMO_PAGE) {          // the demo locked: loaded anew (nothing of it stays), the sign-in still set to the demo -- no Touch ID at once
    try { sessionStorage.setItem('kontor.login', 'demo'); } catch (e) {}
    history.replaceState(null, '', location.pathname); location.reload(); return;
  }
  asMicStop(false);          // a recording does not run on behind the lock
  $('#shell').classList.add('hidden'); $('#login').classList.remove('hidden'); $('#drawer').classList.remove('open');
  if (FIND.open) findBar(false);
  keysShow();                // locked: the keys (and the Mac app's menu entries) that need Kontor open are off
  const setup = SESSION && SESSION.setup_needed && !OFFLINE.mode;
  if (setup || OFFLINE.mode) LOGIN.demo = false;
  $('#login-text').textContent = OFFLINE.mode ? t('der_mac_ist_nicht_erreichbar')
    : setup ? t('erster_start_passwort_festlegen_mindes')
    : LOGIN.demo ? t('demo_anmelden')
    : SESSION && SESSION.setup_local_only ? t('noch_kein_passwort_festgelegt_die')
    : SESSION && SESSION.waiting ? t('anmeldung_wartet') : '';
  $('#login-text').hidden = !$('#login-text').textContent;
  // Touch ID eingeschaltet (am Mac): nur Touch ID, Passwort erst auf Wunsch – nie beides gleichzeitig
  const tid = !setup && !OFFLINE.mode && SESSION && SESSION.touchid;
  const tidMode = tid && !LOGIN.pw;
  $('#login-pw2').classList.toggle('hidden', !setup);
  $('#setup-tid').classList.toggle('hidden', !(setup && SESSION && SESSION.touchid_available));
  $('#login-btn').textContent = setup ? t('passwort_festlegen') : LOGIN.demo ? t('demo_oeffnen') : t('anmelden');
  $('#tid-box').classList.toggle('hidden', !tidMode);
  $('#login-form').classList.toggle('hidden', !!tidMode);
  $('#tid-instead').classList.toggle('hidden', !(tid && LOGIN.pw));
  $('#login-err').textContent = SESSION && SESSION.locked_seconds ? (t('gesperrt_fuer') + SESSION.locked_seconds + t('s_nach_fehlversuchen')) : '';
  $('#demo-btn').classList.toggle('hidden', !!(setup || OFFLINE.mode || !SESSION || SESSION.setup_local_only));
  $('#demo-btn').textContent = t(LOGIN.demo ? 'demo_zurueck' : 'demo_link');
  if (!tidMode) setTimeout(() => { if (!$('#login').contains(document.activeElement)) $('#login-pw').focus(); }, 50);   // never move the cursor out of a field being filled
  if (tidMode) tryTouchId(true);     // Touch ID at once, without a click -- only while Kontor is the active window (see tryTouchId)
}
const LOGIN = {pw: false, demo: false};      // pw: "Stattdessen Passwort eingeben" gewählt; demo: die Anmeldung öffnet die Demo
const TID = {pending: false, lastTry: 0, id: null};       // id: the request running (random) -- the demo link switches it
try { if (sessionStorage.getItem('kontor.login') === 'demo') { LOGIN.demo = true; TID.skipNext = true; } sessionStorage.removeItem('kontor.login'); } catch (e) {}
const tidAsk = () => { $('#login-err').textContent = t(LOGIN.demo ? 'touch_id_bitte_am_mac_demo' : 'touch_id_bitte_am_mac'); };
async function tryTouchId(auto) {
  if (TID.pending || LOGIN.pw || !(SESSION && SESSION.touchid && !SESSION.setup_needed)) return;
  if (auto && TID.skipNext) { TID.skipNext = false; return; }           // nach bewusstem Sperren nicht sofort wieder fragen
  if (auto && Date.now() - TID.lastTry < 4000) return;
  // only when you are in Kontor: a lock that happened in the background (or a window just becoming visible) does not put the
  // system dialog in front of what you are doing -- it comes when you switch to Kontor (focus -> revalidate)
  if (auto && (document.hidden || !document.hasFocus())) return;
  TID.pending = true; TID.lastTry = Date.now();
  TID.id = Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
  tidAsk();
  let again = false;
  try { const r = await api('/api/touchid', Object.assign({tid: TID.id}, LOGIN.demo ? {demo: true} : {})); if (r.demo) return demoEnter(); S.csrf = r.csrf; $('#login-err').textContent = ''; await enterApp(); }
  catch (err) {
    if (err.status === 409 && err.data && err.data.switched) again = true;          // switched meanwhile: its window closed, asked anew for that
    else if (err.status === 409 && LOGIN.demo && err.data && err.data.signed_in) location.reload();     // signed in meanwhile (another window)
    else $('#login-err').textContent = auto ? t('touch_id_nicht_bestaetigt_erneut') : err.message;
  }
  finally { TID.pending = false; TID.id = null; }
  if (again) tryTouchId(false);
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
  if (checkVersion(s.version)) return;
  if (OFFLINE.mode) { OFFLINE.mode = false; OFFLINE.as_of = null; SESSION = s; S.csrf = s.signed_in ? s.csrf : null; if (s.signed_in) { await enterApp(); } else showLogin(); return; }
  if (!s.signed_in && !loginShown) { SESSION = s; S.csrf = null; showLogin(); }
  else if (!s.signed_in && loginShown && s.touchid && !s.setup_needed) { SESSION = s; tryTouchId(true); }
  else if (s.signed_in && loginShown) { SESSION = s; S.csrf = s.csrf; await enterApp(); }
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) revalidate(); });
window.addEventListener('focus', revalidate);
$('#login-form').addEventListener('submit', async e => {
  e.preventDefault();
  if (LOGIN.busy) return;          // a second click (↩) while the first is on its way: nothing more
  LOGIN.busy = true;
  try { await loginSubmit(); } finally { LOGIN.busy = false; }
});
async function loginSubmit() {
  const pw = $('#login-pw').value, setup = SESSION && SESSION.setup_needed && !OFFLINE.mode;
  if (setup && pw !== $('#login-pw2').value) { $('#login-err').textContent = t('passwoerter_stimmen_nicht_ueberein'); return; }
  if (OFFLINE.mode) {
    $('#login-err').textContent = t('pruefe');
    try { await offlineLogin(pw); S.csrf = 'offline'; $('#login-pw').value = ''; $('#login-err').textContent = ''; await enterApp(); } catch (err) { $('#login-err').textContent = err.message; }
    return;
  }
  try {
    if (LOGIN.demo && !setup) $('#login-err').textContent = t('demo_startet');
    const r = await api(setup ? '/api/setup' : '/api/login', setup ? Object.assign({password: pw, language: LANG}, SESSION.touchid_available ? {touchid: $('#setup-tid-cb').checked} : {}) : Object.assign({password: pw}, LOGIN.demo ? {demo: true} : {}));
    if (r.demo) return demoEnter();
    LOGIN.pw = false;
    S.csrf = r.csrf; $('#login-pw').value = ''; $('#login-pw2').value = '';
    await offKeyEnsure(pw);
    await enterApp();
  } catch (err) { if (err.status === 409 && LOGIN.demo && err.data && err.data.signed_in) location.reload(); else $('#login-err').textContent = err.message; }      // signed in meanwhile (another window): that window's Kontor
}
$('#touchid-btn').addEventListener('click', () => tryTouchId(false));
$('#lang-sel').addEventListener('change', e => setLang(e.target.value, true));
$('#pw-instead').addEventListener('click', () => { LOGIN.pw = true; showLogin(); });
$('#tid-instead').addEventListener('click', () => { LOGIN.pw = false; showLogin(); });
$('#sync-btn').addEventListener('click', () => syncNow(false, true));
$('.side .brand').addEventListener('click', e => { go(e.target.closest('#ver') && !demoOn() ? '#settings/updates' : '#overview'); });
async function lockNow() { try { await api('/api/lock', {}); } catch (e) {} S.csrf = null; OFFKEY = null; TID.skipNext = true; await checkSession(); }
// the demo: Kontor with made-up data, to show it -- opened with the same sign-in (the link below the card switches the sign-in to it)
const demoOn = () => !!(SESSION && SESSION.demo);
$('#demo-btn').title = t('demo_link_tip');
$('#demo-btn').addEventListener('click', () => {
  LOGIN.demo = !LOGIN.demo; $('#login-err').textContent = ''; showLogin();
  // a Touch ID window open: confirmed, it opens what is chosen now -- it closes, and the page asks anew (its window says which)
  if (TID.pending && TID.id) { if (!LOGIN.pw) tidAsk(); api('/api/touchid/switch', {tid: TID.id, demo: LOGIN.demo}).catch(() => {}); }
});
// signed in to the demo: the page loads anew -- into the demo and out of it, nothing of one stays in the page's memory for the other
function demoEnter() { $('#login-pw').value = ''; history.replaceState(null, '', '#overview'); location.reload(); }
let DEMO_PAGE = false;          // this page shows the demo (set when it opens; it is never shown again without loading anew)
function demoUi() {
  const on = demoOn();
  $('#demo-badge').classList.toggle('hidden', !on);
  const st = $('#nav a[href="#settings"]'); if (st) st.classList.toggle('hidden', on);
}
$('#lock-btn').addEventListener('click', lockNow);
// ---------------------------------------------------------------- Tastaturkürzel
// One list for the keys. The page answers them -- in Kontor's Mac app its menu does instead (it gets the list, words and keys,
// from here and calls kontorCmd), so no key counts twice. A browser keeps some keys for itself (⇧⌘R Reader or a hard reload,
// ⌘1–9 tabs, ⌘L the address, ⌘G its find): those work only in an app ("app": the Mac app or Safari's web app, "shell": the
// Mac app), and only where a key works is it shown (in the tooltip and in the menu). ⌘R reloads the page everywhere, as in
// any browser (in the Mac app its own menu entry: it also brings back an error page) -- syncing with MoneyMoney is ⇧⌘R.
function cmds() {
  const inside = !!S.csrf && $('#login').classList.contains('hidden'), save = $('#main [data-cmd-s]');
  const nav = $$('#nav a[href^="#"]').filter(a => !a.classList.contains('hidden') && !a.closest('.hidden') && a.id !== 'nav-assist').slice(0, 9);
  return [
    {id: 'sync', menu: 'file', key: 'r', shift: true, where: 'app', t: t('mac_m_sync'), on: inside && !OFFLINE.mode && !SYNC.busy, run: () => syncNow(false, true)},
    {id: 'save', menu: 'file', key: 's', where: 'all', t: t('mac_m_sichern'), on: !!save && !save.disabled, run: () => { const b = $('#main [data-cmd-s]'); if (b && !b.disabled) b.click(); }},
    {id: 'lock', menu: 'file', key: 'l', where: 'all', shown: 'app', t: t('btn_sperren'), on: inside, run: lockNow},          // (a browser mostly keeps ⌘L: not shown there)
    {id: 'find', menu: 'find', key: 'f', where: 'all', t: t('mac_m_suchen'), on: true, run: findOpen},
    {id: 'findNext', menu: 'find', key: 'g', where: 'shell', t: t('find_weiter'), on: FIND.open && FIND.hits.length > 0, run: () => findStep(1)},
    {id: 'findPrev', menu: 'find', key: 'g', shift: true, where: 'shell', t: t('find_zurueck'), on: FIND.open && FIND.hits.length > 0, run: () => findStep(-1)},
    {id: 'assistant', menu: 'view', key: 'k', where: 'all', t: t('ki_assistent'), on: inside && asOn() && S.tab !== 'assistant', run: () => asShow(!AS.open)},
    ...nav.map((a, i) => ({id: 'page' + (i + 1), menu: 'view', key: String(i + 1), where: 'app', t: (a.querySelector('span') || a).textContent.trim(),
      href: a.getAttribute('href'), on: inside, run: () => go(a.getAttribute('href'))}))];
}
const keyLive = c => c.where === 'all' || (c.where === 'app' && APP_MODE) || SHELL;
const keyShown = c => keyLive(c) && (c.shown !== 'app' || APP_MODE);
const keyText = c => (c.shift ? '⇧' : '') + '⌘' + c.key.toUpperCase();
function keyHint(id) { const c = cmds().find(x => x.id === id); return c && keyShown(c) ? ` (${keyText(c)})` : ''; }
function kontorCmd(id) { const c = cmds().find(x => x.id === id); if (c && c.on) c.run(); return !!(c && c.on); }          // the Mac app's menu
document.addEventListener('keydown', e => {
  if (!e.metaKey || e.altKey || e.ctrlKey || SHELL) return;          // the Mac app: its menu answers
  const k = (e.key || '').toLowerCase(), c = cmds().find(x => x.key === k && !!x.shift === e.shiftKey);
  if (!c || !keyLive(c)) return;
  if (c.id === 'find') { if (findOpen()) e.preventDefault(); return; }          // the page's own search -- else the browser's find
  if (c.id === 'save' && $('#main [data-cmd-s]')) e.preventDefault();          // (not the browser's "save page", also while nothing changed)
  if (c.on) { e.preventDefault(); c.run(); }
});
// the title bar's height (taller in a narrow window): what sticks right below it (the help's search) sits there
try { const tb = $('.topbar'); if (tb) new ResizeObserver(() => document.documentElement.style.setProperty('--topbar-h', tb.offsetHeight + 'px')).observe(tb); } catch (e) {}
// to the Mac app: its menu entries (sent again only when they change; on/off too); the keys in the tooltips
let SHELL_CMDS = '';
function keysShow() {
  const list = cmds();
  if (SHELL) {
    const menu = list.map(c => ({id: c.id, menu: c.menu, key: c.key, shift: !!c.shift, title: c.t, on: !!c.on})), sig = JSON.stringify(menu);
    if (sig !== SHELL_CMDS) { SHELL_CMDS = sig; shellPost({commands: menu}); }
  }
  const hint = id => { const c = list.find(x => x.id === id); return c && keyShown(c) ? ` (${keyText(c)})` : ''; };
  const tip = (el, base, id) => { if (el) el.title = base + hint(id); };
  tip($('#lock-btn'), t('sperren_tip'), 'lock');
  tip($('#assist-btn'), t('ki_tip'), 'assistant');
  $$('#nav a[href^="#"]').forEach(a => { const c = list.find(x => x.href === a.getAttribute('href')); a.title = c && keyShown(c) ? `${c.t} (${keyText(c)})` : ''; });
  $$('#main [data-cmd-s]').forEach(b => { if (b.dataset.tip == null) b.dataset.tip = b.title || b.textContent.trim(); b.title = b.dataset.tip + hint('save'); });
  $$('[data-find]').forEach(f => { f.title = f.placeholder + hint('find'); });
}

// Find on the page (⌘F): the page's own search where it has one (the help, transactions: marked data-find) -- else, in the
// Mac app (it has no find of its own), a find bar: every hit marked, the current one stronger, ⌘G / ⇧⌘G or ↩ / ⇧↩ go on;
// gone with esc, ⌘F again or a click anywhere else.
// Marks without touching the page (CSS highlights); what the page draws anew is searched again, the place kept.
const FIND = {open: false, q: '', hits: [], i: -1, tm: 0, mt: 0, mo: null};
function findOpen() {
  const own = $$('[data-find]').find(el => el.getClientRects().length && !el.disabled);
  if (own) { own.focus(); own.select(); return true; }
  if (!SHELL) return false;
  findBar(!FIND.open);
  return true;
}
document.addEventListener('pointerdown', e => { const bar = $('#find'); if (FIND.open && bar && !bar.contains(e.target)) findBar(false); }, true);
function findBar(open) {
  let bar = $('#find');
  if (!open) {
    if (bar) bar.remove();
    if (FIND.mo) FIND.mo.disconnect();
    clearTimeout(FIND.tm); clearTimeout(FIND.mt);
    Object.assign(FIND, {open: false, hits: [], i: -1, mo: null});
    findMarks();
    keysShow();
    return;
  }
  if (!bar) {
    bar = document.createElement('div'); bar.id = 'find'; bar.className = 'find'; bar.setAttribute('role', 'search');
    bar.innerHTML = `<input type="search" id="find-q" placeholder="${t('find_ph')}" aria-label="${t('find_ph')}" autocomplete="off" spellcheck="false">
      <span id="find-n" class="small muted" aria-live="polite"></span>
      <button class="ico" id="find-prev" title="${t('find_zurueck')} (⇧⌘G)" aria-label="${t('find_zurueck')}"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg></button>
      <button class="ico" id="find-next" title="${t('find_weiter')} (⌘G)" aria-label="${t('find_weiter')}"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg></button>
      <button class="small secondary" id="find-done">${t('find_fertig')}</button>`;
    document.body.appendChild(bar);
    const q = $('#find-q', bar);
    q.value = FIND.q;
    q.addEventListener('input', () => { FIND.q = q.value; clearTimeout(FIND.tm); clearTimeout(FIND.mt); FIND.tm = setTimeout(() => findRun(FIND.q), 120); });
    q.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); findStep(e.shiftKey ? -1 : 1); }
      if (e.key === 'Escape') { e.preventDefault(); findBar(false); }
    });
    $('#find-prev', bar).addEventListener('click', () => findStep(-1));
    $('#find-next', bar).addEventListener('click', () => findStep(1));
    $('#find-done', bar).addEventListener('click', () => findBar(false));
    FIND.mo = new MutationObserver(() => { clearTimeout(FIND.mt); FIND.mt = setTimeout(() => findRun(FIND.q, true), 250); });          // (its own timer: typing is never undone)
    FIND.mo.observe($('#main') || document.body, {childList: true, subtree: true, characterData: true});
  }
  FIND.open = true;
  const m = $('main'); if (m) bar.style.right = Math.max(16, innerWidth - m.getBoundingClientRect().right + 16) + 'px';          // over the page, not the assistant beside it
  const q = $('#find-q', bar); q.focus(); q.select();
  if (q.value.trim()) findRun(q.value);
}
function findRun(q, keep) {
  const was = FIND.i;
  FIND.q = q; FIND.hits = []; FIND.i = -1;
  const needle = q.trim().toLowerCase(), bar = $('#find');
  if (needle) {
    const skip = /^(SCRIPT|STYLE|NOSCRIPT|TEXTAREA|OPTION|SELECT)$/;
    const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {acceptNode: n => {
      const p = n.parentElement;
      if (!p || skip.test(p.tagName) || (bar && bar.contains(p)) || !n.data.trim() || !p.getClientRects().length) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }});
    for (let n = walk.nextNode(); n && FIND.hits.length < 2000; n = walk.nextNode()) {
      const hay = n.data.toLowerCase();
      if (hay.length !== n.data.length) continue;          // (a letter whose small form is longer: no exact place)
      for (let k = hay.indexOf(needle); k >= 0 && FIND.hits.length < 2000; k = hay.indexOf(needle, k + needle.length)) {
        const r = document.createRange(); r.setStart(n, k); r.setEnd(n, k + needle.length); FIND.hits.push(r);
      }
    }
  }
  if (keep && FIND.hits.length) { FIND.i = Math.min(Math.max(was, 0), FIND.hits.length - 1); findPaint(); }
  else if (FIND.hits.length) findStep(1);
  else findPaint();
  keysShow();
}
function findPaint() {
  const n = $('#find-n');
  if (n) n.textContent = !FIND.q.trim() ? '' : FIND.hits.length ? t('find_n', FIND.i + 1, FIND.hits.length) : t('find_keine');
  const bar = $('#find'); if (bar) bar.classList.toggle('none', !!FIND.q.trim() && !FIND.hits.length);
  findMarks();
}
// the marks: the same two highlights, emptied and filled anew -- replaced or removed, WebKit kept painting the old ones
function findMarks() {
  try {
    if (!window.Highlight || !CSS.highlights) return;
    if (!FIND.hl) { FIND.hl = new Highlight(); FIND.hn = new Highlight(); }
    CSS.highlights.set('kontor-find', FIND.hl); CSS.highlights.set('kontor-find-now', FIND.hn);
    FIND.hl.clear(); FIND.hn.clear();
    if (!FIND.open) return;
    FIND.hits.forEach(r => FIND.hl.add(r));
    if (FIND.hits[FIND.i]) FIND.hn.add(FIND.hits[FIND.i]);
  } catch (e) {}
}
function findStep(d) {
  if (!FIND.open || !FIND.hits.length) return;
  const n = FIND.hits.length;
  FIND.i = FIND.i < 0 ? (d > 0 ? 0 : n - 1) : (FIND.i + d + n) % n;
  findPaint();
  const el = FIND.hits[FIND.i].startContainer.parentElement;
  if (el) el.scrollIntoView({block: 'center', inline: 'nearest'});
}

async function enterApp() {
  if (demoOn() !== DEMO_PAGE && (DEMO_PAGE || $('#main').childElementCount)) { history.replaceState(null, '', demoOn() ? '#overview' : location.pathname); location.reload(); return; }     // into or out of the demo: anew
  DEMO_PAGE = demoOn();
  if (DEMO_PAGE) LS.demo = new Map();          // the demo changes nothing kept on this device: what it writes stays in the page's memory
  $('#login').classList.add('hidden'); $('#shell').classList.remove('hidden');
  demoUi();
  // nothing on the page yet (signed in after an update, the service still starting): something that turns, not a dark window
  if (!$('#main').childElementCount) $('#main').innerHTML = `<div class="loading"><span class="spin"></span>${t('0_wird_geladen', 'Kontor')}</div>`;
  await loadAll();
  if (!OFFLINE.mode && checkVersion((S.STATUS || {}).version)) return;        // signed in again after an update: the new files first
  await syncLang();
  // straight into the setup, at its first open step: on the very first start (nothing set up yet) and the first time Kontor
  // opens as an app at the Mac (created in step 1 -- the setup goes on here)
  if (demoOn() && DEMO_OFF.has((location.hash.slice(1).split(/[/?]/)[0]))) history.replaceState(null, '', '#overview');
  if (!location.hash && !OFFLINE.mode && !demoOn() && setupOpen() && (S.setup || !S.DATA || (APP_MODE && (S.STATUS || {}).local && !((S.CFG || {}).ui || {}).webapp)))
    history.replaceState(null, '', '#setup');
  // locked (⌘L, idle) with something typed in and not saved: signed in again, the page stays as you left it -- saved with its button
  if (!(DIRTY.on && DIRTY.hash === location.hash && $('#main .actions'))) route();
  if (!OFFLINE.mode) asLoad().then(() => { try { if (LS.get('kontor.assist') === '1' && asOn()) { AS.open = true; asLayout(); } } catch (e) {} if (S.tab === 'assistant' || S.tab === 'setup') route(); });
  if (!OFFLINE.mode && !demoOn()) api('/api/offline/verifier').catch(() => {});       // für die Offline-Ansicht zwischenspeichern
  if (APP_MODE) webappSeen();
  offlineBanner();
}
async function loadAll() {
  const [status, data, cfg, konten, kats] = await Promise.all([
    api('/api/status'), api('/api/dataset'), api('/api/config'), api('/api/accounts'), api('/api/categories')]);
  S.STATUS = status; S.DATA = data.empty ? null : data; S.CFG = cfg; S.KONTEN = konten.accounts || []; S.KATS = kats.categories || [];
  if (!(status.report || {}).running) BER.as_of = (status.report || {}).as_of || '';     // dieser Stand ist jetzt geladen
  S.setup = data.setup;
  if (S.DATA) { const keys = Object.keys(S.DATA.areas || {}); if (!S.area || !keys.includes(S.area)) S.area = S.DATA.main_area || keys[0]; }
  if (OFFLINE.mode) offlineBanner();
  else if (status.update && status.update.newer) banner('Kontor ' + status.update.available + t(upFinds(status.update).length ? 'upd_banner' : 'ist_verfuegbar_unter_updates_installie'), upFinds(status.update).length ? 'warn' : 'info');
  else if (S.DATA && (S.DATA.accounts_new || []).length) { const b = $('#banner'); b.innerHTML = `${t('neue_oder_unbestaetigte_konten_0', esc(S.DATA.accounts_new.slice(0, 4).map(k => k.name).join(', ')), S.DATA.accounts_new.length > 4 ? ' …' : '')} <a href="#accounts">${t('bereich_und_position_bestaetigen')}</a>`; b.className = 'banner info'; }
  else if (S.DATA) banner('');
  statusMini(); bereichSeg();
}
const B = () => (S.DATA && S.DATA.areas && S.DATA.areas[S.area] && !S.DATA.areas[S.area].error) ? S.DATA.areas[S.area] : null;
const BN = u => (S.DATA && S.DATA.area_names && S.DATA.area_names[u || S.area]) || '';
function mmState(st) {
  const m = st.moneymoney || {};
  if (!m.running) return {cls: 'off', text: t('moneymoney_aus')};
  if (m.locked === true) return {cls: 'warn', text: t('moneymoney_gesperrt')};
  if (m.locked === false) return {cls: 'ok', text: t('moneymoney_laeuft')};
  return {cls: 'ok', text: t('moneymoney_laeuft')};
}
const nKonten = n => n === 1 ? t('ein_konto') : n + t('konten');
function fmtZeit(ts) {
  // 'YYYY-MM-DD HH:MM' -> 'heute 13:40' / 'gestern 08:12' / '03.11. 22:10' / '03.11.25 22:10' (local time; English 03/11)
  if (!ts) return '';
  const iso = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  const now = new Date(), tag = ts.slice(0, 10), zeit = ts.slice(11, 16), sep = LANG === 'en' ? '/' : '.';
  if (tag === iso(now)) return t('zeit_heute', zeit);
  if (tag === iso(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1))) return t('zeit_gestern', zeit);
  const y = ts.slice(0, 4) === String(now.getFullYear()) ? '' : ts.slice(2, 4);
  return ts.slice(8, 10) + sep + ts.slice(5, 7) + (LANG === 'en' ? (y ? sep + y : '') : '.' + y) + ' ' + zeit;
}
function viewCtl() {
  // columns of the tables: months (with yearly sums) or years only
  return `<div class="seg" id="modus-seg">${[['months', t('monate'), t('monate_tip')], ['years', t('jahre'), '']].map(([k, l, tip]) => `<button data-m="${k}" class="${S.mode === k ? 'on' : ''}"${tip ? ` title="${tip}"` : ''}>${l}</button>`).join('')}</div>`;
}
const swCtl = (id, on, label, tip) => `<label class="switch"${tip ? ` title="${esc(tip)}"` : ''}><input type="checkbox" id="${id}" ${on ? 'checked' : ''}><i></i>${label}</label>`;
// balance sheet: show hidden and empty accounts (with their number); cash flow / planning: show empty rows
const alleCtl = (n, bilanz) => swCtl('alle-zeilen', S.all, bilanz ? t('ausgeblendete_n', n ? ` (${n})` : '') : t('leere_zeilen'), bilanz ? t('alle_zeilen_tip_n', n) : t('alle_zeilen_tip'));
const planCtl = () => swCtl('planan', S.plan, t('plan'), t('plan_tip'));
const planOn = () => S.plan || S.tab === 'balance' || S.tab === 'planning';     // in Bilanz und Planung immer mit Plan
function hasRules() { const c = S.CFG || {}; return !!((c.loans || []).length || (c.companies || []).length || (c.account_mirrors || []).length); }
function navBadge(href, text, title) {
  const a = $(`#nav a[href="${href}"]`); if (!a) return;
  let d = a.querySelector('.nbadge');
  if (!text) { if (d) d.remove(); return; }
  if (!d) { d = document.createElement('span'); a.appendChild(d); }
  d.className = 'nbadge' + (text === '•' ? '' : ' n'); d.textContent = text === '•' ? '' : text; d.title = title || '';
}
// what a run does now: reading MoneyMoney, checking the rules, booking n of m
function runStep(st) {
  const s = ((st || {}).service || {}).step || {};
  return s.step === 'buchen' ? t('lauf_buchen', Math.min(s.n + 1, s.date_from), s.date_from) : s.step === 'rules' ? t('lauf_regeln') : t('lauf_lesen');
}
// a spinner drawn anew -- the chat or the status line redrawn many times a second -- turns on from where the one before stood,
// instead of starting over: else it looks stuck while work goes on
const spinKeep = root => { if (!root) return; const d = -(performance.now() % 800) + 'ms'; $$('.spin', root).forEach(s => { s.style.animationDelay = d; }); };
function statusMini() {
  const st = S.STATUS; if (!st) return;
  const mm = mmState(st), m = st.moneymoney || {}, b = st.report || {}, l = st.last_run, ba = m.bank_fetch;
  const zeile = (k, v, title) => `<div class="sm-row"${title ? ' title="' + esc(title) + '"' : ''}><span>${k}</span><b>${v}</b></div>`;
  let h = `<div class="sm-head"><span class="dot ${mm.cls}"></span>${mm.text} ${hq('abgleich')}</div>`;
  if (st.read_only) h += `<div class="sm-ro" title="${esc(t('s_von_unterwegs_nur_ansehen'))}">${ICON.eye}${t('nur_ansehen')}</div>`;          // from another device: what you change is not taken
  if (m.as_of || ba) {
    const n = ba ? ba.back_count : 0;
    const warn = n ? ` <span class="sm-badge" title="${esc(n + (n === 1 ? t('konto') : t('konten')) + t('laenger_nicht_abgerufen') + ba.back.slice(0, 5).map(k => k.name).join(', ') + (n > 5 ? ' …' : '') + t('details_unter_synchronisierung'))}">⚠ ${n}</span>` : '';
    h += `<a href="#settings/moneymoney" class="sm-link" title="${t('details_zur_synchronisierung')}">`
      + zeile(t('banken_mm'), (ba ? esc(fmtZeit(ba.newest)) : '–') + warn, '')
      + zeile(t('mm_kontor'), m.as_of ? esc(fmtZeit(m.as_of)) : '–', '') + '</a>';
  } else h += `<div>${t('noch_keine_daten_aus_moneymoney')}</div>`;
  const al = asLoading();
  if (al) h += `<a href="#settings/assistant" class="sm-link sm-busy" id="sm-ai" title="${esc(asLoadText(al))}"><span class="spin xs"></span>${esc(asLoadShort(al))}</a>`;
  if (st.restart_pending) h += `<div class="sm-busy"><span class="spin xs"></span>${t('version')} ` + esc(st.restart_pending) + ` ${t('wird_geladen')}</div>`;
  else if ((st.service || {}).running) h += `<div class="sm-busy"><span class="spin xs"></span>${runStep(st)}</div>`;
  else if (b.running) h += `<div class="sm-busy"><span class="spin xs"></span>${t('wird_neu_berechnet')}</div>`;
  if (m.gaps) h += `<div><a href="#settings/moneymoney">${t('depotstaende_pruefen')}</a></div>`;
  if (m.problem_text) h += `<div><a href="#settings/moneymoney" title="${esc(m.problem_text.text)}">${t('moneymoney_lief_kontor_konnte_nicht')}</a></div>`;
  $('#status-mini').innerHTML = h; spinKeep($('#status-mini'));
  const sb = $('#sync-btn');
  if (sb) {
    const busy = !!(st.service.running || SYNC.busy);
    sb.classList.toggle('busy', busy); sb.disabled = busy || OFFLINE.mode;
    sb.title = OFFLINE.mode ? t('offline_ansicht_der_mac_ist_2') : t('jetzt_aus_moneymoney_lesen_regeln') + keyHint('sync');
  }
  keysShow();
  // something to do: bookings waiting for approval (count) or a failed run (!), an update (dot) -- in the sidebar and on the app icon
  const waiting = l && l.dry_run && !l.error ? (l.proposals || []).length : 0, notes = l && !l.error && !waiting ? (l.warnings || []).length : 0;
  navBadge('#bookings', l && l.error ? '!' : waiting ? (waiting > 99 ? '99+' : String(waiting)) : notes ? '•' : '', l && l.error ? t('letzter_abgleich_mit_fehler') : waiting ? tn('0_buchungsvorschlaege', waiting) : tn('n_hinweise_auto', notes));
  navBadge('#settings', st.update && st.update.newer ? (upFinds(st.update).length ? '!' : '•') : asNewer() ? '•' : '', st.update && st.update.newer ? (upFinds(st.update).length ? t('upd_braucht_freigabe', st.update.available) : t('update') + st.update.available + t('verfuegbar')) : asNewer() ? t('ki_neues_da') : '');
  const mb = $('#menu-btn'); if (mb) mb.classList.toggle('has-badge', !!(waiting || notes || (l && l.error) || (st.update && st.update.newer) || asNewer()));     // narrow window: the sidebar is closed
  try { if (navigator.setAppBadge) { if (waiting) navigator.setAppBadge(waiting); else navigator.clearAppBadge(); } } catch (e) { /* not supported */ }
  if (!st.storage.encrypted) banner(t('daten_liegen_unverschluesselt_verschlu'), 'err');
  else if ((st.storage.damaged || []).length) {          // a file that did not read at the sign-in was set aside: said until a backup is restored or the note is closed
    const d = st.storage.damaged, b = $('#banner');
    b.innerHTML = esc(t('ablage_beiseite', d.map(x => x.file).join(', '), d.map(x => x.kept).join(', '))) + (st.local ? ` <button class="small secondary" id="dmg-ok">${t('hinweis_ausblenden')}</button>` : '');
    b.className = 'banner err';
  }
}
$('#banner').addEventListener('click', async e => {
  if (e.target.id !== 'dmg-ok') return;
  try { await api('/api/storage/notice', {}); S.STATUS.storage.damaged = []; banner(''); } catch (err) { toast(err.message, 5000); }
});
const BER = {as_of: '', timer: null};
const SYNC = {busy: false};
const MMH = {busy: false};
const DATA_TABS = ['overview', 'balance', 'cashflow', 'planning', 'tax', 'properties', 'transactions', 'categories', 'accounts/', 'accounts/positions', 'bookings'];   // 'accounts/': the accounts list itself
async function pollStatus(all) {
  // Status holen; läuft ein Abgleich oder Berichtsneubau, öfter nachsehen und nach Abschluss die Daten frisch laden
  // all (after "Sync"): the open page is drawn again whatever it is, not only the pages with figures
  S.STATUS = await api('/api/status'); statusMini();
  if (checkVersion(S.STATUS.version)) return;
  if (S.CFG && S.STATUS.webapp && !(S.CFG.ui || {}).webapp) { S.CFG.ui = Object.assign({}, S.CFG.ui, {webapp: true}); webappDraw(); }
  if (S.STATUS.restart_pending) { clearTimeout(BER.timer); BER.timer = setTimeout(() => pollStatus().catch(() => waitAndReload(true)), 3000); return; }
  const b = S.STATUS.report || {};
  clearTimeout(BER.timer);
  if (b.running || (S.STATUS.service || {}).running) { BER.timer = setTimeout(() => pollStatus(all).catch(() => {}), 3000); return; }
  if ((b.as_of || '') !== BER.as_of) {
    BER.as_of = b.as_of || '';
    if (b.error) { toast(t('auswertung_konnte_nicht_aktualisiert_w') + b.error, 6000); return; }
    await loadAll();
    const dr = $('#drawer');
    if (dr.classList.contains('open') && HD.uuid && $('#hq-seg', dr)) { if (!HD.live && !drawerDirty()) { try { await openHistDrawer(HD.uuid); } catch (e) {} } }
    else if ((DATA_TABS.includes(S.tab) || DATA_TABS.includes(S.tab + '/' + S.sub) || all) && !dr.classList.contains('open') && !DIRTY.on) route();
    toastQuiet(t('auswertung_aktualisiert'));
  }
}
function afterRebuild(r) {
  // Antwort einer Änderung, die den Bericht neu baut: sofort Status prüfen (Hintergrund)
  if (r && r.report === 'requested') pollStatus().catch(() => {});
}
function bereichSeg() {
  const seg = $('#bereich-seg'); if (!S.DATA) { seg.classList.add('hidden'); return; }
  const keys = Object.keys(S.DATA.areas || {});
  seg.classList.toggle('hidden', keys.length < 2 || !['overview', 'balance', 'cashflow', 'planning'].includes(S.tab));
  seg.innerHTML = keys.map(k => `<button data-b="${esc(k)}" class="${k === S.area ? 'on' : ''}" title="${esc(BN(k))}">${esc(BN(k))}</button>`).join('');          // (shortened for lack of room: the whole name on hover)
  $$('button', seg).forEach(b => b.addEventListener('click', () => { S.area = b.dataset.b; S.collapsed = {}; bereichSeg(); route(); }));
  const on = $('button.on', seg); if (on && seg.scrollWidth > seg.clientWidth) seg.scrollLeft = on.offsetLeft - (seg.clientWidth - on.offsetWidth) / 2;   // many areas: the bar scrolls sideways
}

// ---------------------------------------------------------------- Spalten, Werte
// month view: this year and the two before (a table with all months of 25 years is slow to draw); the year stepper of the
// toolbar (yearCtl) moves its first year back and forth, the year view shows all years
const MONTH_YEARS = 2;          // the month view: the running year and the one before (‹ › shows earlier ones)
const firstYear = D => S.vonJahr ?? (+String(D.actual_until || D.months[D.months.length - 1] || '').slice(0, 4) - (MONTH_YEARS - 1));
function cols(D, stocks) {
  // stocks (balance sheet): no year columns in the month view – a year column would only repeat December (or the current month)
  D = D || B(); const fy = firstYear(D), plan = planOn() ? (D.plan_months || []) : [];
  const ist = S.mode === 'years' ? D.months : D.months.filter(m => +m.slice(0, 4) >= fy);
  const mcol = (m, isPlan) => ({key: m, label: ML(m), months: [m], plan: isPlan, cur: m === D.actual_until, part: m === D.actual_until, year: false});
  const all = [...ist.map(m => mcol(m, false)), ...plan.map(m => mcol(m, true))];
  const years = {};
  for (const c of all) { const y = c.key.slice(0, 4); (years[y] = years[y] || {months: [], plan: false, ist: false}).months.push(c.key); if (c.plan) years[y].plan = true; else years[y].ist = true; }
  // the running year (actual + plan) is shown faded like the current month (not finished), the plan years faded and hatched
  const ycol = y => ({key: y, label: (S.mode === 'years' ? y : 'Σ ' + y) + (years[y].months.length < 12 ? ' · ' + years[y].months.length + t('mon') : ''), months: years[y].months, plan: years[y].plan && !years[y].ist, mixed: years[y].plan && years[y].ist, part: years[y].months.includes(D.actual_until), cur: false, year: true});
  if (S.mode === 'years') return Object.keys(years).sort().map(ycol);
  if (stocks) return all.map((c, i) => Object.assign(c, {jan: i > 0 && c.key.endsWith('-01')}));
  const out = [];
  for (const c of all) { out.push(c); if (c.key.endsWith('-12') || c.key === all[all.length - 1].key) out.push(ycol(c.key.slice(0, 4))); }
  return out;
}
function defl(m) {
  const D = B(); if (!S.real || S.tab !== 'planning' || !D || !D.plan_months || !D.plan_months.includes(m)) return 1;
  const i = D.plan_months.indexOf(m) + 1, infl = +((D.plan || {}).inflation_percent_pa || 0);
  return Math.pow(1 + infl / 100, -i / 12);
}
const sumOver = (vals, months) => months.reduce((a, m) => a + (vals[m] ?? 0) * defl(m), 0);
const lastOf = (vals, months) => { for (let i = months.length - 1; i >= 0; i--) if (vals[months[i]] != null) return vals[months[i]] * defl(months[i]); return null; };
// a cell's classes; a year's sum among months is marked (only years: nothing to tell apart)
function cls(v, c) { let s = ''; if (c.plan) s += ' plan'; else if (c.part) s += ' part'; if (c.cur && S.mode !== 'years') s += ' cur'; if (c.year && S.mode !== 'years') s += ' year'; if (c.jan) s += ' ystart'; if (v == null || Math.abs(v) < 0.005) s += ' zero'; else s += v < 0 ? ' neg' : ' pos'; return s; }
const cells = (C, fn) => C.map(c => { const v = fn(c); return `<td class="${cls(v, c)}">${FC(v)}</td>`; }).join('');
const isCurCol = c => { const D = B(), ib = (D && D.actual_until) || ''; return c.year ? c.key === ib.slice(0, 4) && S.mode === 'years' : c.key === ib; };
const thead = (first, C) => `<thead><tr><th>${first}</th>${C.map(c => `<th data-key="${c.key}" class="${c.year && S.mode !== 'years' ? 'year' : ''}${c.jan ? ' ystart' : ''}${c.plan ? ' plan' : ''}"${isCurCol(c) ? ' data-cur="1"' : ''} title="${c.plan ? t('plan') : c.mixed ? t('ist_plan') : t('ist')}">${c.label}</th>`).join('')}</tr></thead>`;
const noData = `<div class="card"><div class="v s">${t('noch_keine_daten')}</div><div class="d">${t('unter_einrichtung_den_bericht_erstelle')}</div></div>`;

// ---------------------------------------------------------------- Diagramme (SVG)
function niceTicks(min, max, n, least = 0) {
  // about n round steps (1, 2, 5 × 10^k); with fewer than "least" lines a finer round step (also 2.5: 0 / 25 / 50 / 75 / 100 Tsd.)
  const span = (max - min) || 1, raw = span / n, p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p, step = (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p;
  const make = st => { const o = []; for (let k = Math.ceil(min / st - 1e-9); k * st <= max + st * 1e-9; k++) { const v = k * st; o.push(Math.abs(v) < st * 1e-6 ? 0 : v); } return o; };   // no "-0"
  let out = make(step);
  if (least && out.length < least) {
    const finer = []; for (const e of [1, 0.1]) for (const x of [10, 5, 2.5, 2, 1]) if (x * p * e < step * (1 - 1e-9)) finer.push(x * p * e);
    for (const st of finer.sort((a, b) => b - a)) { const o = make(st); if (o.length >= least) { out = o; break; } }
  }
  return out;
}

// What is open -- for the overview (a card beside the monthly chart) and the assistant (on an empty conversation, each with what it can do
// about it): [kind, text, page, what the assistant may be asked to do (or '')]. Kontor's own figures; no model needed.
async function openItems(D) {
  const m = D.months, cur = m[m.length - 1], yr = cur.slice(0, 4);
  const [ok, ob] = await Promise.all([api(`/api/transactions?year=${yr}&uncategorized=1&limit=1&entity=${encodeURIComponent(S.area)}`).catch(() => ({})),
    api(`/api/transactions?year=${yr}&without_receipt=1&direction=out&limit=1&entity=${encodeURIComponent(S.area)}`).catch(() => ({}))]);
  const lastRun = S.STATUS.last_run, items = [];
  if (lastRun && lastRun.dry_run && lastRun.proposals && lastRun.proposals.length) items.push(['warn', tn('0_buchungsvorschlaege', lastRun.proposals.length), '#bookings', 'bookings']);
  if (ok.hits) items.push(['warn', tn('n_umsaetze', ok.hits) + ' ' + yr + t('ohne_kategorie_zuordnen'), '#categories', 'categorize']);
  if ((S.DATA.accounts_new || []).length) items.push(['warn', nKonten(S.DATA.accounts_new.length) + t('ohne_bestaetigte_zuordnung_bereich_pos'), '#accounts', '']);
  if (ob.hits) items.push(['neutral', tn('n_ausgaben', ob.hits) + ' ' + yr + t('ohne_beleg'), '#transactions?no_receipt=1', 'receipts']);
  const ue = (D.cashflow.reconciliation || {})[cur]; if (ue && Math.abs(ue.unexplained) > 1) items.push(['warn', t('unerklaerte_vermoegensaenderung_im_lau') + F(ue.unexplained) + t('pruefzeile'), '#cashflow', 'unexplained']);
  for (const w of (D.warnings || []).slice(0, 3)) items.push(['warn', w, '#bookings', '']);
  if (S.STATUS.update && S.STATUS.update.newer) items.push(upFinds(S.STATUS.update).length ? ['warn', t('upd_braucht_freigabe', S.STATUS.update.available), '#settings/updates', ''] : ['info', t('update') + S.STATUS.update.available + t('verfuegbar'), '#settings/updates', '']);
  if (asNewer()) items.push(['info', t('ki_neues_da'), '#settings/assistant', '']);
  return items;
}

// ---------------------------------------------------------------- Übersicht
// The overview: the most important charts and key figures on one screen, reduced to what they say at a glance -- no tables, no plan, no
// comparisons. A click on a chart opens its place in Bilanz or Cashflow. Above them only what is to do (if anything).
async function vUebersicht() {
  const D = B();
  if (!D) return S.setup || !S.DATA ? `<div class="card"><div class="v s">${t('willkommen_bei_kontor')}</div><div class="d">${t('die_einrichtung_fuehrt_dich_durch')}</div><div class="actions"><a href="#setup"><button>${t('einrichtung_oeffnen')}</button></a></div></div>` : noData;
  const m = D.months, cur = m[m.length - 1], yr = cur.slice(0, 4);
  const items = await openItems(D);
  // beside the monthly chart (lower right): what is open, each line leads where it is done -- the list scrolls if long
  const todo = items.length ? `<div class="card ov-todo" data-ov="todo" data-ex="overview.todo"><div class="ov-head"><b>${t('ov_offen')}</b><span class="ov-fig"><span class="ov-s">${items.length}</span></span></div><div class="ov-todo-l">${items.map(([k, x, href]) => `<a href="${href}" class="ov-todo-i ${k}"><i class="ov-todo-d"></i><span>${esc(x)}</span><span class="ov-todo-c" aria-hidden="true">›</span></a>`).join('')}</div></div>` : '';
  // ex: where the card and its head figure stand in Kontor's description of the page (docs/ui/overview.md)
  const card = (id, title, go, ex, foot = '') => `<div class="card link ov-card" data-ov="${id}" data-ovgo="${go}" ${ex[0]} role="link" tabindex="0" aria-label="${esc(title)}"><div class="ov-head"><b>${esc(title)}</b><span class="ov-fig" id="ov-fig-${id}" ${ex[1] || ''}></span></div><div class="ov-plot" id="ov-${id}"></div>${foot}</div>`;
  const unk = cfDone(D).slice(-12).some(k => Math.abs(((D.cashflow.sums || {})[k] || {}).unclear || 0) >= 0.5);          // grey bars drawn: named too
  const key = [['ein', t('einnahmen')], ['aus', t('ausgaben')], ['inv', t('cf_investitionen')], ['fin', t('cf_finanzierung')]].concat(unk ? [['unk', t('cf_unklar')]] : []).map(([c, l]) => `<span><i class="sw ${c === 'ein' ? 'in' : c === 'aus' ? 'out' : c}"></i>${esc(l)}</span>`).join('')
    + `<span><i class="sw net"></i>${esc(t('zahlungsfluss_gesamt_veraenderung_liqu'))}</span>`;
  return `<div class="ov-grid${todo ? '' : ' no-todo'}"><div class="cf-tip hidden" id="cf-tip" role="tooltip"></div>${card('nw', t('nettovermoegen'), 'nw', ['data-ex="overview.nw"', 'data-ex="overview.nw.head"'])}`
    + card('comp', t('vermoegensstruktur'), 'table', ['data-ex="overview.comp"', 'data-ex="overview.comp.head"']) + card('wealth', t('cf_verm_bruecke'), 'wealth', ['data-ex="overview.wealth"', 'data-ex="overview.wealth.head"'])
    + card('months', t('cf_je_monat_t'), 'months', ['data-ex="overview.months"', 'data-ex="overview.months.head"'], `<div class="ov-key">${key}</div>`) + card('build', t('ov_aufbau'), 'table', ['data-ex="overview.build"']) + `${todo}</div>`;
}
// where a chart leads: the balance sheet's chart or table, the cash flow's months or net worth bridge (the last 12 months, as here)
const OV_GO = {nw: ['#balance', '#bch'], table: ['#balance', '.wrap.bil-tbl'], ekq: ['#balance', 'tr.ekq'], months: ['#cashflow', '[data-cfid="months"]'], wealth: ['#cashflow', '[data-cfid="wealth"]'],
  cftable: ['#cashflow', 'table.cf-tbl:not(.cf-names)']};
function ovGo(k) {
  const [hash, sel] = OV_GO[k] || ['#overview', null];
  if (k === 'ekq') S.posOpen._kennzahlen = true;          // the equity ratio: under net worth, opened
  if (hash === '#cashflow') { S.cfZeit = '12m'; S.cfBrZoom = S.cfWbZoom = null; }
  S.ovGo = sel; go(hash);
}
function ovArrive(main) {          // after the page is drawn: its chart in view
  const sel = S.ovGo; S.ovGo = null; if (!sel) return;
  const el = $(sel, main); if (!el) return;
  setTimeout(() => { pageTo(el.getBoundingClientRect().top - pageTop() + pageY() - 12); el.classList.add('ov-hit'); setTimeout(() => el.classList.remove('ov-hit'), 1600); }, 60);
}
function bindOverview(main) {
  const grid = $('.ov-grid', main); if (!grid) return;
  // hovering a chart: the figures of the month, tile or step under the pointer, as in the cash flow's charts
  const hide = () => { const b = $('#cf-tip'); if (b) b.classList.add('hidden'); };
  grid.addEventListener('pointerover', e => { const el = e.target.closest('[data-cftip]'); if (el) cfShowTip(el); });
  grid.addEventListener('pointerout', e => { const el = e.target.closest('[data-cftip]'); if (el && !(e.relatedTarget && el.contains(e.relatedTarget))) hide(); });
  $$('.ov-card', main).forEach(c => { c.addEventListener('click', e => { if (!e.target.closest('a, button')) ovGo(e.target.closest('[data-ovgo]').dataset.ovgo); });          // a key figure: its own place
    c.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ovGo(c.dataset.ovgo); } }); });
  ovDraw();
}
function ovDraw() {
  const D = B(), grid = $('#main .ov-grid'); if (!D || !grid) return;
  // one screen in three columns: the grid takes the height left below it, not more than a calm size (a narrower window: the
  // cards of their own height, in two columns or stacked)
  const wide = window.innerWidth > 1100;
  grid.style.height = wide ? Math.min(660, Math.max(460, window.innerHeight - grid.getBoundingClientRect().top - pageY() - 24)) + 'px' : '';
  // the figure first (it can take a second line on a narrow screen), then the chart in the room left; the hover texts anew
  CF.tips = []; const tipBox = $('#cf-tip'); if (tipBox) tipBox.classList.add('hidden');
  const put = (id, fn) => { const el = $('#ov-' + id); if (!el) return; const f = $('#ov-fig-' + id); el.innerHTML = '';
    if (f) f.innerHTML = fn(D, 320, 200).fig || '';
    const r = el.getBoundingClientRect(), out = fn(D, Math.max(240, Math.floor(r.width)), Math.max(130, Math.floor(r.height))); el.innerHTML = out.svg; };
  put('nw', ovNetWorth); put('comp', ovComposition); put('months', ovMonths); put('wealth', ovWealth); put('build', ovBuild);
}
const ovEmpty = txt => ({svg: `<div class="ov-empty muted small">${esc(txt)}</div>`, fig: ''});
// 5. Wealth building: per building block -- participations, property (net of its loans, where they are linked to it), cash and
// investments, the other debts -- what it is worth and how it changed over the twelve months of the bridge: money that went in or
// out (contributions, purchases, saving, repayment) and the change in value without any money moving. A block with a balance
// only carried backwards (no known one at the start): its change unknown, not estimated
function ovBuild(D) {
  const ms = cfDone(D).slice(-13); if (ms.length < 2) return ovEmpty(t('noch_zu_wenig_monate'));
  const b = ms[0], k = ms[ms.length - 1], span = ms.slice(1);
  const accs = D.balance.rows.filter(r => !r.group && ROLE[r.role] && r.role !== 'contingent' && r.role !== 'ignore');
  const at = (r, m) => (r.amounts || {})[m] || 0, known = r => !r.projected_before || b >= r.projected_before;
  const linked = new Set(((S.CFG || {}).real_estate || []).flatMap(im => Object.values(im.loan_accounts || {}).filter(Boolean).map(x => String(x).split('|')[0].trim())));
  const ofImmo = accs.some(r => r.role === 'liabilities' && linked.has(r.id)) && accs.some(r => r.role === 'real_estate');
  const blockOf = r => r.role === 'participations' ? 'bet' : r.role === 'real_estate' || (ofImmo && r.role === 'liabilities' && linked.has(r.id)) ? 'immo' : r.role === 'liabilities' ? 'debt' : 'liq';
  const wert = {};
  for (const z of ((D.cashflow.sections || []).find(sk => sk.name === 'valuation') || {rows: []}).rows) if (z.account) wert[z.account] = (wert[z.account] || 0) + span.reduce((a, m) => a + ((z.amounts || {})[m] || 0), 0);
  const B0 = {bet: [t('beteiligungen'), 'var(--c-bet)'], immo: [t(ofImmo ? 'ov_b_immo_netto' : 'immobilien'), 'var(--c-immo)'], liq: [t('ov_b_liq'), 'var(--c-liq)'],
    debt: [t(ofImmo ? 'ov_b_debt_rest' : 'ov_k_schulden'), 'var(--c-verb)']};
  const blocks = Object.keys(B0).map(id => { const rs = accs.filter(r => blockOf(r) === id), now = rs.reduce((a, r) => a + at(r, k), 0);
    const chg = rs.reduce((a, r) => a + at(r, k) - at(r, b), 0), w = rs.reduce((a, r) => a + (wert[r.id] || 0), 0);
    return {id, rs, now, chg, w, flow: chg - w, unk: rs.filter(r => !known(r) && (Math.abs(at(r, k)) >= 0.5 || Math.abs(at(r, b)) >= 0.5))}; })
    .filter(x => x.rs.some(r => Math.abs(at(r, k)) >= 0.5 || Math.abs(at(r, b)) >= 0.5));
  if (!blocks.length) return ovEmpty(t('noch_keine_bestaende'));
  const scale = Math.max(1, ...blocks.filter(x => !x.unk.length).map(x => Math.abs(x.chg)));
  const sg = v => (v > 0.5 ? '+' : v < -0.5 ? '' : '±') + F0(v) + ' €', per = `${ML(span[0])} – ${ML(k)}`;
  const EXB = {bet: 'data-ex="overview.build.bet"', immo: 'data-ex="overview.build.immo"', liq: 'data-ex="overview.build.liq"', debt: 'data-ex="overview.build.debt"'};          // docs/ui/overview.md
  const rows = blocks.map(x => {
    const [name, color] = B0[x.id], unk = x.unk.length > 0, w = Math.min(50, Math.abs(x.chg) / scale * 50);
    const sub = x.id === 'debt' ? (unk || Math.abs(x.chg) < 0.5 ? '' : t(x.chg > 0 ? 'ov_b_getilgt' : 'ov_b_neu', F0(Math.abs(x.chg))))
      : unk ? '' : `${t('ov_b_fluss')} ${sg(x.flow)} · ${t('ov_b_wert')} ${sg(x.w)}`;
    // the tooltip: each account now and its change, the two parts, what is not known
    const lines = x.rs.filter(r => Math.abs(at(r, k)) >= 0.5 || Math.abs(at(r, b)) >= 0.5).sort((p, q) => Math.abs(at(q, k)) - Math.abs(at(p, k)));
    const tip = cfTip(`<div class="cf-tip-h">${esc(name)} · ${esc(per)}</div>`
      + lines.slice(0, 8).map(r => cfTipRow('none', r.name, F0(at(r, k)) + ' €', known(r) ? (Math.abs(at(r, k) - at(r, b)) >= 0.5 ? {cls: '', txt: esc(sg(at(r, k) - at(r, b)))} : null) : {cls: '', txt: esc(t('vor_0_unbekannt', ML(r.projected_before)))})).join('')
      + (lines.length > 8 ? `<div class="cf-tip-note">${esc(t('cf_uebrige', lines.length - 8))}</div>` : '')
      + (unk ? '' : `<div class="cf-tip-res">${x.id === 'debt' ? '' : cfTipRow('none', t('ov_b_fluss'), sg(x.flow)) + cfTipRow('none', t('ov_b_wert'), sg(x.w))}${cfTipTot(t('ov_b_veraenderung'), sg(x.chg))}</div>`)
      + `<div class="cf-tip-note">${esc(unk ? t('ov_b_unbekannt_tip') : x.id === 'debt' ? t('ov_b_debt_tip') : t('ov_b_fluss_tip'))}</div>`);
    return `<div class="ov-bs-r" ${EXB[x.id]} data-cftip="${tip}"><span class="ov-bs-n"><i style="background:${color}"></i>${esc(name)}</span>`
      + `<span class="ov-bs-d${unk ? ' muted' : Math.abs(x.chg) < 0.5 ? '' : x.chg > 0 ? ' pos' : ' neg'}">${esc(unk ? t('ov_b_unbekannt') : sg(x.chg))}</span>`
      + `<span class="ov-bs-b">${unk ? '' : `<i class="${x.chg >= 0 ? 'pos' : 'neg'}" style="${x.chg >= 0 ? 'left:50%' : `left:${(50 - w).toFixed(1)}%`};width:${w.toFixed(1)}%"></i>`}</span>`
      + `<span class="ov-bs-s">${esc(F0(x.now))} €${sub ? ' · ' + esc(sub) : ''}</span></div>`;
  }).join('');
  return {svg: `<div class="ov-bs">${rows}</div>`, fig: `<span class="ov-s">${esc(per)}</span>`};
}
const ovDelta = v => v == null ? '' : `<span class="ov-d ${v >= 0 ? 'pos' : 'neg'}">${v >= 0 ? '+' : ''}${F0(v)} €</span>`;
// 1. Net worth: the last twelve closed months as a line over a quiet area; the figure now and its change over them
function ovNetWorth(D, W, H) {
  const nw = D.balance.net_worth || {}, ms = cfDone(D).filter(k => nw[k] != null).slice(-13);          // twelve closed months back from the last one
  if (ms.length < 2) return ovEmpty(t('noch_zu_wenig_monate'));
  const v = ms.map(k => nw[k]), last = v[v.length - 1], yago = ms.length > 12 ? v[v.length - 13] : null;
  const P = {l: 46, r: 8, t: 8, b: 20}, ticks = niceTicks(Math.min(...v), Math.max(...v), 3, 3), lo = Math.min(ticks[0], ...v), hi = Math.max(ticks[ticks.length - 1], ...v);
  const x = i => P.l + i / (ms.length - 1) * (W - P.l - P.r), y = val => P.t + (hi - val) / ((hi - lo) || 1) * (H - P.t - P.b), ref = Math.max(Math.abs(lo), Math.abs(hi));
  const pts = v.map((val, i) => `${x(i).toFixed(1)},${y(val).toFixed(1)}`).join(' ');
  let g = ticks.map(tk => `<line class="cf-grid-l${Math.abs(tk) < 1e-9 ? ' zero' : ''}" x1="${P.l}" x2="${W - P.r}" y1="${y(tk).toFixed(1)}" y2="${y(tk).toFixed(1)}"/><text class="cf-tick" x="${P.l - 6}" y="${(y(tk) + 4).toFixed(1)}" text-anchor="end">${esc(Fk(tk, false, ref))}</text>`).join('');
  g += `<polygon class="ov-area" points="${x(0).toFixed(1)},${y(Math.max(lo, 0)).toFixed(1)} ${pts} ${x(ms.length - 1).toFixed(1)},${y(Math.max(lo, 0)).toFixed(1)}"/><polyline class="ov-line" points="${pts}"/>`;
  g += `<circle class="ov-dot" cx="${x(ms.length - 1).toFixed(1)}" cy="${y(last).toFixed(1)}" r="4"/>`;
  // each month: a guide and its point under the pointer, the figure and its changes in the tooltip
  const sw = (W - P.l - P.r) / Math.max(1, ms.length - 1), sgn = d => (d > 0.5 ? '+' : '') + F0(d) + ' €';
  ms.forEach((k, i) => { const tip = cfTip(`<div class="cf-tip-h">${esc(MLL(k))}</div>` + cfTipRow('sw nwc', t('nettovermoegen'), F0(v[i]) + ' €')
      + (i ? cfTipRow('none', t('ov_ggue_vormonat'), sgn(v[i] - v[i - 1])) : '') + (i >= 12 ? cfTipRow('none', t('ov_ggue_vorjahr'), sgn(v[i] - v[i - 12])) : ''));
    const x0 = Math.max(P.l, x(i) - sw / 2), x1 = Math.min(W - P.r, x(i) + sw / 2);
    g += `<g class="ov-pt" data-cftip="${tip}"><rect class="cf-hit" x="${x0.toFixed(1)}" y="0" width="${(x1 - x0).toFixed(1)}" height="${H - P.b}"/>`
      + `<line class="ov-hl" x1="${x(i).toFixed(1)}" x2="${x(i).toFixed(1)}" y1="${P.t}" y2="${H - P.b}"/><circle class="ov-hd" cx="${x(i).toFixed(1)}" cy="${y(v[i]).toFixed(1)}" r="4"/></g>`; });
  for (const i of [0, Math.floor((ms.length - 1) / 2), ms.length - 1]) g += `<text class="cf-tick${i === ms.length - 1 ? ' end' : ''}" x="${x(i).toFixed(1)}" y="${H - 4}" text-anchor="${i === 0 ? 'start' : i === ms.length - 1 ? 'end' : 'middle'}">${esc(ML(ms[i]))}</text>`;
  return {svg: `<svg class="cf-svg ov-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(t('nettovermoegen'))}">${g}</svg>`,
    fig: `<span class="ov-v">${F0(last)} €</span><span class="ov-s">${esc(ML(ms[ms.length - 1]))}${yago != null ? ` · ${t('ov_12_monate')} ${ovDelta(last - yago)}` : ''}</span>`};
}
// a change in percent, as short as it can be: one decimal under 100 %, whole numbers above, thousands abbreviated
const ovPct = d => { if (d == null || !isFinite(d)) return ''; const a = Math.abs(d), s = d > 0.05 ? '+' : d < -0.05 ? '−' : '±';
  return s + (a >= 999.5 ? (a / 1000).toLocaleString(LOCALE, {maximumFractionDigits: a >= 9950 ? 0 : 1}) + t('tsd_kurz') : a >= 99.95 ? Math.round(a).toLocaleString(LOCALE) : a.toLocaleString(LOCALE, {minimumFractionDigits: 1, maximumFractionDigits: 1})) + ' %'; };
// 2. What the net worth consists of now, as a balance sheet: the assets as a treemap (each position by its size, with its share),
// beside them in one column what pays for them -- equity and debts, on the same scale (so the equity ratio shows at a glance)
function treemap(vals, x, y, w, h) {          // squarified: [{i, x, y, w, h}] for values sorted from the largest
  const out = [], total = vals.reduce((a, v) => a + v, 0); if (total <= 0 || w <= 0 || h <= 0) return out;
  let items = vals.map((v, i) => ({i, a: v * w * h / total}));
  const worst = (row, side) => { const sum = row.reduce((a, e) => a + e.a, 0), mx = Math.max(...row.map(e => e.a)), mn = Math.min(...row.map(e => e.a));
    return Math.max(side * side * mx / (sum * sum), sum * sum / (side * side * mn)); };
  while (items.length) {
    const side = Math.min(w, h), row = [items[0]]; let rest = items.slice(1);
    while (rest.length && worst([...row, rest[0]], side) <= worst(row, side)) row.push(rest.shift());
    const sum = row.reduce((a, e) => a + e.a, 0);
    if (w >= h) { const rw = sum / h; let yy = y; for (const e of row) { const eh = e.a / rw; out.push({i: e.i, x, y: yy, w: rw, h: eh}); yy += eh; } x += rw; w -= rw; }
    else { const rh = sum / w; let xx = x; for (const e of row) { const ew = e.a / rh; out.push({i: e.i, x: xx, y, w: ew, h: rh}); xx += ew; } y += rh; h -= rh; }
    items = rest;
  }
  return out;
}
function ovComposition(D, W, H) {
  const done = cfDone(D), k = done[done.length - 1] || (D.months || [])[D.months.length - 1];          // the last closed month
  const k0 = (() => { const [y, m] = k.split('-').map(Number); return `${y - 1}-${String(m).padStart(2, '0')}`; })();          // a year before
  const pos = D.balance.rows.filter(r => r.group && ROLE[r.role] && r.role !== 'contingent' && r.role !== 'ignore');
  const val = (r, m = k) => (r.amounts || {})[m] || 0, assets = pos.filter(r => r.role !== 'liabilities' && val(r) > 0.5).sort((a, b) => val(b) - val(a));
  const has0 = pos.some(r => (r.amounts || {})[k0] != null);
  // debts account by account (the tiles at the right): a loan account in credit (overpaid) is no debt -- it stands with the assets
  const liab = D.balance.rows.filter(r => !r.group && r.role === 'liabilities'), sumOf = (rs, m) => rs.reduce((a, r) => a + val(r, m), 0);
  const debtsAt = m => -sumOf(liab.filter(r => val(r, m) < -0.5), m) - sumOf(pos.filter(r => r.role !== 'liabilities' && val(r, m) < -0.5), m);
  const sumAt = m => sumOf(pos.filter(r => r.role !== 'liabilities' && val(r, m) > 0.5), m) + sumOf(liab.filter(r => val(r, m) > 0.5), m);
  const debts = debtsAt(k), sumA = sumAt(k), equity = sumA - debts;
  if (sumA < 0.5 && debts < 0.5) return ovEmpty(t('noch_keine_bestaende'));
  const total = Math.max(sumA, debts);
  const yoy = (now, then) => !has0 || then == null || Math.abs(then) < 0.5 ? '' : ovPct((now - then) / Math.abs(then) * 100);          // nothing to compare (new, unknown): nothing
  // a year before only where it is known: an account whose first known balance is later carries that value backwards -- no
  // change can be read from it (unknown, not 0 %)
  const accsOf = r => r.group ? D.balance.rows.filter(x => !x.group && x.role === r.role) : [r];
  const known0 = r => accsOf(r).every(a => !a.projected_before || k0 >= a.projected_before);
  const then = (r, sign = 1) => known0(r) ? sign * val(r, k0) : null;
  // a tile: a quiet tint of the position's colour with a solid edge, its name and figures inside where they fit (all in the hover)
  // a tile: a quiet tint of the position's colour with a solid edge; its name, amount and change against a year before inside
  // where they fit (all of it, with its share of the total, in the hover). good: a rise is good (assets) or bad (debts)
  const tile = (x, y, w, h, color, name, v, chg, good = true, v0 = null) => {
    x += 1; y += 1; w -= 2; h -= 2; if (w < 1 || h < 1) return '';
    const room = n => Math.floor((w - 14) / n), cut = (txt, n) => txt.length > room(n) ? txt.slice(0, Math.max(1, room(n) - 1)) + '…' : txt;
    const share = FN(Math.abs(v) / (total || 1) * 100, 0) + ' %', cls = !chg || chg.startsWith('±') ? '' : (chg.startsWith('+') === good ? ' pos' : ' neg');
    const tip = cfTip(`<div class="cf-tip-h">${esc(name)}</div>` + cfTipRow('none', ML(k), F0(v) + ' €') + (has0 && name !== t('ov_fehlbetrag') ? cfTipRow('none', ML(k0), v0 == null ? esc(t('unbekannt')) : F0(v0) + ' €', chg ? {cls: cls.trim(), txt: esc(chg)} : null) : '')
      + `<div class="cf-tip-note">${esc(t('ov_anteil', share))}</div>`);
    let g = `<g class="ov-tile" data-cftip="${tip}"><rect class="ov-tm" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" rx="4" style="--c:${color}"/>`
      + `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="3" height="${h.toFixed(1)}" rx="1.5" style="fill:${color}"/>`;
    if (w >= 46 && h >= 20) {
      g += `<text class="ov-tm-n" x="${(x + 9).toFixed(1)}" y="${(y + 15).toFixed(1)}">${esc(cut(name, 6.8))}</text>`;
      if (h >= 36) g += `<text class="ov-tm-v" x="${(x + 9).toFixed(1)}" y="${(y + 30).toFixed(1)}">${esc(cut(Fs(v, 0) + ' €', 6.2))}</text>`;
      if (h >= 52 && chg) g += `<text class="ov-tm-v ov-tm-c${cls}" x="${(x + 9).toFixed(1)}" y="${(y + 45).toFixed(1)}">${esc(cut(chg, 6.2))}</text>`;
    }
    return g + '</g>';
  };
  // two halves of the same size, as the totals are the same: the assets at the left, what stands against them (net worth and
  // each debt) at the right; debts above the assets: the gap among the assets. The figure: the assets (the left half) -- no
  // balance sheet total: what is kept on no account (stock, payment terms, provisions) Kontor does not know
  const cap = 16, half = (W - 10) / 2, x2 = half + 10, ph = H - cap;
  const debtRows = D.balance.rows.filter(r => !r.group && r.role === 'liabilities' && val(r) < -0.5).sort((a, b) => val(a) - val(b));
  const eq0 = pos.every(known0) ? sumAt(k0) - debtsAt(k0) : null;          // each entry: colour, name, amount, change, a rise is good, a year before
  const passiva = [...(equity > 0.5 ? [['var(--c-nw)', t('nettovermoegen'), equity, yoy(equity, eq0), true, eq0]] : []),
    ...debtRows.map(r => ['var(--c-verb)', r.name, -val(r), yoy(-val(r), then(r, -1)), false, then(r, -1)])];
  // a position below 0 that is no debt (an overdrawn account, a participation worth less than nothing): with its own name
  for (const r of pos.filter(r => r.role !== 'liabilities' && val(r) < -0.5)) passiva.push(['var(--c-verb)', r.name, -val(r), yoy(-val(r), then(r, -1)), false, then(r, -1)]);
  const aktiva = assets.map(r => [ROLE[r.role][1], r.name, val(r), yoy(val(r), then(r)), true, then(r)])
    .concat(liab.filter(r => val(r) > 0.5).map(r => [ROLE.liabilities[1], r.name, val(r), yoy(val(r), then(r)), true, then(r)]));
  if (equity < -0.5) aktiva.push(['var(--c-neutral)', t('ov_fehlbetrag'), -equity, '', true, null]);
  const side = (list, x0) => treemap(list.map(e => e[2]), x0, cap, half, ph).map(q => { const [c, n, v, chg, good, v0] = list[q.i]; return tile(q.x, q.y, q.w, q.h, c, n, v, chg, good, v0); }).join('');
  const g = `<g data-ex="overview.comp.assets"><text class="ov-cap" x="2" y="11">${esc(t('ov_aktiva'))}</text>${side(aktiva, 0)}</g>`
    + `<g data-ex="overview.comp.funding"><text class="ov-cap" x="${(x2 + 2).toFixed(1)}" y="11">${esc(t('ov_passiva'))}</text>${side(passiva, x2)}</g>`;
  return {svg: `<svg class="cf-svg ov-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(t('vermoegensstruktur'))}">${g}</svg>`,
    fig: `<span class="ov-v">${F0(sumA)} €</span><span class="ov-s" title="${esc(t('ov_brutto_tip'))}">${esc(t('ov_brutto_am', ML(k)))}${has0 ? ' · ' + esc(t('ov_vergleich', ML(k0))) : ''}</span>`};          // the period: that month, against a year before
}
// 3. The last twelve closed months: money in up, money out down (income, expenses, investing, financing), the change in cash as
// a short stroke -- the upper part of the cash flow's monthly chart; a few far larger months are cut (marked) so the rest stays readable
function ovMonths(D, W, H) {
  const ms = cfDone(D).slice(-12); if (!ms.length) return ovEmpty(t('cf_keine_zahlungen'));
  const parts = [['income', 'ein'], ['expenses', 'aus'], ['investing', 'inv'], ['financing', 'fin'], ['unclear', 'unk']];
  const bs = ms.map(k => { const s = (D.cashflow.sums || {})[k] || {}, o = {k, net: s.cash_change || 0};
    for (const [n, c] of parts) o[c] = s[n] || 0; o.up = parts.reduce((a, [, c]) => a + Math.max(0, o[c]), 0); o.dn = parts.reduce((a, [, c]) => a + Math.min(0, o[c]), 0); return o; });
  let hi = Math.max(0, ...bs.map(b => b.up)), lo = Math.min(0, ...bs.map(b => b.dn));
  if (hi - lo < 0.5) return ovEmpty(t('cf_keine_zahlungen'));
  const ext = bs.flatMap(b => [b.up, -b.dn]).filter(v => v > 0.5).sort((p, q) => p - q), q = ext[Math.floor((ext.length - 1) * 0.75)] || 0;
  const cut = ext.length >= 6 && ext[ext.length - 1] > 3 * q && q > 0 ? Math.max(...ext.filter(v => v <= 3 * q)) * 1.12 : null;
  if (cut) { hi = Math.min(hi, cut); lo = Math.max(lo, -cut); }
  let ticks = niceTicks(lo, hi, 3, 3); const step = ticks.length > 1 ? ticks[1] - ticks[0] : hi - lo;
  if (!cut) { if (ticks[0] > lo + step * 1e-6) ticks.unshift(ticks[0] - step); if (ticks[ticks.length - 1] < hi - step * 1e-6) ticks.push(ticks[ticks.length - 1] + step); lo = ticks[0]; hi = ticks[ticks.length - 1]; }
  else ticks = ticks.filter(v => v >= lo - 1e-6 && v <= hi + 1e-6);
  const P = {l: 46, r: 6, t: 8, b: 20}, ref = Math.max(Math.abs(lo), Math.abs(hi));
  const y = v => P.t + (hi - Math.max(lo, Math.min(hi, v))) / ((hi - lo) || 1) * (H - P.t - P.b), slot = (W - P.l - P.r) / bs.length, bw = Math.max(3, Math.min(22, slot - 6));
  let g = ticks.map(tk => `<line class="cf-grid-l${Math.abs(tk) < 1e-9 ? ' zero' : ''}" x1="${P.l}" x2="${W - P.r}" y1="${y(tk).toFixed(1)}" y2="${y(tk).toFixed(1)}"/><text class="cf-tick" x="${P.l - 6}" y="${(y(tk) + 4).toFixed(1)}" text-anchor="end">${esc(Fk(tk, false, ref))}</text>`).join('');
  g += `<line class="cf-grid-l zero" x1="${P.l}" x2="${W - P.r}" y1="${y(0).toFixed(1)}" y2="${y(0).toFixed(1)}"/>`;
  bs.forEach((b, i) => {
    const x0 = P.l + slot * i + (slot - bw) / 2; let up = 0, dn = 0;
    for (const [, c] of parts) { const v = b[c]; if (Math.abs(v) < 0.5) continue;
      const a = v > 0 ? up : dn, e = a + v; if (v > 0) up = e; else dn = e;
      const y1 = y(Math.max(a, e)), y2 = y(Math.min(a, e)); if (y2 - y1 < 0.5) continue;
      g += `<rect class="cf-col ${c}" x="${x0.toFixed(1)}" y="${y1.toFixed(1)}" width="${bw.toFixed(1)}" height="${(y2 - y1).toFixed(1)}"/>`; }
    if ((cut && b.up > hi + 0.5) || (cut && b.dn < lo - 0.5)) { const yc = b.up > hi + 0.5 ? P.t + 4 : H - P.b - 4;
      g += `<path class="cf-break" d="M${(x0 - 2).toFixed(1)},${(yc + 3).toFixed(1)}L${(x0 + bw + 2).toFixed(1)},${(yc - 3).toFixed(1)}"/>`; }
    if (Math.abs(b.net) >= 0.5 && b.net >= lo - 0.5 && b.net <= hi + 0.5 && Math.abs(y(b.net) - y(0)) >= 4) g += `<line class="cf-net" x1="${(x0 - 3).toFixed(1)}" x2="${(x0 + bw + 3).toFixed(1)}" y1="${y(b.net).toFixed(1)}" y2="${y(b.net).toFixed(1)}"/>`;
    if (i === 0 || i === bs.length - 1 || (bs.length > 6 && i === Math.floor(bs.length / 2))) g += `<text class="cf-tick${i === bs.length - 1 ? ' end' : ''}" x="${(x0 + bw / 2).toFixed(1)}" y="${H - 4}" text-anchor="middle">${esc(ML(b.k))}</text>`;
  });
  const sgn = v => (v > 0.5 ? '+' : '') + F0(v) + ' €', nz = (c, l, v) => Math.abs(v) >= 0.005 ? cfTipRow(c, l, sgn(v)) : '';
  bs.forEach((b, i) => {          // a month under the pointer: its parts and the change in cash, as in the cash flow
    const tip = cfTip(`<div class="cf-tip-h">${esc(MLL(b.k))}</div>` + nz('sw ein', t('einnahmen'), b.ein) + nz('sw aus', t('ausgaben'), b.aus) + nz('sw inv', SEC_LABEL.investing, b.inv)
      + nz('sw fin', SEC_LABEL.financing, b.fin) + nz('sw unk', t('cf_unklar'), b.unk) + `<div class="cf-tip-res">${cfTipTot(t('zahlungsfluss_gesamt_veraenderung_liqu'), sgn(b.net))}</div>`);
    g += `<rect class="cf-hit" data-cftip="${tip}" x="${(P.l + slot * i).toFixed(1)}" y="0" width="${slot.toFixed(1)}" height="${H - P.b}"/>`; });
  const net = bs.reduce((a, b) => a + b.net, 0);
  return {svg: `<svg class="cf-svg ov-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(t('cf_je_monat_t'))}">${g}</svg>`,
    fig: `<span class="ov-s">${t('ov_bank_12')} ${ovDelta(net)}</span>`};
}
// 4. Where the net worth of the last twelve closed months came from: start, the steps (surplus, interest, changes in value ...), end
function ovWealth(D, W, H) {
  const ms = cfDone(D).slice(-12); if (!ms.length) return ovEmpty(t('cf_keine_zahlungen'));
  const rows = cfWealthTree(D, ms, []); if (!rows.some(r => r.kind !== 'tot')) return ovEmpty(t('cf_keine_zahlungen'));
  let lvl = 0; const list = rows.map(r => { if (r.kind === 'tot') { lvl = r.v; return {...r, a: 0, b: r.v}; } const o = {...r, a: lvl, b: lvl + r.v}; lvl += r.v; return o; });
  const lo = Math.min(0, ...list.map(r => Math.min(r.a, r.b))), hi = Math.max(0, ...list.map(r => Math.max(r.a, r.b)));
  const nameW = Math.min(W * 0.36, 170), numW = 74, L = nameW + 4, R = W - numW - 6, X = v => L + (v - lo) / ((hi - lo) || 1) * (R - L);
  const rh = Math.min(30, Math.max(18, (H - 6) / list.length)), bh = Math.min(14, rh * 0.5);
  let g = '', yy = 3, prevEnd = null;
  for (const r of list) {
    const mid = yy + rh / 2, x0 = X(Math.min(r.a, r.b)), x1 = X(Math.max(r.a, r.b)), cls = r.kind === 'tot' ? 'tot' : r.kind === 'one' ? 'unk' : r.v >= 0 ? 'in' : 'out';
    if (prevEnd != null) { const xj = X(r.kind === 'tot' ? r.b : r.a); g += `<line class="cf-br-link" x1="${xj.toFixed(1)}" x2="${xj.toFixed(1)}" y1="${prevEnd.toFixed(1)}" y2="${(mid - bh / 2).toFixed(1)}"/>`; }
    const room = Math.floor((nameW - 4) / 6.6), lab = r.label.length > room ? r.label.slice(0, Math.max(3, room - 1)) + '…' : r.label;
    g += `<text class="ov-ln${r.kind === 'tot' ? ' tot' : ''}" x="2" y="${(mid + 4).toFixed(1)}">${esc(lab)}</text>`;
    if (Math.abs(r.v) >= 0.005) g += `<rect class="cf-br-bar ${cls}" x="${x0.toFixed(1)}" y="${(mid - bh / 2).toFixed(1)}" width="${Math.max(2, x1 - x0).toFixed(1)}" height="${bh.toFixed(1)}" rx="3"/>`;
    g += `<text class="ov-lv${r.kind === 'tot' ? ' tot' : ''}" x="${W - 4}" y="${(mid + 4).toFixed(1)}" text-anchor="end">${(r.kind === 'tot' || r.v < 0 ? '' : '+') + esc(F0(r.v))}</text>`;
    // the step under the pointer: its amount and its largest parts
    const sg = v => (r.kind === 'tot' || v < 0 ? '' : '+') + F0(v) + ' €', kids = (r.kids || []).slice(0, 8);
    const tip = cfTip(`<div class="cf-tip-h">${esc(r.label)}</div>` + (kids.length ? kids.map(c => cfTipRow('none', c.label, (c.v < 0 ? '' : '+') + F0(c.v) + ' €')).join('') + `<div class="cf-tip-res">${cfTipTot(r.label, sg(r.v))}</div>`
      : cfTipRow('none', `${ML(ms[0])} – ${ML(ms[ms.length - 1])}`, sg(r.v))));
    g += `<rect class="cf-hit" data-cftip="${tip}" x="0" y="${yy.toFixed(1)}" width="${W}" height="${rh.toFixed(1)}" rx="4"/>`;
    prevEnd = mid + bh / 2; yy += rh;
  }
  const tot = list.filter(r => r.kind === 'tot'), chg = tot.length > 1 ? tot[tot.length - 1].v - tot[0].v : null;
  return {svg: `<svg class="cf-svg ov-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(t('cf_verm_bruecke'))}">${g}</svg>`,
    fig: `<span class="ov-s">${esc(ML(ms[0]))} – ${esc(ML(ms[ms.length - 1]))}${chg != null ? ' · ' + ovDelta(chg) : ''}</span>`};
}

// ---------------------------------------------------------------- Einrichtung (modular)
const MODULES = [
  {id: 'webapp', t: t('mod_webapp'), d: t('mod_webapp_d'), done: () => APP_MODE || !!((S.CFG || {}).ui || {}).webapp, href: '#settings', optional: true},
  {id: 'connect', t: t('mod_connect'), d: t('moneymoney_laeuft_und_ist_entsperrt'), done: () => S.KONTEN.length > 0, href: '#settings/moneymoney'},
  {id: 'areas', t: t('mod_areas'), d: t('welche_konten_gehoeren_zusammen_privat'), done: () => (S.CFG.areas || []).length > 0 || !!S.DATA, href: '#accounts/areas'},
  {id: 'accounts', t: t('mod_accounts'), d: t('jedes_konto_bestaetigen_bereich_und'), done: () => !!S.DATA && !((S.DATA.accounts_new || []).length), href: '#accounts'},
  {id: 'history', t: t('mod_history'), d: t('bisherigen_verlauf_aller_konten_einmal'), done: () => !!((S.STATUS || {}).moneymoney || {}).history, href: '#accounts/history', optional: true},
  {id: 'rules', t: t('mod_rules'), d: t('darlehen_spiegeln_und_verzinsen_beteil'), done: () => hasRules(), href: '#accounts/rules', optional: true},
  {id: 'categories', t: t('mod_categories'), d: t('kategorien_auswaehlen_d'), done: () => Object.keys((S.CFG.cashflow || {}).positions || {}).length > 0, href: '#accounts/positions', optional: true},
  {id: 'properties', t: t('mod_properties'), d: t('kalkulationen_anlegen_mit_konten_und'), done: () => (S.CFG.real_estate || []).length > 0, href: '#properties', optional: true},
  {id: 'planning', t: t('mod_planning'), d: t('horizont_inflation_steigerungen_darleh'), done: () => !!S.DATA, href: '#planning', optional: true},
  {id: 'tax', t: t('mod_tax'), d: t('vermietungskategorie_darlehen_objekt_a'), done: () => ['property_loans', 'depreciation', 'positions', 'entities'].some(k => Object.keys((S.CFG.tax || {})[k] || {}).length), href: '#accounts/tax', optional: true},
  {id: 'receipts', t: t('mod_receipts'), d: t('belegordner_und_ablagemuster_belege_zu'), done: () => !!(S.CFG.receipts || {}).folder_confirmed, href: '#settings/receipts', optional: true},
  {id: 'iphone', t: t('mod_iphone'), d: t('zugriff_vom_iphone_d'), done: () => (((S.CFG || {}).ui || {}).bind || '127.0.0.1') !== '127.0.0.1', href: '#settings/access', optional: true},
  {id: 'assistant', t: t('ki_assistent_lang'), d: t('mod_assistant_d'), done: () => asOn() && !!(AS.st || {}).ready, href: '#settings/assistant', optional: true},
  {id: 'assign', t: t('mod_assign'), d: t('kontor_eigene_kategorien_baum_aus'), done: () => !!S.DATA && !(((S.DATA.categories || {}).total || {}).without), href: '#categories', optional: true},
  {id: 'operation', t: t('mod_operation'), d: t('testmodus_automatischer_abgleich_mitte'), done: () => true, href: '#settings/moneymoney'},
];
// the setup stays in the menu (and guides from step to step) until you close it yourself: "Einrichtung abgeschlossen"
const nextModule = id => MODULES[MODULES.findIndex(m => m.id === id) + 1];          // the next step of the setup
const setupMissing = () => MODULES.some(m => !m.optional && !m.done());
const setupOpen = () => !((S.CFG || {}).ui || {}).setup_done;          // (also before the settings have arrived, just after signing in)
function vEinrichtung(sub) {
  let h = `<div class="lang-pick" data-ex="setup.language"><label for="w-lang" class="small muted">${t('sprache_label')}</label><select id="w-lang">${langOpts()}</select></div>${S.KONTEN.length ? '' : `<div class="note">${t('noch_keine_konten_aus_moneymoney')}</div>`}<div class="setup-list" data-ex="setup.steps">`;
  MODULES.forEach((m, i) => {
    const ok = m.done();
    h += `<div class="srow ${ok ? 'done' : ''}"><div class="n">${ok ? '✓' : i + 1}</div><div class="b"><div class="t">${esc(m.t)}<span class="pill ${ok ? 'ok' : (m.optional ? 'neutral' : 'warn')}">${ok ? t('eingerichtet') : (m.optional ? t('optional') : t('offen'))}</span></div><div class="d">${m.id === 'webapp' ? webappStep(ok) : esc(m.d)}</div></div><div class="a">${m.id === 'webapp' ? (!SHELL && macApp() && macApp().ready ? `<button id="mac-app-open" class="small">${t('mac_app_oeffnen')}</button>` : INSTALL_PROMPT && !ok ? `<button id="webapp-install" class="small">${t('als_app_installieren')}</button>` : '') : `<a href="${m.href}"><button class="small ${ok ? 'secondary' : ''}">${ok ? t('anpassen') : t('einrichten')}</button></a>`}</div></div>`;
  });
  h += '</div>';
  const miss = setupMissing(), close = setupOpen()
    ? `<button id="setup-done" ${miss ? `disabled title="${esc(t('einrichtung_erst_noetige'))}"` : `title="${esc(t('einrichtung_abschliessen_tip'))}"`}>${t('einrichtung_abschliessen')}</button>`
    : `<button id="setup-again" class="secondary" title="${esc(t('einrichtung_wieder_tip'))}">${t('einrichtung_wieder')}</button>`;
  h += `<div data-ex="setup.finish"><div class="actions">${close}<button id="check-btn" class="secondary">${t('einrichtung_pruefen')}</button>${hq('einrichtung_knoepfe')}</div><div id="findings-e" class="findings"></div></div>`;
  if (!S.DATA) h += `<div class="card" data-ex="setup.report"><h3>${t('erste_auswertung_erstellen')}</h3><div class="small muted">${t('liest_alle_umsaetze_aus_moneymoney')}</div><div class="actions"><button id="w-report" class="small">${t('auswertung_erstellen')}</button></div></div>`;
  return h;
}
function mmhStep1(st) {
  const off = !(st.moneymoney || {}).running;
  return `<div class="b"><b>${t('moneymoney_beenden')}</b><span class="dot ${off ? 'ok' : 'warn'}"></span>${off ? t('moneymoney_ist_beendet') : t('in_moneymoney_q_druecken_sonst')}</div>`;
}
async function vMMHistorie() {
  let r = {}; try { r = await api('/api/sync'); } catch (e) {}
  const rest = depotSection(r) + histImportSection();
  return setupNav('history') + `<div data-ex="accounts.history"><div data-ex="accounts.history.moneymoney"><h2>${t('verlauf_aus_mm_h')}</h2>` + (S.STATUS.local ? vMMImport() : `<div class="note">${t('nur_direkt_am_mac_moeglich')}</div>`) + '</div>' + rest + '</div>';
}
function histImportSection() {
  return `<div data-ex="accounts.history.import"><h2>${t('saldenverlauf_importieren_0', hq('verlauf_import'))}</h2><div class="note">${t('fuer_depots_und_konten_ohne')}</div>
    <div class="drop" id="hi-drop">${t('datei_hierher_ziehen')}<br><button id="hi-pick" class="small" style="margin-top:8px">${t('datei_waehlen')}</button></div><div id="hi-preview"></div></div>`;
}
function vMMImport() {
  const st = S.STATUS, last = (st.moneymoney || {}).history;
  const n = x => x === 1 ? t('ein_konto_2') : x + t('konten');
  return `${last ? `<div class="banner info small">${t('uebernommen_am_0_1_2', esc(fmtZeit(last.time)), n(last.accounts), last.date_from ? `${t('0_bis_1_2', ML(last.date_from), ML(last.date_to))}` : '')}</div>` : ''}
  <div class="note">${t('kontor_uebernimmt_einmalig_den_bisheri', hq('mmhist'))}</div>
  <div class="steps">
    <div class="step ${(st.moneymoney || {}).running ? '' : 'done'}" id="mmh-s1">${mmhStep1(st)}</div>
    <div class="step"><div class="b"><b>${t('datei_im_finder_zeigen')}</b>${t('kontor_oeffnet_ein_finder_fenster')}<div class="actions"><button id="mmh-zeigen" class="small">${t('im_finder_zeigen')}</button></div><div class="small muted">${t('kein_fenster_in_moneymoney_hilfe')}</div></div></div>
    <div class="step ${last ? 'done' : ''}"><div class="b"><b>${t('hierher_ziehen_passwort_eingeben')}</b>${t('danach_erscheint_ein_fenster_von')}<div class="drop" id="mmh-drop">${t('moneymoney_sqlite_hierher_ziehen')}<br><button id="mmh-pick" class="small" style="margin-top:8px">${t('datei_waehlen')}</button><input type="file" id="mmh-file" class="hidden"></div><div id="mmh-res" class="findings"></div></div></div>
    <div class="step hidden" id="mmh-names" data-ex="accounts.history.securities"></div>
    </div>`;
}
// Kontostände: what history Kontor knows per portfolio (MoneyMoney does not give it out) and months that may be missing
function depotSection(r) {
  const dep = r.depots || [];
  let h = (r.gaps || []).length ? `<div class="banner">${t('moeglicherweise_fehlen_depotstaende_mo', r.gaps.map(l => `<b>${esc(l.name)}</b> ${l.months.map(ML).join(', ')}`).join('; '))} <button class="small secondary" id="gap-ok">${t('hinweis_ausblenden')}</button></div>` : '';
  if (dep.length) h += `<h2>${t('depots_wertverlauf_0', hq('depotverlauf'))}</h2><div class="note">${t('depot_verlauf_note', r.recorded_since ? ML(r.recorded_since) : t('heute'))}${more('balances')}</div>
    <div class="wrap auto"><table class="plain acct-table sync-table"><thead><tr><th>${t('depot')}</th><th>${t('bereich')}</th><th>${t('bekannt_ab')}</th><th></th></tr></thead><tbody>${dep.map(k => `<tr data-uuid="${k.uuid}"><td>${esc(k.name)}<div class="small muted">${esc(CP(k.path.split(' / ').slice(0, -1).join(' / ')))}</div></td><td class="small">${esc(k.area || '–')}</td><td>${k.first_balance ? ML(k.first_balance) : '–'}${k.from_moneymoney ? ` <span class="small muted">${t('aus_moneymoney')}</span>` : ''}${k.own ? ` <span class="small muted">${t('0_eingetragen', k.own)}</span>` : ''}</td><td class="c nowrap"><button class="small secondary dep-hist">${t('staende_eintragen')}</button></td></tr>`).join('')}</tbody></table></div>`;
  return h ? `<div data-ex="accounts.history.depots">${h}</div>` : '';
}
const MMH_TXT = {received: t('gleich_erscheint_das_passwortfenster_v'), password: t('bitte_im_fenster_von_macos'), decrypt: t('wird_im_arbeitsspeicher_entschluesselt'), search: t('kontostaende_werden_gesucht_und_geprue')};
async function mmhFollow() {
  // Fortschritt des Einlesens verfolgen, bis ein Ergebnis da ist
  for (;;) {
    let r; try { r = await api('/api/history/mm-status'); } catch (e) { await new Promise(ok => setTimeout(ok, 1500)); continue; }
    const res = $('#mmh-res');
    if (r.running) { if (res) res.innerHTML = `<div class="working"><span class="spin"></span>${esc(MMH_TXT[r.step] || t('bitte_warten'))}</div>`; await new Promise(ok => setTimeout(ok, 800)); continue; }
    const e = r.result || {};
    if (e.ok) { try { S.STATUS = await api('/api/status'); statusMini(); } catch (x) {} }
    const msg = e.ok ? `${t('kontostaende_von_0_uebernommen_1', e.accounts === 1 ? t('einem_konto') : e.accounts + t('konten'), e.date_from ? ` ${t('0_bis_1_3', ML(e.date_from), ML(e.date_to))}` : '', e.depots ? `${t('davon_0', e.depots === 1 ? t('ein_depot') : e.depots + t('depots'))}` : '')}` : (e.text || t('nicht_uebernommen'));
    if (S.tab === 'accounts' && S.sub === 'history') { if (e.ok) { try { S.DATA = await api('/api/dataset'); } catch (x) {} await route(); } const res2 = $('#mmh-res'); if (res2) showFindings(res2, [], msg, e.ok ? 'ok' : 'error'); }
    else toast(msg, 8000);
    return;
  }
}
async function mmhNames(openList) {
  // the names of the securities: the ones MoneyMoney knows only by their ISIN can be looked up once at OpenFIGI (only on a
  // click, only the ISINs are sent); then all securities are listed with their names, which can be changed here
  const el = $('#mmh-names'); if (!el) return;
  let r; try { r = await api('/api/securities/lookup'); } catch (e) { return; }
  const n = r.open.length, had = r.found + r.without > 0, list = r.list || [];
  el.classList.toggle('hidden', !n && !list.length); el.classList.toggle('done', !n && list.length > 0);
  const base = x => x.mm || x.looked_up || '';
  el.innerHTML = `<div class="b"><b>${t('wp_suche_titel')} <span class="pill neutral">${t('optional')}</span></b>`
    + (list.length ? `<div class="small muted">${t('wp_aus_mm', r.from_mm, list.length)}</div>` : '')
    + (n ? `<div>${t('wp_suche_text', n === 1 ? t('wp_suche_eins') : t('wp_suche_n', n))}</div><details class="small"><summary>${t('wp_suche_liste')}</summary><div class="mono">${r.open.map(esc).join(', ')}</div></details>` : '')
    + (had ? `<div class="small muted">${t('wp_suche_stand', r.found, r.without, esc(fmtZeit(r.time)))}</div>` : '')
    + (list.length ? `<details class="small"${openList ? ' open' : ''}><summary>${t('wp_suche_bearbeiten', list.length)}</summary><div class="small muted">${t('wp_suche_bearbeiten_tip')}</div>`
      + `<div class="wp-edit">${list.map(x => `<label><span class="mono" title="${esc(x.mm ? t('wp_in_mm', x.mm) : t('wp_in_mm_ohne'))}">${esc(x.isin)}</span><input data-isin="${esc(x.isin)}" value="${esc(x.own_name || base(x))}" placeholder="${esc(base(x) || t('wp_suche_kein_name'))}" maxlength="120"></label>`).join('')}</div>`
      + `<div class="actions"><button id="wp-names-save" class="small">${t('speichern')}</button></div></details>` : '')
    + `<div class="actions">${n ? `<button id="wp-look" class="small">${t('wp_suche_btn')}</button>` : ''}${had || list.some(x => x.own_name) ? `<button id="wp-look-del" class="small secondary">${t('wp_suche_entfernen')}</button>` : ''}</div><div id="wp-look-res" class="findings"></div></div>`;
  const run = async (btn, body) => {
    const res = $('#wp-look-res', el); btn.classList.add('busy'); res.innerHTML = `<div class="working"><span class="spin"></span>${t('bitte_warten')}</div>`;
    try {
      const j = await api('/api/securities/lookup', body);
      try { S.DATA = await api('/api/dataset'); } catch (e) {}
      await mmhNames(!body.action || body.action === 'names');
      const res2 = $('#wp-look-res'); if (res2) showFindings(res2, [], j.removed ? t('wp_suche_entfernt') : body.action === 'names' ? t('wp_suche_gespeichert') : t('wp_suche_ergebnis', j.new, j.sent, j.from_mm), 'ok');
    } catch (e) { showFindings(res, [], e.message, 'error'); btn.classList.remove('busy'); }
  };
  const lb = $('#wp-look', el); if (lb) lb.addEventListener('click', () => run(lb, {}));
  const ld = $('#wp-look-del', el); if (ld) ld.addEventListener('click', () => run(ld, {action: 'remove'}));
  const ns = $('#wp-names-save', el); if (ns) ns.addEventListener('click', () => run(ns, {action: 'names', names: Object.fromEntries($$('.wp-edit input', el).map(i => [i.dataset.isin, i.value.trim()]))}));
}
const MMHP = {timer: null};
function mmhPoll() {
  // Auf der Seite "Kontostände aus MoneyMoney": alle 3 s pruefen, ob MoneyMoney beendet ist
  clearTimeout(MMHP.timer);
  if (!(S.tab === 'accounts' && S.sub === 'history')) return;
  MMHP.timer = setTimeout(async () => {
    try { S.STATUS = await api('/api/status?fresh=1'); statusMini(); const el = $('#mmh-s1'); if (el) { el.className = 'step ' + ((S.STATUS.moneymoney || {}).running ? '' : 'done'); el.innerHTML = mmhStep1(S.STATUS); } } catch (e) {}
    mmhPoll();
  }, 3000);
}
function mmStepDone(st) { return st.moneymoney.running && st.moneymoney.locked !== true; }
function mmStepInner(st) {
  const m = st.moneymoney;
  const txt = !m.running ? t('moneymoney_starten_und_entsperren_kont')
    : m.locked === true ? t('moneymoney_laeuft_ist_aber_gesperrt') : t('moneymoney_laeuft_und_ist_entsperrt_2');
  return `<div class="b"><b>${t('moneymoney_laeuft')}</b><span class="dot ${!m.running ? 'off' : m.locked === true ? 'warn' : 'ok'}"></span>${txt}</div>`;
}
const VB = {timer: null};
const READ_STEPS = [['accounts', 1], ['transactions', 8], ['parse', 3], ['portfolios', 2], ['categories', 1], ['save', 2]];   // Schritt, Dauer ohne Erfahrungswert (s)
const READ_LABEL = {accounts: t('lesen_accounts'), transactions: t('lesen_transactions'), parse: t('lesen_parse'), portfolios: t('lesen_portfolios'), categories: t('lesen_categories'), save: t('lesen_save')};
function readProgress() {
  // Fortschrittsbalken beim Lesen aus MoneyMoney: Schritte vom Dienst, Anteil nach der Dauer der Schritte beim letzten Mal
  let on = true, timer = null;
  const tick = async () => {
    if (!on) return;
    try {
      const p = await api('/api/check/status'), bar = $('#w-prog'), lab = $('#w-prog-l');
      if (bar && p.step && p.start) {
        const est = Object.fromEntries(READ_STEPS.map(([k, d]) => [k, (p.duration || {})[k] || d])), idx = READ_STEPS.findIndex(([k]) => k === p.step);
        const inStep = Math.max(0, p.now - p.since), cur = idx >= 0 ? Math.max(est[p.step], inStep * 1.15) : 0;
        const total = READ_STEPS.reduce((a, [k]) => a + est[k], 0) - (idx >= 0 ? est[p.step] - cur : 0);
        const done = READ_STEPS.slice(0, Math.max(0, idx)).reduce((a, [k]) => a + est[k], 0) + Math.min(inStep, cur);
        bar.style.width = (p.step === 'done' ? 100 : Math.min(99, 100 * done / Math.max(1, total))).toFixed(1) + '%';
        if (lab) lab.textContent = (READ_LABEL[p.step] || t('lese_konten_und_umsaetze_aus')) + ' · ' + Math.round(p.now - p.start) + ' s';
      }
    } catch (e) {}
    if (on) timer = setTimeout(tick, 350);
  };
  timer = setTimeout(tick, 150);
  return () => { on = false; clearTimeout(timer); const bar = $('#w-prog'); if (bar) bar.style.width = '100%'; };
}
function vbPoll() {
  // Auf der Seite "Verbindung" alle 3 s pruefen, ob MoneyMoney laeuft und entsperrt ist
  clearTimeout(VB.timer);
  if (!(S.tab === 'settings' && S.sub === 'moneymoney')) VB.checked = null;
  if (!(S.tab === 'settings' && S.sub === 'moneymoney') || (mmStepDone(S.STATUS) && S.KONTEN.length)) return;
  VB.timer = setTimeout(async () => {
    try { S.STATUS = await api('/api/status?fresh=1'); statusMini(); const el = $('#vb-mm'); if (el) { el.className = 'step ' + (mmStepDone(S.STATUS) ? 'done' : ''); el.innerHTML = mmStepInner(S.STATUS); } } catch (e) {}
    vbPoll();
  }, 3000);
}
function vVerbindung() {
  const st = S.STATUS;
  return `<div class="steps" data-ex="settings.moneymoney.connection">
    <div class="step ${mmStepDone(st) ? 'done' : ''}" id="vb-mm">${mmStepInner(st)}</div>
    <div class="step ${S.KONTEN.length ? 'done' : ''}"><div class="b"><b>${t('zugriff_erlauben_und_konten_lesen', hq('berechtigung'))}</b>${t('macos_fragt_einmal_ob_python3')}<div class="actions"><button id="w-check" class="small">${t('verbindung_pruefen')}</button></div><div id="w-busy" class="prog-wrap hidden"><div class="prog"><i id="w-prog"></i></div><span class="prog-l" id="w-prog-l">${t('lese_konten_und_umsaetze_aus')}</span></div><div id="w-findings" class="findings"></div></div></div>
    </div>`;
}
const FIRMA_RE = /\b(gmbh|ug|ag|se|kg|ohg|gbr|egbr|e\.?\s?k\.?|e\.?\s?v\.?|eg|ltd|inc|llc|holding|verwaltung|beteiligung|immobilien|stiftung|verein|genossenschaft|partner|&\s?co)\b/i;
const guessArt = name => FIRMA_RE.test(name || '') || /(gmbh|gbr|holding)/i.test(name || '') ? 'company' : 'private';
function vBereicheEditor() {
  const roots = S.KONTEN.filter(k => k.group && k.depth === 0);
  let list = (S.CFG.areas || []).length ? S.CFG.areas : roots.map(r => ({id: r.uuid, name: r.name, accounts: [r.uuid + ' | ' + r.name], main_area: false, kind: guessArt(r.name), share: null}));
  if (list.length && !list.some(b => b.main_area)) { const p = list.find(b => (b.kind || guessArt(b.name)) === 'private') || list[0]; p.main_area = true; }
  if (!(S.CFG.areas || []).length) list = list.map((b, i) => [b, i]).sort((x, y) => (!x[0].main_area - !y[0].main_area) || (((x[0].kind || guessArt(x[0].name)) !== 'private') - ((y[0].kind || guessArt(y[0].name)) !== 'private')) || x[1] - y[1]).map(x => x[0]);
  let h = `<div data-ex="accounts.areas"><div class="note">${t('bereiche_note', more('areas'), S.KONTEN.length ? '' : `<b>${t('noch_keine_konten_geladen_zuerst')}</b>`)}</div><div class="list" id="bereiche">`;
  list.forEach((b, i) => { h += bereichForm(b, i); });
  h += `</div><div class="actions"><button id="add-bereich" class="secondary">${t('bereich_hinzufuegen')}</button><button id="save-bereiche" class="${setupOpen() ? 'secondary' : ''}">${t('speichern')}</button>${setupOpen() ? `<button data-savenext="#accounts" data-save="areas">${t('speichern_und_weiter_konten')}</button><button class="secondary" data-next="#setup">${t('zurueck_zur_einrichtung')}</button>` : ''}</div><div id="findings-b" class="findings"></div></div>`;
  return h;
}
function bereichForm(b, i) {
  const sel = new Set((b.accounts || []).map(r => r.split('|')[0].trim()));
  const art = b.kind || guessArt(b.name);
  const pct = b.share != null && b.share !== '' ? Math.round(parseFloat(b.share) * 10000) / 100 : '';
  // Konten unter einer gewaehlten Gruppe sind enthalten (angehakt, gesperrt)
  // an account given an area under Konten is in exactly that area, whatever its group (as the service counts it): shown so, changed there
  const ids = new Map((S.CFG.areas || []).map(x => [x.id, x.name])), mapped = {};
  Object.entries((S.CFG.balance || {}).accounts_mapping || {}).forEach(([ref, z]) => { if (z && ids.has(z.area)) mapped[ref.split('|')[0].trim()] = z.area; });
  const rows = []; let within = null;
  for (const k of S.KONTEN) {
    if (within !== null && k.depth <= within) within = null;
    const fixed = !k.group && b.id && mapped[k.uuid] ? mapped[k.uuid] : null, implied = within !== null || !!fixed;
    const checked = fixed ? fixed === b.id : sel.has(k.uuid) || implied;
    if (k.group && sel.has(k.uuid) && within === null) within = k.depth;
    rows.push(`<label class="chk small ${implied ? 'implied' : ''}" style="padding-left:${k.depth * 14}px"${fixed ? ` title="${esc(t('b_zugeordnet_unter_konten', ids.get(fixed)))}"` : ''}><input type="checkbox" class="b-k" data-ebene="${k.depth}" data-gruppe="${k.group ? 1 : 0}"${fixed ? ` data-fixed="1"${sel.has(k.uuid) ? ' data-listed="1"' : ''}` : ''} value="${k.uuid} | ${esc(k.name)}" ${checked ? 'checked' : ''} ${implied ? 'disabled' : ''}> ${esc(k.name)}${k.group ? ` <span class="muted">${t('gruppe_mit_allen_konten_darunter')}</span>` : ''}</label>`);
  }
  return `<div class="item" data-i="${i}"><div class="grow"><div class="form">
    <label>${t('name')}</label><input type="text" class="b-name" value="${esc(b.name || '')}">
    <input type="hidden" class="b-id" value="${esc(b.id || '')}">
    <label>${t('art')}</label><select class="b-art"><option value="private" ${art === 'private' ? 'selected' : ''}>${t('privat')}</option><option value="company" ${art === 'company' ? 'selected' : ''}>${t('gesellschaft_gbr_gmbh')}</option></select>
    <label>${t('hauptbereich_0', hq('main_area'))}</label><label class="chk"><input type="radio" name="b-haupt" class="b-haupt" ${b.main_area ? 'checked' : ''}> ${b.main_area ? t('ja') : t('nein')}</label>
    <label class="b-anteil-row ${art === 'private' ? 'hidden' : ''}">${t('anteil_0', hq('share'))}</label><div class="row tight b-anteil-row ${art === 'private' ? 'hidden' : ''}"><input type="number" step="0.01" min="0" max="100" class="b-anteil" value="${pct}" placeholder="100" style="width:110px"> %</div>
    <label>${t('konten_gruppen_0', hq('gruppenwahl'))}</label><div class="list b-konten" style="max-height:240px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:6px 10px">${rows.join('')}</div>
  </div></div><div class="b-side"><div class="b-mvs"><button class="secondary small b-mv" data-d="-1" title="${t('nach_oben')}">▲</button><button class="secondary small b-mv" data-d="1" title="${t('nach_unten')}">▼</button></div><button class="danger small del">${t('entfernen')}</button></div></div>`;
}
function bereichMvState() { const its = $$('#bereiche .item'); its.forEach((it, i) => { const [up, dn] = $$('.b-mv', it); if (up) up.disabled = i === 0; if (dn) dn.disabled = i === its.length - 1; }); }
function bindBereichKonten(main) {
  // Gruppe anhaken -> alle Konten darunter enthalten (gesperrt); Konto darunter abwaehlen -> Gruppe wird abgewaehlt, die uebrigen bleiben einzeln gewaehlt
  $$('.b-konten', main).forEach(box => box.addEventListener('change', e => {
    const cb = e.target; if (!cb.classList.contains('b-k')) return;
    const all = $$('.b-k', box), idx = all.indexOf(cb), lvl = +cb.dataset.ebene;
    const below = []; for (let j = idx + 1; j < all.length && +all[j].dataset.ebene > lvl; j++) below.push(all[j]);
    if (cb.dataset.gruppe === '1') {
      below.filter(c => !c.dataset.fixed).forEach(c => { c.checked = cb.checked; c.disabled = cb.checked; c.closest('label').classList.toggle('implied', cb.checked); });
    } else if (!cb.checked) {
      // uebergeordnete, angehakte Gruppen aufloesen: die uebrigen Konten darunter bleiben einzeln gewaehlt
      let cur = lvl;
      for (let j = idx - 1; j >= 0; j--) {
        const g = all[j]; if (+g.dataset.ebene >= cur) continue;
        cur = +g.dataset.ebene;
        if (g.dataset.gruppe === '1' && g.checked) { g.checked = false; for (let m = j + 1; m < all.length && +all[m].dataset.ebene > cur; m++) { if (all[m].dataset.fixed) continue; all[m].disabled = false; all[m].closest('label').classList.remove('implied'); } }
      }
      cb.checked = false;
    }
  }));
  $$('.b-haupt', main).forEach(r => r.addEventListener('change', () => $$('.b-haupt', main).forEach(x => { x.parentElement.lastChild.textContent = x.checked ? ' ja' : ' nein'; })));
  const anteilSichtbar = it => $$('.b-anteil-row', it).forEach(x => x.classList.toggle('hidden', $('.b-art', it).value === 'private'));
  $$('.b-name', main).forEach(inp => inp.addEventListener('input', () => { const it = inp.closest('.item'), sel = $('.b-art', it); if (sel && !sel.dataset.touched) { sel.value = guessArt(inp.value); anteilSichtbar(it); } }));
  $$('.b-art', main).forEach(sel => sel.addEventListener('change', () => { sel.dataset.touched = '1'; anteilSichtbar(sel.closest('.item')); }));
}
function collectBereiche() {
  const cfg = JSON.parse(JSON.stringify(S.CFG));
  cfg.areas = $$('#bereiche .item').map(it => ({ id: $('.b-id', it).value.trim() || ('b-' + Math.random().toString(36).slice(2, 10)), name: $('.b-name', it).value.trim(),
    kind: $('.b-art', it).value || guessArt($('.b-name', it).value), main_area: $('.b-haupt', it).checked,
    share: $('.b-art', it).value === 'private' || $('.b-anteil', it).value === '' ? null : Math.round(parseFloat($('.b-anteil', it).value) * 100) / 10000, active: true,
    // an account given its area under Konten (locked here): in its area, and wherever it was listed before -- kept as it was
    accounts: $$('.b-k', it).filter(c => c.dataset.fixed ? c.checked || c.dataset.listed : c.checked && !c.disabled).map(c => c.value) }));
  if (cfg.areas.length && !cfg.areas.some(b => b.main_area)) cfg.areas[0].main_area = true;
  return cfg;
}
async function vKontenEditor() {
  const leaves = S.KONTEN.filter(k => !k.group);
  let ab = {}; try { ab = Object.fromEntries(((await api('/api/sync')).accounts || []).map(k => [k.uuid, k])); } catch (e) {}     // online or offline, as recognised
  const cfg = S.CFG, rollen = cfg.balance.roles || {}, verlauf = cfg.balance.history_source || {}, hide = new Set((cfg.balance.hidden_accounts || []).map(r => r.split('|')[0].trim())), show = new Set((cfg.balance.always_show || []).map(r => r.split('|')[0].trim()));
  const roleOf = u => { const k = Object.keys(rollen).find(x => x.split('|')[0].trim() === u); return k ? rollen[k] : ''; };
  const verOf = u => { const k = Object.keys(verlauf).find(x => x.split('|')[0].trim() === u); return k ? verlauf[k] : ''; };
  const bereiche = (S.CFG.areas || []).length ? S.CFG.areas.map(b => [b.id, b.name]) : Object.entries((S.DATA && S.DATA.area_names) || {});
  const neu = leaves.filter(k => !k.confirmed);
  let h = `<div data-ex="accounts.accounts"><div class="note">${t('konten_note', more('accounts'))}</div>
  ${neu.length ? `<div class="banner info">${t('0_noch_nicht_bestaetigt_1', nKonten(neu.length), esc(neu.slice(0, 6).map(k => k.name).join(', ')), neu.length > 6 ? ' …' : '')}</div>` : ''}
  <div class="row tight"><label>${t('nach_aktivitaet_ausblenden_ohne_bestan')} <input type="number" id="k-inaktiv" min="0" value="${cfg.balance.inactive_months ?? 12}" style="width:70px"> ${t('monaten_0', hq('inactive'))}</label><label class="switch"><input type="checkbox" id="k-show-inactive" checked><i></i>${t('ausgeblendete_hier_zeigen')}</label></div>
  <div class="wrap auto" data-ex="accounts.accounts.table"><table class="plain acct-table"><thead><tr><th>${t('konto_2')}</th><th>${t('bereich_0', hq('area'))}</th><th>${t('position_0', hq('position_kurz'))}</th><th>${t('verlauf_0', hq('verlauf_kurz'))}</th><th>${t('art')}${hq('ab_art')}</th><th>${t('anzeige_0', hq('anzeige'))}</th><th class="num">${t('saldo')}</th></tr></thead><tbody>`;
  // Reihenfolge: Bereiche wie unter „Bereiche“ angeordnet, darin die Konten wie in MoneyMoney; ohne Bereich zum Schluss
  const zuOf = k => ((cfg.balance.accounts_mapping || {})[k.uuid + ' | ' + k.name]) || Object.entries(cfg.balance.accounts_mapping || {}).find(([r]) => r.split('|')[0].trim() === k.uuid)?.[1] || {};
  const bIdx = Object.fromEntries(bereiche.map(([id], i) => [id, i]));
  const rows = leaves.map((k, i) => ({k, i, bsel: zuOf(k).area || k.area_id || ''})).sort((a, b) => ((bIdx[a.bsel] ?? 1e6) - (bIdx[b.bsel] ?? 1e6)) || a.i - b.i);
  let lastB = null;
  for (const {k, bsel} of rows) {
    if (bsel !== lastB) { lastB = bsel; h += `<tr class="bgroup"><td colspan="7">${esc((bereiche.find(([id]) => id === bsel) || [null, t('ohne_bereich')])[1])}</td></tr>`; }
    const cur = roleOf(k.uuid), ver = verOf(k.uuid);
    const vis = hide.has(k.uuid) ? 'hide' : show.has(k.uuid) ? 'show' : '', grenze = k.active_limit ?? (k.inactive_auto ? 9999 : 0), auto = autoHidden(grenze, cfg.balance.inactive_months ?? 12);
    const rolle = cur || k.role || 'other', quelle = ver || k.history_source || (k.depot ? 'balances' : 'transactions');
    // Vorschlag (was Kontor aus Name, Typ und Gruppe erkennt) steht in der Liste mit „(Vorschlag)“; gestrichelt = Vorschlag gewählt
    const sv = k.role_proposal || rolle, vv = k.depot ? 'balances' : 'transactions';
    const dash = (cur, v) => cur === v ? ' proposal' : '';
    h += `<tr data-uuid="${k.uuid}" data-ref="${k.uuid} | ${esc(k.name)}" data-auto="${auto ? 1 : 0}" data-grenze="${grenze}" class="${kontoHidden(vis, auto) ? 'inactive' : ''}${k.confirmed ? '' : ' neu'}"><td title="${esc(k.path)}">${esc(k.name)}${k.confirmed ? '' : `<span class="tag warn">${t('neu')}</span>`}<span class="tag k-vis">${t('ausgeblendet')}</span>${k.stale ? `<span class="tag warn" title="${t('saldo_0_aber_seit_1', F(k.balance_amount), esc(k.last_booking || k.updated || t('jeher')))}">${t('veraltet')}</span>` : ''}<div class="small muted">${esc(CP(k.path.split(' / ').slice(0, -1).join(' / ')))} · ${k.depot ? t('depot') : (k.manual || k.fetch === 'offline') ? t('manuell') : esc(k.type_name || t('bank'))}</div></td><td><select class="k-bereich"><option value="">${t('b_wie_bereiche')}</option>${bereiche.map(([id, n]) => `<option value="${esc(id)}" ${bsel === id ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></td>
      <td><select class="k-rolle${dash(rolle, sv)}" data-vor="${sv}">${ROLE_OPTS.map(([v, l]) => `<option value="${v}" ${rolle === v ? 'selected' : ''}>${l}${v === sv ? ` (${t('vorschlag')})` : ''}</option>`).join('')}</select></td>
      <td class="nowrap"><select class="k-verlauf${dash(quelle, vv)}" data-vor="${vv}">${[['transactions', t('umsaetze_2')], ['balances', t('kontostaende')]].map(([v, l]) => `<option value="${v}" ${quelle === v ? 'selected' : ''}>${l}${v === vv ? ` (${t('vorschlag')})` : ''}</option>`).join('')}</select> <button class="ghost small k-hist" title="${t('monatsstaende_ansehen_und_bearbeiten')}">${t('verlauf')}</button></td>
      <td>${ab[k.uuid] ? `<select class="ab-sel" title="${esc((ab[k.uuid].reason || t('wird_von_moneymoney_bei_bank')) + (ab[k.uuid].kind === 'online' && ab[k.uuid].time ? ' · ' + t('letzter_abruf') + ' ' + fmtZeit(ab[k.uuid].time) : ''))}"><option value="online" ${ab[k.uuid].kind === 'online' ? 'selected' : ''}>${t('art_online')}</option><option value="offline" ${ab[k.uuid].kind === 'offline' ? 'selected' : ''}>${t('art_offline')}</option></select>` : '–'}</td>
      <td><select class="k-show" title="${auto ? t('kein_bestand_und_kein_umsatz') + (cfg.balance.inactive_months ?? 12) + t('monaten') : t('mit_bestand_oder_umsatz_in') + (cfg.balance.inactive_months ?? 12) + t('monaten')}"><option value="">${t('nach_aktivitaet')}</option><option value="show" ${vis === 'show' ? 'selected' : ''}>${t('immer_anzeigen')}</option><option value="hide" ${vis === 'hide' ? 'selected' : ''}>${t('ausblenden')}</option></select></td>
      <td class="num ${(k.balance_amount || 0) < 0 ? 'neg' : 'pos'}">${F(k.balance_amount)}</td></tr>`;
  }
  h += `</tbody></table></div><div class="actions"><button id="save-konten" class="${setupOpen() ? 'secondary' : ''}">${t('speichern')}</button>${setupOpen() ? `<button data-savenext="#accounts/history" data-save="accounts">${t('speichern_und_weiter_kontostaende_aus')}</button><button class="secondary" data-next="#setup">${t('zurueck_zur_einrichtung')}</button>` : ''}</div><div id="findings-k2" class="findings"></div></div>`;
  return h;
}
let HI = null;   // {name, b64, vorschau}
async function histImportPreview(file) {
  const b64 = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1] || ''); r.onerror = rej; r.readAsDataURL(file); });
  HI = {name: file.name, b64};
  try { const r = await api('/api/history/import', {file: b64, name: file.name}); HI.preview = r.preview; HI.hints = r.hints || []; } catch (e) { HI = null; $('#hi-preview').innerHTML = `<div class="findings"><div class="error">${esc(e.message)}</div></div>`; return; }
  renderHistImport();
}
function renderHistImport() {
  const el = $('#hi-preview'); if (!el || !HI) return;
  const leaves = S.KONTEN.filter(k => !k.group);
  const opts = sel => `<option value="">${t('nicht_uebernehmen')}</option>` + leaves.map(k => `<option value="${k.uuid} | ${esc(k.name)}" ${sel === k.uuid ? 'selected' : ''}>${esc(k.name)}${k.depot ? t('depot_2') : ''}${k.history_source === 'balances' ? t('kontostaende_2') : ''}</option>`).join('');
  el.innerHTML = `<div class="card" style="margin-top:12px"><h3>${esc(HI.name)} <span class="muted">${t('0_spalten_konten_erkannt_1', HI.preview.length, HI.hints.length ? ' · ' + esc(HI.hints.join(' ')) : '')}</span></h3>
    <div class="wrap auto"><table class="plain"><thead><tr><th>${t('in_der_datei')}</th><th class="num">${t('monate')}</th><th>${t('zeitraum')}</th><th>${t('konto_in_kontor')}</th></tr></thead><tbody>${HI.preview.map(v => `<tr data-name="${esc(v.name)}"><td>${esc(v.name)}</td><td class="num">${v.count}</td><td class="small">${v.date_from} – ${v.date_to}</td><td><select class="hi-map">${opts(v.uuid)}</select>${v.uuid && !v.certain ? ` <span class="tag" title="${t('automatisch_zugeordnet_pruefen')}">${t('vorschlag')}</span>` : ''}</td></tr>`).join('')}</tbody></table></div>
    <div class="row tight" style="margin-top:8px"><label class="chk"><input type="checkbox" id="hi-gaps" checked> ${t('nur_monate_uebernehmen_fuer_die')}</label><button id="hi-import" class="small">${t('uebernehmen')}</button><span class="small muted">${t('ohne_zuordnung_bleibt_eine_zeile')}</span></div><div id="hi-report" class="findings"></div></div>`;
  $('#hi-import').onclick = async () => {
    const zuordnung = {}; $$('#hi-preview tr[data-name]').forEach(tr => { zuordnung[tr.dataset.name === t('s_ohne_konto') ? '' : tr.dataset.name] = $('.hi-map', tr).value; });
    try { const r = await api('/api/history/import', {file: HI.b64, name: HI.name, assignment: zuordnung, take_over: true, gaps_only: $('#hi-gaps').checked}); showFindings($('#hi-report'), [], r.taken_over + t('monatswerte_fuer') + (r.accounts === 1 ? t('ein_konto_2') : r.accounts + t('konten')) + t('uebernommen') + (r.report ? t('bericht_aktualisiert') : '.'), 'ok'); await loadAll(); } catch (e) { showFindings($('#hi-report'), [], e.message, 'error'); }
  };
}
function kontoHidden(vis, auto) { return vis === 'hide' || (vis === '' && !!auto); }
function autoHidden(grenze, n) { n = +n || 0; return n > 0 && n <= (+grenze || 0); }      // "nach Aktivität": ohne Bestand und Umsatz seit N Monaten
function collectKonten() {
  const cfg = JSON.parse(JSON.stringify(S.CFG)); const b = cfg.balance = cfg.balance || {};
  b.roles = {}; b.history_source = {}; b.illiquid_accounts = []; b.hidden_accounts = []; b.always_show = []; b.accounts_mapping = b.accounts_mapping || {};
  $$('tr[data-uuid]').forEach(tr => { const ref = tr.dataset.ref;
    // Position und Verlauf werden fest gespeichert: spätere Änderungen an Name, Typ oder Gruppe in MoneyMoney verschieben nichts
    b.accounts_mapping[ref] = {area: $('.k-bereich', tr).value, position: $('.k-rolle', tr).value, confirmed: true};
    b.roles[ref] = $('.k-rolle', tr).value;
    b.history_source[ref] = $('.k-verlauf', tr).value;
    if ($('.k-show', tr).value === 'hide') b.hidden_accounts.push(ref); if ($('.k-show', tr).value === 'show') b.always_show.push(ref); });
  b.inactive_months = Math.max(0, parseInt($('#k-inaktiv').value) || 0);
  return cfg;
}
// Verlauf (Monatsstaende) je Konto
function holdingsBox(uuid) {
  // Depot: Positionen aus MoneyMoney (Stand des letzten Lesens), aufklappbar oben im Verlaufsfenster
  const d = ((S.DATA && S.DATA.depots) || []).find(x => x.account === uuid); if (!d || !d.positions.length) return '';
  const gv = d.cost_basis ? d.sum - d.cost_basis : null;
  return `<details class="holdings" data-ex="drawer.hist.holdings"><summary>${tn('0_positionen', d.positions.length)} · ${F0(d.sum)} €${gv != null ? ` · <span class="${gv >= 0 ? 'pos' : 'neg'}">${gv >= 0 ? '+' : ''}${F0(gv)} € (${FN((d.sum / d.cost_basis - 1) * 100, 1)} %)</span>` : ''}</summary>
    <div class="small muted" style="margin:4px 0">${t('bestaende_aus_moneymoney_stand_des')} ${xlsxBtn('holdings')}</div>
    <table class="plain small"><thead><tr><th>${t('position')}</th><th class="num">${t('menge')}</th><th class="num">${t('wert')}</th><th class="num">G/V</th></tr></thead><tbody>`
    + d.positions.map(p => `<tr><td title="${esc([p.isin, p.asset_class].filter(Boolean).join(' · '))}">${esc(p.name)}</td><td class="num">${p.quantity.toLocaleString(LOCALE, {maximumFractionDigits: 4})}</td><td class="num">${F(p.value)}</td><td class="num ${p.value - p.cost_basis >= 0 ? 'pos' : 'neg'}">${p.cost_basis ? F(p.value - p.cost_basis) : ''}</td></tr>`).join('')
    + '</tbody></table></details>';
}
async function openHistDrawer(uuid, vorschau) {
  // vorschau: Verlaufsquelle, die erst angezeigt und mit „Speichern“ übernommen wird (z. B. aus der Kontentabelle)
  if (drawerAgain('acc:' + uuid + ':' + (vorschau || ''))) return;
  const r = await api('/api/history?account=' + encodeURIComponent(uuid) + (vorschau ? '&source=' + vorschau : ''));
  const k = S.KONTEN.find(x => x.uuid === uuid) || {name: r.name || uuid};
  const d = $('#drawer');
  HD.uuid = uuid; HD.live = r.live;
  // (data-ex: what each part shows, in Kontor's description of the side panels -- docs/ui/drawer.md)
  d.innerHTML = `<button class="close icon">✕</button><h2>${esc(k.name || r.name)}</h2><div data-ex="drawer.hist">${holdingsBox(uuid)}
    <div data-ex="drawer.hist.source"><div class="row tight"><span class="small muted">${t('verlauf_aus_0', hq('history_source'))}</span><div class="seg" id="hq-seg"><button class="hq-q" data-q="transactions">${t('umsaetzen')}</button><button class="hq-q" data-q="balances">${t('kontostaenden')}</button></div></div>
    <div class="small muted" id="hq-erkl" style="margin:4px 0 8px"></div>
    <div id="hq-hinweis"></div><div id="hq-pending"></div></div>
    <div class="h-chart" id="h-chart" data-ex="drawer.chart"></div>
    <div data-ex="drawer.hist.months"><h3>${t('monatsstaende')}</h3>
    <div class="row tight" id="h-addrow"><input type="month" id="h-von" style="width:140px"><button id="h-add" class="small secondary">${t('monat_ergaenzen')}</button></div>
    <div class="hist-grid" id="h-grid"></div>
    <div class="actions" id="h-actions"><button id="h-save" class="small">${t('speichern')}</button><button id="h-undo" class="small secondary hidden">${t('verwerfen')}</button><button id="h-clear" class="small secondary">${t('alle_eigenen_werte_loeschen')}</button></div></div>
    <div id="h-importbox"><h3>${t('import_aus_saldenexport')}</h3><div class="small muted">${t('csv_mit_datum_saldo_ein')}</div>
    <textarea id="h-csv" placeholder="${t('datum_saldo_31_12_2024')}"></textarea><div class="actions"><button id="h-import" class="small secondary">${t('vorschau')}</button><button id="h-import2" class="small hidden">${t('uebernehmen')}</button></div><div id="h-prev" class="findings"></div></div></div>`;
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
  $('#h-undo', d).onclick = async () => { try { renderHist(await api('/api/history?account=' + encodeURIComponent(uuid) + '&source=' + HD.r.source_saved)); } catch (e) { toast(e.message, 6000); } };
  $('#h-add', d).onclick = () => {
    // eingegebenen Monat hinzufuegen (gibt es ihn schon, wird sein Feld gewaehlt); Liste bleibt nach Monaten sortiert
    const mk = $('#h-von', d).value; if (!/^\d{4}-\d{2}$/.test(mk)) return;
    const have = $(`#h-grid input[data-mk="${mk}"]`, d); if (have) { have.focus(); return; }
    const next = $$('#h-grid input', d).find(i => i.dataset.mk > mk), html = `<label>${ML(mk)}<input type="text" data-mk="${mk}" class="auto" value=""></label>`;
    if (next) next.parentNode.insertAdjacentHTML('beforebegin', html); else $('#h-grid', d).insertAdjacentHTML('beforeend', html);
    $(`#h-grid input[data-mk="${mk}"]`, d).focus();
  };
  $('#h-save', d).onclick = async () => {
    const werte = {}; let bad = null; if (HD.r.source === 'balances') $$('#h-grid input', d).forEach(i => { if (!i.classList.contains('auto') || i.value.trim()) { const v = numIn(i.value); if (Number.isNaN(v)) bad = bad || i; werte[i.dataset.mk] = v; } });
    if (bad) { bad.focus(); bad.select(); toast(t('zahl_unlesbar', bad.value.trim()), 6000); return; }          // nothing is saved while one value is no number
    const body = {account: uuid, amounts: werte}; if (HD.r.source !== HD.r.source_saved) body.source = HD.r.source;
    try {
      const res = await api('/api/history', body); renderHist(res.history); toast(t('gespeichert'));
      if (body.source) { S.CFG = await api('/api/config'); const sel = $(`tr[data-uuid="${uuid}"] .k-verlauf`); if (sel) { sel.value = body.source; sel.classList.toggle('proposal', sel.value === sel.dataset.vor); } }
    } catch (e) { toast(e.message, 6000); }
  };
  $('#h-clear', d).onclick = async () => { if (!confirm(t('alle_eigenen_monatswerte_dieses_kontos'))) return; try { const res = await api('/api/history', {account: uuid, amounts: {}, delete: true}); renderHist(res.history); } catch (e) { toast(e.message, 6000); } };
  $('#h-import', d).onclick = async () => { try { const r2 = await api('/api/history/import', {account: uuid, csv: $('#h-csv', d).value}); $('#h-prev', d).innerHTML = r2.preview.map(v => `<div class="${v.uuid ? 'ok' : 'warning'}">${t('0_1_monate_2_3', esc(v.name), v.count, v.date_from, v.date_to, v.uuid ? '' : t('kein_konto_zugeordnet'))}</div>`).join(''); $('#h-import2', d).classList.remove('hidden'); } catch (e) { $('#h-prev', d).innerHTML = `<div class="error">${esc(e.message)}</div>`; } };
  $('#h-import2', d).onclick = async () => { try { const r2 = await api('/api/history/import', {account: uuid, csv: $('#h-csv', d).value, take_over: true}); toast(r2.taken_over + t('werte_uebernommen')); S.CFG = await api('/api/config'); const sel = $(`tr[data-uuid="${uuid}"] .k-verlauf`); if (sel) sel.value = 'balances'; await openHistDrawer(uuid); } catch (e) { toast(e.message, 6000); } };
}
function renderHist(r) {
  // Fensterinhalt aus der Vorschau des Dienstes (fuer dieses eine Konto sofort gerechnet)
  const d = $('#drawer'); if (!d.classList.contains('open')) return;
  HD.r = r; HD.live = r.live;
  const stand = r.source === 'balances';
  $$('.hq-q', d).forEach(x => x.classList.toggle('on', x.dataset.q === r.source));
  $('#hq-erkl', d).textContent = stand
    ? (r.depot ? t('letzter_bekannter_kontostand_gilt_depo')
               : t('eingetragene_kontostaende_sind_massgeb'))
    : t('saldo_am_monatsende_heutiger_saldo');
  const P = r.check || {}, infos = [];
  if (r.hint) infos.push(r.hint.replace(/^'[^']*': /, ''));
  if (!stand && P.first_booking && Math.abs(P.opening_balance || 0) > 0.005) infos.push(`${t('moneymoney_hat_umsaetze_erst_ab', P.first_booking.slice(8, 10), P.first_booking.slice(5, 7), P.first_booking.slice(0, 4), F(P.opening_balance))}`);
  if (!stand && !P.bookings && !r.depot) infos.push(t('keine_umsaetze_in_moneymoney_der'));
  if (P.pending_count) infos.push(`${t('0_vorgemerkte_umsaetze_zusammen_1', P.pending_count, F(P.pending_sum))}`);
  if (!r.live) infos.push(t('noch_kein_moneymoney_stand_im'));
  $('#hq-hinweis', d).innerHTML = infos.map(t => `<div class="banner info small">${esc(t)}</div>`).join('');
  const pending = r.source_saved && r.source !== r.source_saved;
  $('#hq-pending', d).innerHTML = pending ? `<div class="banner small">${t('vorschau_verlauf_aus_0_gespeichert', r.source === 'balances' ? t('kontostaenden') : t('umsaetzen'), r.source_saved === 'balances' ? t('kontostaende') : t('umsaetze_2'))}</div>` : '';
  const werte = r.amounts || {}, man = r.manual || {};
  const months = Object.keys(Object.assign({}, werte, man)).sort();
  const anker = new Set(r.anchor || []);
  $('#h-grid', d).innerHTML = months.map(mk => {
    const own = man[mk] != null;
    const val = werte[mk] != null ? F(werte[mk]) : '';
    if (!stand) return `<label>${ML(mk)}<input type="text" data-mk="${mk}" class="auto" value="" placeholder="${val}" disabled></label>`;
    return `<label class="${anker.has(mk) && !own ? 'rec' : ''}"${!own && (r.moneymoney || {})[mk] != null ? ` title="${t('aus_moneymoney_2')}"` : ''}>${ML(mk)}<input type="text" data-mk="${mk}" class="${own ? '' : 'auto'}" value="${own ? F(man[mk]) : ''}" placeholder="${val}"></label>`;
  }).join('');
  const pre = months[0] ? new Date(+months[0].slice(0, 4), +months[0].slice(5) - 2, 15) : new Date();   // Vorschlag: Monat vor dem ersten
  $('#h-von', d).value = `${pre.getFullYear()}-${String(pre.getMonth() + 1).padStart(2, '0')}`;
  $('#h-addrow', d).classList.toggle('hidden', !stand);
  $('#h-actions', d).classList.toggle('hidden', !stand && !pending);
  $('#h-clear', d).classList.toggle('hidden', !stand); $('#h-undo', d).classList.toggle('hidden', !pending);
  const g = $('#h-grid', d); if (g) g.scrollTop = g.scrollHeight;          // neueste Monate sichtbar
  const hp = months.filter(mk => werte[mk] != null).map(mk => [mk, werte[mk]]);
  $('#h-chart', d).innerHTML = histChart(hp); bindHistChart($('#h-chart', d), hp);
}
// History chart of the drawer (account or security): month-end values as a line with area; range 1 J / Alle (default all),
// swipe sideways or drag on the month axis to move, pinch / Ctrl+wheel / double click to zoom, the amount axis as in the
// other charts (drag to zoom the value range, tap for automatic)
const HC = {pts: [], f0: 0, f1: 0, yr: null, geo: null, btn: 0};
function histChart(pts) { return pts.length < 2 ? '' : `<div class="h-head"><div class="seg small" id="h-rb"><button data-m="12">${t('bch_jahre', 1)}</button><button data-m="0" class="on">${t('alle')}</button></div></div><svg class="h-svg" id="h-svg"></svg>`; }
function bindHistChart(box, pts) {
  const svg = $('#h-svg', box); if (!svg || pts.length < 2) return;
  Object.assign(HC, {pts, f0: 0, f1: pts.length - 1, yr: null, btn: 0});
  hcDraw();
  const W = () => HC.geo.W, pt = e => { const r = svg.getBoundingClientRect(); return (e.clientX - r.left) * W() / r.width; }, pty = e => { const r = svg.getBoundingClientRect(); return (e.clientY - r.top) * HC.geo.H / r.height; };
  const last = () => HC.pts.length - 1;
  const view = (f0, span) => { span = Math.max(1, Math.min(last(), span)); HC.f0 = Math.max(0, Math.min(last() - span, f0)); HC.f1 = HC.f0 + span; HC.btn = null; hcDraw(); };
  const at = px => { const G = HC.geo; return HC.f0 + (px - G.P.l) * (HC.f1 - HC.f0) / Math.max(1, G.W - G.P.l - G.P.r); };
  const zoom = (c, f) => { const span = HC.f1 - HC.f0, ns = Math.max(1, Math.min(last(), span * f)); view(c - (c - HC.f0) * ns / span, ns); };
  chartGestures(svg, {pt, pty, geo: () => HC.geo, ygeo: () => HC.geo, range: () => [HC.f0, HC.f1], view: (f0, span) => view(f0, span),
    yview: (lo, hi) => { HC.yr = lo == null ? null : [lo, hi]; hcDraw(); }, hide: () => { const hv = $('.h-hover', svg); if (hv) hv.innerHTML = ''; }});
  svg.addEventListener('pointermove', e => {
    if (!e.target.classList.contains('bch-hit')) return;
    const G = HC.geo, i = Math.max(Math.ceil(HC.f0), Math.min(Math.floor(HC.f1), Math.round(at(pt(e))))), [mk, v] = HC.pts[i], xi = G.x(i), right = xi > G.W * 0.6;
    $('.h-hover', svg).innerHTML = `<line class="bch-cross" x1="${xi.toFixed(1)}" x2="${xi.toFixed(1)}" y1="${G.P.t}" y2="${G.H - G.P.b}"/><circle class="bch-dot" cx="${xi.toFixed(1)}" cy="${G.y(v).toFixed(1)}" r="3.5"/>`
      + `<text class="h-lab" x="${(right ? xi - 6 : xi + 6).toFixed(1)}" y="${G.P.t + 10}" text-anchor="${right ? 'end' : 'start'}">${esc(ML(mk) + ': ' + F(v))}</text>`;
  });
  svg.addEventListener('pointerleave', () => { const hv = $('.h-hover', svg); if (hv) hv.innerHTML = ''; });
  svg.addEventListener('dblclick', e => { if (e.target.classList.contains('bch-hit')) zoom(at(pt(e)), 0.5); });
  svg.addEventListener('wheel', e => {
    if (!e.target.classList.contains('bch-hit')) return;
    if (e.ctrlKey) { e.preventDefault(); zoom(at(pt(e)), Math.exp(e.deltaY * 0.01)); return; }
    if (Math.abs(e.deltaX) <= Math.abs(e.deltaY) || HC.f1 - HC.f0 >= last()) return;
    e.preventDefault(); const G = HC.geo, span = HC.f1 - HC.f0; view(HC.f0 + e.deltaX * span / Math.max(1, G.W - G.P.l - G.P.r), span);
  }, {passive: false});
  $$('#h-rb button', box).forEach(b => b.addEventListener('click', () => {
    const m = +b.dataset.m; HC.btn = m;
    if (!m) { HC.f0 = 0; HC.f1 = last(); } else { HC.f1 = last(); HC.f0 = Math.max(0, last() - m + 1); if (HC.f1 - HC.f0 < 2) HC.f0 = Math.max(0, HC.f1 - 2); }
    hcDraw();
  }));
}
function hcDraw() {
  const svg = $('#h-svg'); if (!svg) return;
  const pts = HC.pts, W = 420, H = 140, P = {l: 46, r: 6, t: 8, b: 18}, f0 = HC.f0, f1 = HC.f1, span = Math.max(1, f1 - f0);
  const i0 = Math.max(0, Math.floor(f0)), i1 = Math.min(pts.length - 1, Math.ceil(f1)), vals = pts.slice(i0, i1 + 1).map(p => p[1]);
  let max = Math.max(...vals, 0), min = Math.min(...vals, 0); if (max === min) max = min + 1;
  if (HC.yr) [min, max] = HC.yr;
  const x = i => P.l + (i - f0) * (W - P.l - P.r) / span, y = v => P.t + (max - v) * (H - P.t - P.b) / (max - min), f = v => v.toFixed(1);
  let g = '';
  for (const [tk, ref] of axisTicks(min, max, 3)) g += `<line class="bch-grid${Math.abs(tk) < 1e-9 ? ' zero' : ''}" x1="${P.l}" x2="${W - P.r}" y1="${f(y(tk))}" y2="${f(y(tk))}"/><text class="bch-y" x="${P.l - 5}" y="${f(y(tk) + 4)}">${Fk(tk, false, ref)}</text>`;
  const ppm = (W - P.l - P.r) / span, step = [1, 2, 3, 6, 12, 24, 60, 120].find(st => st * ppm >= 52) || 120;
  for (let i = i0; i <= i1; i++) {
    const mk = pts[i][0], mo = +mk.slice(5), yr = +mk.slice(0, 4), xi = x(i);
    if (mo === 1 && xi > P.l) g += `<line class="bch-year" x1="${f(xi)}" x2="${f(xi)}" y1="${P.t}" y2="${H - P.b}"/>`;
    const lab = step < 12 ? (mo - 1) % step === 0 : mo === 1 && yr % (step / 12) === 0;
    if (lab && xi > P.l + 12 && xi < W - 14) g += `<text class="bch-x" x="${f(xi)}" y="${H - 4}">${step < 12 ? (mo === 1 ? yr : MONATE[mo - 1] + ' ' + String(yr).slice(2)) : yr}</text>`;
  }
  const line = pts.slice(i0, i1 + 1).map((p, k) => (k ? 'L' : 'M') + f(x(i0 + k)) + ' ' + f(y(p[1]))).join(''), yb = f(Math.max(P.t, Math.min(H - P.b, y(0))));
  g += `<clipPath id="h-clip"><rect x="${P.l}" y="${P.t}" width="${W - P.l - P.r}" height="${H - P.t - P.b}"/></clipPath>`
    + `<g clip-path="url(#h-clip)"><path class="h-area" d="${line}L${f(x(i1))} ${yb}L${f(x(i0))} ${yb}Z"/><path class="h-line" d="${line}"/></g>`
    + `<g class="h-hover"></g><rect class="bch-hit" x="${P.l}" y="0" width="${W - P.l - P.r}" height="${H - P.b}"/><rect class="bch-yax" x="0" y="0" width="${P.l - 2}" height="${H}"><title>${t('bch_yax_tip')}</title></rect>`
    + `<rect class="bch-pan" x="${P.l}" y="${H - P.b}" width="${W - P.l - P.r}" height="${P.b}"><title>${t('bch_pan_tip')}</title></rect>`;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.innerHTML = g;
  HC.geo = {W, H, P, x, y, min, max};
  $$('#h-rb button').forEach(b => b.classList.toggle('on', HC.btn != null && +b.dataset.m === HC.btn));
}
const HD = {uuid: null, live: false, r: null};
// hover text of a security: the name shown, MoneyMoney's own name (never lost, also after renaming) and the ISIN
function wpTip(w, acc) {
  if (w.rest) return w.name;
  const src = w.orig ? t('wp_in_mm', w.orig) : t('wp_in_mm_ohne');
  return [acc ? acc + ' · ' + w.name : w.name, w.isin ? 'ISIN ' + w.isin : '', w.orig !== w.name || !w.orig ? src : '',
    w.source === 'own_name' ? t('wp_eigener_name') : w.source === 'lookup' ? t('wp_nachgeschlagen') : ''].filter(Boolean).join('\n');
}
function openWpDrawer(id) {
  if (drawerAgain('wp:' + id)) return;
  // a security of a portfolio: its month-end values (from MoneyMoney's history, Kontor's record and the current export), with
  // MoneyMoney's name and the ISIN
  const D = B(); let acc = null, w = null;
  for (const r of D.balance.rows) { const x = (r.securities || []).find(p => p.id === id); if (x) { acc = r; w = x; break; } }
  if (!w) return;
  const d = $('#drawer'), pts = D.months.filter(m => w.amounts[m] != null).map(m => [m, w.amounts[m]]);
  d.innerHTML = `<button class="close icon">✕</button><h2>${esc(w.name)}</h2><div data-ex="drawer.security"><div class="small muted">${esc(acc.name)}${w.isin ? ' · ISIN ' + esc(w.isin) : ''}</div>
    ${w.rest ? '' : `<div class="small muted">${esc(w.orig ? t('wp_in_mm', w.orig) : t('wp_in_mm_ohne'))}${w.source === 'own_name' ? ' · ' + t('wp_eigener_name') : w.source === 'lookup' ? ' · ' + t('wp_nachgeschlagen') : ''}</div>`}
    <div class="h-chart" id="h-chart" data-ex="drawer.chart">${histChart(pts)}</div>
    <h3>${t('monatsstaende')}</h3><div class="hist-grid" id="h-grid">${pts.map(([mk, v]) => `<label>${ML(mk)}<input type="text" class="auto" value="${F(v)}" disabled></label>`).join('')}</div></div>`;
  d.classList.add('open');
  $('.close', d).onclick = closeDrawer;
  bindHistChart($('#h-chart', d), pts);
  const g = $('#h-grid', d); if (g) g.scrollTop = g.scrollHeight;
}
const pctQ = q => (q * 100).toLocaleString(LOCALE, {minimumFractionDigits: 1, maximumFractionDigits: 1}) + ' %';
function openEkqDrawer(mk) {
  // the equity ratio of a month, step by step: equity, own debts, the share of each company's debts, the ratio
  if (drawerAgain('ekq:' + mk)) return;
  const EQ = ((B() || {}).balance || {}).equity_ratio, e = EQ && EQ.months[mk], d = $('#drawer'); if (!e) return;
  const row = (l, v, c = '') => `<tr class="${c}"><td>${l}</td><td class="num">${v == null ? '–' : F0(v) + ' €'}</td></tr>`;
  const sub = list => list.map(([n, v]) => `<tr class="muted ind1"><td>${esc(n)}</td><td class="num">${F0(v)} €</td></tr>`).join('');
  const pct = a => (a * 100).toLocaleString(LOCALE, {maximumFractionDigits: 2}) + ' %';
  let h = row(t('nettovermoegen'), e.nw) + (e.capital_amount ? row(t('ekq_kapital'), e.capital_amount) : '') + row(t('ekq_ek'), e.equity_value, 'total')
    + row(t('ekq_eigene'), e.own) + sub(e.accounts);
  for (const f of e.businesses) h += row(t('ekq_firma', esc(f.name), pct(f.share), F0(f.debts) + ' €'), f.pro_rata) + sub(f.accounts);
  h += row(t('ekq_schulden'), e.debts, 'total') + row(t('ekq_vermoegen'), e.equity_value + e.debts)
    + `<tr class="total"><td>${t('ekq_quote')}</td><td class="num">${e.quote == null ? t('unbekannt') : pctQ(e.quote)}</td></tr>`;
  const ohne = EQ.without_lookthrough || [];
  d.innerHTML = `<button class="close icon">✕</button><h2>${t('ekq')} ${alphaTag()}</h2><div data-ex="drawer.ekq"><div class="muted">${MONATE_LANG[+mk.slice(5) - 1]} ${mk.slice(0, 4)}</div>
    <div class="note">${t('ekq_note')}</div><div class="wrap auto"><table class="plain small ekq-tbl"><tbody>${h}</tbody></table></div>
    <div class="note">${t('ekq_regeln')}</div>`
    + (ohne.length ? `<div class="note warn">${t(ohne.length === 1 ? 'ekq_ohne_1' : 'ekq_ohne_n', ohne.map(esc).join(', '))}</div>` : '')
    + (e.unknown.length ? `<div class="note warn">${t('ekq_unbekannt', e.unknown.map(esc).join(', '))}</div>` : '') + '</div>';
  d.classList.add('open');
  $('.close', d).onclick = closeDrawer;
}
function openTransitDrawer(m) {
  if (!m && drawerAgain('transit')) return;
  // Geldtransit: die erkannten Umbuchungen, deren Ab- und Gutschrift in verschiedene Monate fallen -- from a month's figure only those
  // under way at its end (one side booked by then, the other after)
  const r = ((B() || {}).balance || {rows: []}).rows.find(x => x.transit); if (!r) return;
  const end = m ? monthEnd(m) : null, open = u => (u.out_date <= end) !== (u.in_date <= end);
  const list = (r.transfers || []).slice().reverse().filter(u => !m || open(u)), d = $('#drawer');
  const head = m ? `<div class="note"><b>${esc(t('transit_ende', MLL(m)))}</b> ${F((r.amounts || {})[m] || 0)} · <a href="#" id="tr-all">${t('alle_zeigen')}</a></div>` : '';
  d.innerHTML = `<button class="close icon">✕</button><h2>${esc(r.name)}</h2><div data-ex="drawer.transit">${head}<div class="note">${t('geld_unterwegs_tip')}</div>
    <div class="wrap auto"><table class="plain small"><thead><tr><th>${t('abgebucht')}</th><th>${t('gutgeschrieben')}</th><th class="num">${t('betrag')}</th></tr></thead><tbody>`
    + list.map(u => `<tr><td>${FD(u.out_date)}<div class="muted">${esc(u.from_account)}</div></td><td>${FD(u.in_date)}<div class="muted">${esc(u.to_account)}</div></td><td class="num">${F(u.amount)}</td></tr>`).join('')
    + (list.length ? '' : `<tr><td colspan="3" class="muted">${t('transit_keine')}</td></tr>`) + `</tbody></table></div></div>`;
  d.classList.add('open'); DRW.key = 'transit';
  $('.close', d).onclick = closeDrawer;
  const all = $('#tr-all', d); if (all) all.onclick = e => { e.preventDefault(); openTransitDrawer(); };
}
// typed in and not saved: a month's balance (also one typed into a grey field, which is saved as your own) or a pasted list
const histTyped = d => $$('#h-grid input:not([disabled])', d).some(i => i.value !== i.defaultValue);
const drawerDirty = () => histTyped($('#drawer')) || !!($('#drawer #h-csv') && $('#drawer #h-csv').value.trim());

// ---------------------------------------------------------------- Bilanz
function vBilanz() {
  // Eine Tabelle: Positionen (farbig, aufklappbar) mit ihren Konten; Plan-Spalten rechts angehängt
  const D = B(); if (!D) return noData;
  const C = cols(null, true);
  const pr = D.balance.projection || null;
  const proj = pr ? Object.fromEntries(pr.rows.map(r => [r.id, r.amounts])) : {};
  const W = new Map(), werte = r => { if (!W.has(r.id)) W.set(r.id, proj[r.id] ? Object.assign({}, r.amounts, proj[r.id]) : r.amounts); return W.get(r.id); };
  const nw = pr ? Object.assign({}, D.balance.net_worth, pr.net_worth) : D.balance.net_worth;
  const pos = D.balance.rows.filter(r => r.group);
  S.posOpen = S.posOpen || {};
  const allOpen = pos.length && pos.every(r => S.posOpen[r.role]);
  S.depOpen = S.depOpen || {};                          // portfolios opened into their securities (each on its own)
  const ord = bilBlocks(), at = ord.indexOf('table');
  // top: the view (months/years) for chart and table; the table options sit in its header cell (no gap to the chart)
  const top = `<div class="toolbar" data-ex="balance.toolbar">${viewCtl()}${yearCtl()}<span class="sp"></span>${viewBtns()}${xlsxBtn('balance')}</div>`, chart = vBilanzChart(D);
  let h = '';                                           // the table (placed above, between or below the charts, see the end)
  const tag = r => (r.offline && !r.group ? `<span class="tag">${t('manuell')}</span>` : '') + (hidden(r) ? `<span class="tag">${t('ausgeblendet')}</span>` : '')
    + (r.projected_before ? `<span class="tag warn" title="${t('vor_0_ist_kein_stand', ML(r.projected_before))}">${t('vor_0_unbekannt', ML(r.projected_before))}</span>` : '');
  const row = (r, cls0, label, ex = '') => `<tr class="${cls0}" data-id="${r.id}" ${ex}><td title="${esc(r.path || r.name)}">${label}</td>${C.map(c => { const v = lastOf(werte(r), c.months); return `<td class="${cls(v, c)}">${FC(v)}</td>`; }).join('')}</tr>`;
  // hidden: what you hid yourself, and whatever is empty in every column shown -- an account idle today (auto-inactive) shows
  // where it still had a balance in the months on screen
  const autoIdle = new Set(D.accounts_inactive_auto || []), empty = r => C.every(c => { const v = lastOf(werte(r), c.months); return v == null || Math.abs(v) < 0.005; });
  const hidden = r => (r.inactive && !autoIdle.has(r.id)) || empty(r);
  // securities like accounts: hidden when empty in all columns or without a value for the inactivity period (sold long ago)
  const inakt = +((S.CFG || {}).balance || {}).inactive_months || 12, recent = D.months.slice(-inakt);
  const secHidden = w => C.every(c => { const v = lastOf(w.amounts, c.months); return v == null || Math.abs(v) < 0.005; }) || !recent.some(m => w.amounts[m] != null && Math.abs(w.amounts[m]) >= 0.005);
  // hidden securities count only where their position is open (the eye shows what this view can show)
  const nSecHid = D.balance.rows.reduce((n, r) => n + (S.posOpen[r.role] ? (r.securities || []).filter(secHidden).length : 0), 0);
  const skip = r => !S.alleB && hidden(r), anyHidden = D.balance.rows.some(r => !r.group && hidden(r)) || nSecHid > 0;
  // header cell: ▸/▾ expands or collapses all positions, the eye also shows empty and hidden accounts and securities (only when there are any)
  const nHid = D.balance.rows.filter(r => !r.group && hidden(r)).length + nSecHid;
  const first = `<div class="th-first"><button class="th-btn" id="pos-all" title="${allOpen ? t('nur_positionen') : t('konten_zeigen')}">${allOpen ? '▾' : '▸'}</button><span>${t('position_konto')}</span>${hq('bilanz_tabelle')}`
    + `<button class="th-mv" data-blk="table" data-mv="-1" title="${t('tbl_hoch')}"${at === 0 ? ' disabled' : ''}>↑</button><button class="th-mv" data-blk="table" data-mv="1" title="${t('tbl_runter')}"${at === 2 ? ' disabled' : ''}>↓</button><span class="sp"></span>`
    + (anyHidden ? `<label class="th-hid${S.alleB ? ' on' : ''}" title="${t('alle_zeilen_tip_n', nHid)}"><input type="checkbox" id="alle-zeilen" ${S.alleB ? 'checked' : ''}>${S.alleB ? ICON.eye : ICON.eyeOff}${nHid}</label>` : '') + `</div><span class="col-grip" title="${t('spalte_breite')}"></span>`;
  h += `<div class="wrap bil-tbl" data-ex="balance.table"${S.bilW ? ` style="--bil-w:${S.bilW}px"` : ''}><table>` + thead(first, C) + '<tbody>';
  for (const r of D.balance.rows) {
    if (r.group) {
      const [label, color] = ROLE[r.role] || [r.name, 'var(--c-neutral)'], open = !!S.posOpen[r.role];
      // number of accounts; "shown/all" when empty or hidden ones are left out (explained in the help of the header cell)
      const accs = D.balance.rows.filter(x => !x.group && x.role === r.role), shown = accs.filter(x => !skip(x)).length;
      if (!S.alleB && accs.length && !shown && empty(r)) continue;          // nothing in it in the months shown: the position too
      const cnt = shown < accs.length ? `<span class="small muted cnt" title="${t('n_von_m_konten', shown, accs.length)}">(${shown}/${accs.length})</span>` : `<span class="small muted cnt">(${accs.length})</span>`;
      h += row(r, 'group pos', `<span class="caret">${open ? '▾' : '▸'}</span><i class="pos-dot" style="background:${color}"></i>${label} ${cnt}`, 'data-ex="balance.table.pos"').replace('<tr ', `<tr data-pos="${r.role}" `).replace(` data-id="${r.id}"`, '');
      continue;
    }
    if (!S.posOpen[r.role] || skip(r)) continue;
    const shKey = `${(ROLE[r.role] || [0, 'var(--c-neutral)'])[1]}|${accIdx(D, r)}`;          // (to colour it again in another theme: printing)
    const sh = accShade((ROLE[r.role] || [0, 'var(--c-neutral)'])[1], accIdx(D, r)), dot = `<i class="pos-dot" data-sh="${esc(shKey)}" style="${swatch(sh.color, sh.hatch)}"></i>`;      // shade as in the chart
    if (r.transit) { h += row(r, 'ind1 transit clickable', `${dot}${esc(r.name)} ${hq('geld_unterwegs')}`, 'data-ex="balance.table.transit"'); continue; }
    const wp = r.securities && r.securities.length ? r.securities : null, dOpen = wp && S.depOpen[r.id];
    // a portfolio: number of its securities, like the accounts of a position ("shown/all" when some are hidden)
    const wn = wp ? wp.filter(w => !w.rest).length : 0, wv = wp ? wp.filter(w => !w.rest && !(!S.alleB && secHidden(w))).length : 0;
    const wcnt = wp ? ` <span class="small muted cnt"${wv < wn ? ` title="${t('n_von_m_wp', wv, wn)}"` : ''}>(${wv < wn ? wv + '/' + wn : wn})</span>` : '';
    h += row(r, 'clickable acct ind1', (wp ? `<span class="caret dep" data-dep="${esc(r.id)}" title="${t(dOpen ? 'wp_zuklappen' : 'wp_aufklappen')}">${dOpen ? '▾' : '▸'}</span>` : '') + dot + `<span class="nm">${esc(r.name)}</span>` + wcnt + tag(r), 'data-ex="balance.table.account"');
    // securities of an expanded portfolio (shades of the account colour, as in the charts); long names shortened, full on hover
    if (dOpen) wp.forEach((w, j) => { if (!S.alleB && secHidden(w)) return; const ws = accShade(sh.color, j + 1);
      h += `<tr class="wpr clickable ind2${w.rest ? ' muted' : ''}" data-wp="${esc(w.id)}" data-ex="balance.table.security"><td title="${esc(wpTip(w))}"><i class="pos-dot" data-sh="${esc(shKey + '|' + (j + 1))}" style="${swatch(ws.color, ws.hatch)}"></i><span class="nm">${esc(w.name)}</span></td>${cells(C, c => lastOf(w.amounts, c.months))}</tr>`; });
    if (pr && r.role === 'participations' && proj.contributions && r === D.balance.rows.filter(x => !x.group && x.role === 'participations').slice(-1)[0])
      h += row({id: 'contributions', name: t('einlagen_entnahmen_kumuliert_plan'), amounts: {}}, 'ind1 muted', t('einlagen_entnahmen_beteiligungen_kumul'), 'data-ex="balance.table.contributions"');
  }
  // key figures under net worth (equity ratio, alpha): folded by default, the name of net worth opens them like a position
  const EQ = D.balance.equity_ratio, kpi = !!(EQ && Object.keys(EQ.months || {}).length), kOpen = kpi && !!S.posOpen._kennzahlen;
  h += `<tr class="total${kpi ? ' fold' : ''}" data-ex="balance.table.nw"><td${kpi ? ` title="${t(kOpen ? 'kennzahlen_zu' : 'kennzahlen_auf')}"` : ''}>${kpi ? `<span class="caret">${kOpen ? '▾' : '▸'}</span>` : ''}<i class="nw-sw"></i>${t('nettovermoegen')}</td>${cells(C, c => lastOf(nw, c.months))}</tr>`;
  // equity ratio (alpha): looking through the companies; actual months only, a click shows the calculation
  if (kOpen) {
    const at = c => { if (c.plan) return null; for (let k = c.months.length - 1; k >= 0; k--) if (EQ.months[c.months[k]]) return c.months[k]; return null; };
    h += `<tr class="ekq ind1" data-ex="balance.table.ekq"><td title="${esc(t('ekq_tip'))}">${t('ekq')} ${alphaTag()}</td>${C.map(c => { const mk = at(c), e = mk && EQ.months[mk];
      return `<td class="${cls(1, c).replace(' pos', '')}"${mk ? ` data-m="${mk}"` : ''}>${!e ? '' : e.quote == null ? `<span title="${esc(t('unbekannt'))}">?</span>` : pctQ(e.quote)}</td>`; }).join('')}</tr>`;
  }
  // outside net worth (guarantees, capital accounts as equity): one collapsible row per kind with its sum, accounts on click
  const out = D.balance.outside || [];
  for (const role of [...new Set(out.map(r => r.role))]) {
    const fx = role === 'foreign_currency', accs = out.filter(r => r.role === role), open = !!S.posOpen[role], [label, color] = fx ? [t('fremdwaehrung_nicht_umgerechnet'), 'var(--c-neutral)'] : ROLE[role] || [role, 'var(--c-neutral)'];
    const sum = c => { if (fx) return null; let v = null; for (const r of accs) { const x = lastOf(r.amounts, c.months); if (x != null) v = (v || 0) + x; } return v; };       // other currencies: no sum
    h += `<tr class="group pos muted" data-pos="${role}" data-ex="balance.table.outside"><td><span class="caret">${open ? '▾' : '▸'}</span><i class="pos-dot" style="background:${color}"></i>${esc(label)} <span class="small muted cnt">(${accs.length})</span> <span class="tag">${t('nicht_im_nw_kurz')}</span></td>${cells(C, sum)}</tr>`;
    if (open) h += accs.map(r => `<tr class="muted ind1" data-ex="balance.table.outside"><td title="${esc(r.path || r.name)}">${esc(r.name)}${fx ? ` <span class="tag">${esc(r.currency)}</span>` : ''}</td>${cells(C, c => lastOf(r.amounts, c.months))}</tr>`).join('');
  }
  h += '</tbody></table></div>';
  // the order of large chart, table and small charts (default in this order; table and large chart can be moved up and down)
  const parts = {chart, table: h, lines: vBilanzLines(D)};
  return top + ord.map(k => parts[k]).join('');
}

// ---------------------------------------------------------------- Bilanz-Grafik (Zusammensetzung im Zeitverlauf)
const MONATE_LANG = LANG === 'en' ? ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
  : ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
const BCH = {d: null, i0: 0, i1: 0, drag: null, hover: null, ro: null};
// colour of an account inside its position (same in the charts and the table): variants of the position colour with a
// neighbouring hue and a different lightness, so that up to ten accounts stay apart without turning into a rainbow;
// beyond that the variants repeat hatched. Computed in OKLCH (perceptually even), so the steps look alike in every colour.
const ACC_STEPS = [[0, 0], [22, -.13], [-22, .09], [40, .02], [-40, -.08], [11, .15], [-11, -.18], [32, .12], [-32, -.02], [0, -.24]];   // [hue °, lightness]
const accIdx = (D, r) => Math.max(0, D.balance.rows.filter(x => !x.group && x.role === r.role).indexOf(r));
const cssColor = c => c.startsWith('var(') ? getComputedStyle(document.documentElement).getPropertyValue(c.slice(4, -1)).trim() : c;
function hexToOklch(hex) {
  const n = parseInt(hex.slice(1), 16), [r, g, b] = [n >> 16, (n >> 8) & 255, n & 255].map(v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b), m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b), q = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * q, A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * q, B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * q;
  return [L, Math.hypot(A, B), Math.atan2(B, A) * 180 / Math.PI];
}
function oklchToHex(L, C, H) {
  for (let c = C; c >= 0; c -= 0.005) {                 // outside sRGB: reduce the chroma until it fits
    const a = c * Math.cos(H * Math.PI / 180), b = c * Math.sin(H * Math.PI / 180);
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, q = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
    const rgb = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * q, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * q, -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * q];
    if (rgb.every(v => v >= -0.001 && v <= 1.001)) return '#' + rgb.map(v => { v = Math.min(1, Math.max(0, v)); v = v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055; return Math.round(v * 255).toString(16).padStart(2, '0'); }).join('');
  }
  return '#8e8e93';
}
const ACC_CACHE = new Map();
function accShade(color, i) {
  const base = cssColor(color), k = base + '|' + i;
  if (!ACC_CACHE.has(k)) {
    let c = color;
    if (/^#[0-9a-f]{6}$/i.test(base)) { const [L, C, H] = hexToOklch(base), [dh, dl] = ACC_STEPS[i % ACC_STEPS.length]; c = i ? oklchToHex(Math.min(.9, Math.max(.35, L + dl)), C, H + dh) : base; }
    ACC_CACHE.set(k, {color: c, hatch: i >= ACC_STEPS.length});
  }
  return ACC_CACHE.get(k);
}
const swatch = (color, hatch) => `background:${hatch ? `repeating-linear-gradient(135deg, ${color} 0 2px, transparent 2px 4px)` : color}`;
function bchData(D) {
  // the large chart: the balance sheet (default) or one of the small charts moved up
  const type = bigType();
  if (type === 'nw') { const x = lcData(D, null); return {months: x.months, ist: x.ist, series: [], nw: x.vals, lineLabel: t('nettovermoegen'), adaptive: true}; }
  if (type === 'sel') {
    const {sel, avail} = lcSelection(D), x = lcData(D, sel);
    return {months: x.months, ist: x.ist, series: [], parts: x.parts || [], nw: x.vals, lineLabel: lcSelTitle(sel, avail, true)[0], lineColor: lcMix(sel), adaptive: true};
  }
  if (type === 'pos') {
    const rolle = lcPosRole(D); if (!rolle) return {months: [], series: [], nw: []};
    const mode = lcPosMode(D, rolle), x = lcStack(D, rolle, mode), off = lcOffSet('pos', rolle + '|' + mode);
    return {months: x.months, ist: x.ist, series: x.series.filter(z => !off.has(z.key)).map(z => Object.assign({op: 1, sub: true}, z)), all: x.series, off,
            nw: x.vals, lineLabel: ROLE[rolle][0], lineColor: ROLE[rolle][1]};
  }
  return bchBilanz(D);
}
function bchBilanz(D) {
  // Positionen (Farben wie in der Tabelle), Ist + Plan; aufgeklappte Positionen zeigen ihre Konten (Abstufungen der Farbe)
  const pr = D.balance.projection || null, proj = pr ? Object.fromEntries(pr.rows.map(r => [r.id, r.amounts])) : {};
  const months = [...D.months, ...(pr ? (D.plan_months || []) : [])];
  const vals = r => { const w = Object.assign({}, r.amounts, proj[r.id] || {}); return months.map(m => w[m] == null ? null : w[m] * defl(m)); };
  const series = [];
  for (const r of D.balance.rows.filter(x => x.group && ROLE[x.role])) {
    const [label, color] = ROLE[r.role];
    const accs = (S.posOpen || {})[r.role] ? D.balance.rows.filter(x => !x.group && x.role === r.role) : [];
    accs.forEach((a, i) => {
      const sh = accShade(color, i), wp = (S.depOpen || {})[a.id] && a.securities && a.securities.length ? a.securities : null;
      if (!wp) { series.push(Object.assign({role: r.role, acc: a.id, dep: !!(a.securities && a.securities.length), label: a.name, op: 1, sub: true, vals: vals(a)}, sh)); return; }
      // a portfolio opened in the table: its securities; months without any known security (and the plan) as the portfolio itself
      const known = months.map((m, k) => k < D.months.length && wp.some(p => p.amounts[m] != null));
      wp.forEach((p, j) => series.push(Object.assign({role: r.role, acc: a.id, wp: p.id, label: p.name, full: wpTip(p, a.name), op: 1, sub: true, vals: months.map((m, k) => known[k] ? p.amounts[m] ?? null : null)}, accShade(sh.color, j + 1))));
      series.push(Object.assign({role: r.role, acc: a.id, dep: true, label: a.name, op: 1, sub: true, vals: vals(a).map((v, k) => known[k] ? null : v)}, sh));
    });
    if (!accs.length) series.push({role: r.role, pos: true, label, color, op: 1, vals: vals(r)});
  }
  const nwAll = pr ? Object.assign({}, D.balance.net_worth, pr.net_worth) : D.balance.net_worth;
  return {months, ist: D.months.length, series: series.filter(x => x.vals.some(v => v != null && Math.abs(v) >= 0.005)), nw: months.map(m => nwAll[m] == null ? null : nwAll[m] * defl(m))};
}
function vBilanzChart(D) {
  const d = bchData(D); if (d.months.length < 2 || (!d.series.length && !d.nw.some(v => v != null))) return '';
  BCH.d = d;
  // range kept as months (survives rebuilds and area changes; null = all); a button alone is anchored to today
  const dflt = bigDefault();
  if (S.bchModus !== S.mode) { S.bchModus = S.mode; viewBchRange((viewSaved(S.mode) || {}).bch); }      // view switched: its saved or Kontor's default range
  const r = S.bchRange, n = d.months.length, rb = bchRanges(true);
  let i0 = -1, i1 = -1;
  if (S.bchLen) { [i0, i1] = bchWindow(d, S.bchLen); S.bchBtn = null; S.bchLen = null; }       // kept as a length, ending today
  else if (r === null) { i0 = 0; i1 = n - 1; }
  else if (r) { i0 = d.months.indexOf(r[0]); i1 = d.months.indexOf(r[1]); }
  if ((i0 < 0 || i1 <= i0) && S.bchBtn) [i0, i1] = bchBigWindow(d, S.bchBtn);
  if (i0 < 0 || i1 <= i0) { [i0, i1] = bchBigWindow(d, dflt); S.bchBtn = dflt; }          // default: 1 year (months) or 5 years (years)
  S.bchRange = i0 === 0 && i1 === n - 1 ? null : [d.months[i0], d.months[i1]];
  if (i0 !== BCH.i0 || i1 !== BCH.i1) BCH.sh = 0;         // the shift of a clicked column only while the range stays
  BCH.i0 = BCH.f0 = i0; BCH.i1 = BCH.f1 = i1;
  const type = bigType(), {avail, sel} = lcSelection(D), pr = lcPosRole(D);
  // what the chart shows, in Kontor's description of the page (docs/ui/balance.md): the balance sheet, or a small chart shown large
  const tex = type === 'nw' ? 'data-ex="balance.nw"' : type === 'sel' ? 'data-ex="balance.sel"' : type === 'pos' ? 'data-ex="balance.pos"' : 'data-ex="balance.bil"';
  const title = type === 'nw' ? `<b class="bch-title" ${tex}>${t('nettovermoegen')}</b>`
    : type === 'sel' ? (([tx, tip]) => `<b class="bch-title${tip ? ' tipped' : ''}" ${tex} data-tip="${esc(tip)}" tabindex="0">${esc(tx)}</b>`)(lcSelTitle(sel, avail, true))
    : type === 'pos' ? `<select id="big-pos-sel" class="lc-pos-sel" title="${t('lc_pos_tip')}">${avail.map(r => `<option value="${r}" ${r === pr ? 'selected' : ''}>${esc(ROLE[r][0])}</option>`).join('')}</select>${pr && lcHasDepot(D, pr) ? `<button class="lc-mode${lcPosMode(D, pr) === 'depot' ? ' on' : ''}" id="big-pos-mode" title="${t('lc_depot_tip')}">${t('lc_depot')}</button>` : ''}`
    : '';
  const below = type === 'sel' ? `<div class="lc-chips below" id="big-chips" ${tex}>${avail.map(r => `<label class="lc-chip"><input type="checkbox" data-r="${r}" ${sel.includes(r) ? 'checked' : ''}><i style="background:${ROLE[r][1]}"></i>${esc(ROLE[r][0])}</label>`).join('')}</div>`
    : type === 'pos' ? `<div class="lc-chips below" id="big-accs" ${tex}></div>` : '';
  return `<div class="card bch${bchLinked() ? ' linked' : ''}${type !== 'balance' ? ' big-' + type : ''}" id="bch" data-ex="balance.chart"><div class="bch-head">${title}<span class="bch-range${type !== 'balance' ? ' sub' : ''}" id="bch-range"></span> ${hq('bch')}${((k) => `<button class="th-mv" data-blk="chart" data-mv="-1" title="${t('grafik_hoch')}"${k === 0 ? ' disabled' : ''}>↑</button><button class="th-mv" data-blk="chart" data-mv="1" title="${t('grafik_runter')}"${k === 2 ? ' disabled' : ''}>↓</button>`)(bilBlocks().indexOf('chart'))}<span class="sp"></span><button class="ghost small bch-link${bchLinked() ? ' on' : ''}" id="bch-link" title="${t('bch_link_tip')}" aria-pressed="${bchLinked()}">${t('bch_link')}</button>${type === 'balance' ? `<button class="lc-mode bch-plan-tg${S.bchPlan !== false ? ' on' : ''}" id="bch-plan" title="${t('bch_plan_tip')}">${t('plan')}</button>` : ''}<label class="bch-n" title="${t('bch_monate_tip')}"><input type="number" id="bch-n" min="1" max="${n - 1}" step="1">${t('bch_m')}</label><div class="seg small" id="bch-rb">${rb.map(([m, l]) => `<button data-m="${m}">${l}</button>`).join('')}</div></div>${type !== 'balance' ? `<div class="lc-row2 bch-row2" ${tex}><span class="lc-val" id="bch-val" data-ex="balance.value"></span></div>` : ''}
    <div class="bch-plot" id="bch-plot" ${tex}><svg class="bch-svg" id="bch-svg"></svg><div class="bch-tip hidden" id="bch-tip"></div></div>${below}</div>`;
}
function bchDraw() {
  const box = $('#bch-plot'), svg = $('#bch-svg'), d = BCH.d; if (!box || !svg || !d) return;
  const W = Math.max(320, box.clientWidth), H = window.matchMedia('(max-width:820px)').matches ? 200 : 250;
  // points to draw: the months of the range, or (aligned with the table) the table's columns at their positions
  const link = bchLinked() ? bchCols(svg) : null, i0 = BCH.i0, i1 = BCH.i1, n = i1 - i0;
  // shift by a fraction of a month (a clicked table column: its month lands exactly above it); the neighbours fill the edges
  const sh = link ? 0 : BCH.sh || 0, last = d.months.length - 1;
  // aligned: the plot uses the full width on the left too (above the row labels of the table it shows the columns scrolled out there)
  const P = link ? {l: 58, r: Math.max(10, W - link.r), t: 8, b: 24} : {l: 58, r: 10, t: 8, b: 24};
  const pts = link ? link.cols : [];
  if (!link) for (let i = Math.max(0, i0 - (sh < 0 ? 1 : 0)); i <= Math.min(last, i1 + (sh > 0 ? 1 : 0)); i++) pts.push({i, x: P.l + (i - i0 - sh) * (W - P.l - P.r) / Math.max(1, n)});
  const N = pts.length - 1;
  // Stapel: positive Anteile von der Nulllinie nach oben, negative nach unten (Reihenfolge wie die Tabelle von oben)
  // the scale follows what is in view (aligned: the visible columns and one beyond each edge)
  let kA = 0, kB = N;
  if (link) { const vis = pts.map((p, k) => p.x >= P.l - 0.5 && p.x <= W - P.r + 0.5 ? k : -1).filter(k => k >= 0); if (vis.length) { kA = Math.max(0, vis[0] - 1); kB = Math.min(N, vis[vis.length - 1] + 1); } }
  const inView = pts.slice(kA, kB + 1), pos = [], neg = [];
  for (const p of inView) { let up = 0, dn = 0; for (const x of d.series) { const v = x.vals[p.i] || 0; if (v > 0) up += v; else dn += v; } pos.push(up); neg.push(dn); }
  const nwv = inView.map(p => d.nw[p.i]).filter(v => v != null);
  let max = Math.max(...pos, ...nwv, 0), min = Math.min(...neg, ...nwv, 0);
  if (d.adaptive && nwv.length) { max = Math.max(...nwv); min = Math.min(...nwv); }          // a single line: the axis follows its values
  if (max - min < 1) { max += 50; min -= 50; }
  const pad = (max - min) * (d.adaptive ? 0.08 : 0.04); max += pad; if (min < 0 || d.adaptive) min -= pad;
  if (S.bchYr) [min, max] = S.bchYr;                    // range set on the y axis (a tap there resets it)
  const x = i => P.l + (i - i0 - sh) * (W - P.l - P.r) / Math.max(1, n), y = v => P.t + (max - v) * (H - P.t - P.b) / (max - min);
  const pf = v => v.toFixed(1);
  let g = `<rect class="bch-bg" x="${P.l}" y="${P.t}" width="${Math.max(0, W - P.l - P.r)}" height="${H - P.t - P.b}"/>`;
  for (const [t, ref] of axisTicks(min, max, H < 220 ? 5 : 6, 5)) g += `<line class="bch-grid${Math.abs(t) < 1e-9 ? ' zero' : ''}" x1="${P.l}" x2="${W - P.r}" y1="${pf(y(t))}" y2="${pf(y(t))}"/><text class="bch-y" x="${P.l - 6}" y="${pf(y(t) + 4)}">${Fk(t, true, ref)}</text>`;
  let plot = '';                                        // everything that is clipped to the plot when aligned with the table
  if (link) {
    // time axis: the column labels of the table (thinned out when the columns are narrow)
    const cw = N > 0 ? Math.abs(pts[1].x - pts[0].x) : 60, step = Math.max(1, Math.ceil(54 / Math.max(1, cw)));
    pts.forEach((p, k) => {
      const xi = pf(p.x), jan = p.key.length === 7 && p.key.endsWith('-01');
      if (jan && k > 0) plot += `<line class="bch-year" x1="${xi}" x2="${xi}" y1="${P.t}" y2="${H - P.b}"/>`;
      plot += `<line class="bch-tick" x1="${xi}" x2="${xi}" y1="${H - P.b}" y2="${H - P.b + (jan ? 5 : 3)}"/>`;
      if (k % step === 0 && p.x > P.l + 12 && p.x < W - P.r - 12) g += `<text class="bch-x" x="${xi}" y="${H - 6}">${esc(p.label)}</text>`;
    });
  } else {
    // Zeitachse: erster und letzter Monat immer beschriftet, dazwischen je nach Ausschnitt (Monate bis Jahrzehnte)
    g += monthAxis(d, i0 + (sh > 0 ? 1 : 0), i1 - (sh < 0 ? 1 : 0), x, P, W, H, true);      // the months fully in view
  }
  // Flaechen
  const df = {s: ''};
  const band = (sel, sign) => {
    const base = Array(N + 1).fill(0); let out = '';
    for (const sx of sel) {
      const top = [], bot = [];
      for (let k = 0; k <= N; k++) { const v = sx.vals[pts[k].i] || 0, part = sign > 0 ? Math.max(0, v) : Math.min(0, v); bot.push(base[k]); base[k] += part; top.push(base[k]); }
      if (top.every((t, k) => Math.abs(t - bot[k]) < 0.005)) continue;
      const path = smoothD(top.map((t, k) => [pts[k].x, y(t)])) + smoothD(bot.map((b, k) => [pts[k].x, y(b)]), true) + 'Z';
      const fill = bandFill(df, `bch-${d.series.indexOf(sx)}`, sx.color, sx.hatch);
      out += `<path class="bch-area${sx.sub ? ' sub' : ''}" data-s="${d.series.indexOf(sx)}" d="${path}" fill="${fill}"${sx.op < 1 ? ` fill-opacity="${sx.op}"` : ''}/>`;
    }
    return out;
  };
  const ordered = d.series.slice().reverse();          // unterste Flaeche = letzte Position der Tabelle
  plot += band(ordered, 1) + band(ordered, -1);
  // the months: completed ones (solid), the running month (dotted and lightly shaded: data still coming in) and the plan (dashed,
  // shaded); the dashed vertical line marks the end of the last completed month
  const ist = d.ist - 1, done = ist - 1, kt = pts.findIndex(p => p.i === ist), kp = pts.findIndex(p => p.i > ist);
  const act = pts.filter(p => p.i <= done), runp = kt >= 0 ? pts.filter(p => p.i > done && p.i <= ist) : [];
  if (act.length && runp.length) runp.unshift(act[act.length - 1]);
  const shade = (cls0, xa, xb) => xb > xa ? `<rect class="${cls0}" x="${pf(xa)}" y="${P.t}" width="${pf(xb - xa)}" height="${H - P.t - P.b}"/>` : '';
  if (runp.length) { df.s += runGrad('bch-rung'); plot += shade('bch-run', Math.max(P.l, runp[0].x), pts[kt].x).replace('<rect ', '<rect fill="url(#bch-rung)" '); }
  if (kp >= 0) plot += shade('bch-plan', Math.max(P.l, kt >= 0 ? pts[kt].x : pts[kp].x), W - P.r);
  if (act.length && (act[act.length - 1].i === done || runp.length)) { const xd = act[act.length - 1].x; plot += `<line class="bch-today" x1="${pf(xd)}" x2="${pf(xd)}" y1="${P.t - 4}" y2="${H - P.b}"/>`; }
  // Nettovermoegen (bis heute durchgezogen, danach gestrichelt)
  const line = (sel, cls0, dot) => heroLine(sel.filter(p => d.nw[p.i] != null).map(p => [p.x, y(d.nw[p.i])]), cls0, d.lineColor, dot);
  if (d.adaptive) {                                     // a single line: filled towards zero, as in the small charts
    const act = pts.filter(p => p.i <= ist && d.nw[p.i] != null), yb = Math.max(P.t, Math.min(H - P.b, y(0)));
    if (act.length > 1) plot += `<path class="lc-area" d="${smoothD(act.map(p => [p.x, y(d.nw[p.i])]))}L${pf(act[act.length - 1].x)} ${pf(yb)}L${pf(act[0].x)} ${pf(yb)}Z" style="fill:${d.lineColor || 'var(--c-nw)'}"/>`;
  }
  plot += (kp >= 0 ? line(pts.filter(p => p.i >= ist), 'bch-nw plan') : '') + (runp.length ? line(runp, 'bch-nw run', true) : '') + line(act, 'bch-nw');
  let defs = df.s;
  if (link || S.bchYr || sh) { defs += `<clipPath id="bch-clip"><rect x="${P.l}" y="${S.bchYr ? P.t : 0}" width="${Math.max(0, W - P.l - P.r)}" height="${S.bchYr ? H - P.t - P.b : H}"/></clipPath>`; g += `<g clip-path="url(#bch-clip)">${plot}</g>`; } else g += plot;
  if (defs) g = `<defs>${defs}</defs>` + g;
  g += `<g id="bch-hover"></g><rect class="bch-sel hidden" id="bch-sel" y="${P.t}" height="${H - P.t - P.b}"/><rect class="bch-hit" id="bch-hit" x="${P.l}" y="0" width="${Math.max(0, W - P.l - P.r)}" height="${H}"/>`
    + `<rect class="bch-yax${S.bchYr ? ' on' : ''}" x="0" y="0" width="${P.l - 2}" height="${H}"><title>${t('bch_yax_tip')}</title></rect>`
    + (link ? '' : `<rect class="bch-pan" x="${P.l}" y="${H - P.b + 2}" width="${W - P.l - P.r}" height="${P.b - 2}"/>`);
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('width', W); svg.setAttribute('height', H); svg.innerHTML = g; svg.classList.remove('hl');
  BCH.geo = {W, H, P, x, y, min, max, inv: py => max - (py - P.t) * (max - min) / Math.max(1, H - P.t - P.b), idx: px => Math.max(i0, Math.min(i1, Math.round(i0 + sh + (px - P.l) * n / Math.max(1, W - P.l - P.r))))};
  const bv = $('#bch-val');
  if (bv) { let a = null, z = null; for (const p of pts) if (p.i <= ist && d.nw[p.i] != null && (!link || (p.x >= P.l && p.x <= W - P.r))) { if (a == null) a = p.i; z = p.i; } bv.innerHTML = valChange(d.nw, a, z); }
  const rl = $('#bch-range');
  if (rl && link) { const vis = pts.filter(p => p.x >= P.l && p.x <= W - P.r); rl.textContent = vis.length ? `${bchKeyLabel(vis[0].key)} – ${bchKeyLabel(vis[vis.length - 1].key)}` : ''; }
  else if (rl) rl.textContent = `${MONATE_LANG[+d.months[i0].slice(5) - 1]} ${d.months[i0].slice(0, 4)} – ${MONATE_LANG[+d.months[i1].slice(5) - 1]} ${d.months[i1].slice(0, 4)}`;
  $$('#bch-rb button').forEach(b => b.classList.toggle('on', S.bchBtn ? +b.dataset.m === S.bchBtn : S.bchRange === null && b.dataset.m === '0'));
  const nf = $('#bch-n'); if (nf && document.activeElement !== nf) nf.value = bchPastEnd(i0, i1) - i0;      // months up to the last completed month
  const ba = $('#big-accs');
  if (ba && d.all) {                                    // the large composition chart: accounts / securities to deselect
    const at = Math.min(i1, ist), inWin = d.all.filter(x => x.vals.slice(i0, i1 + 1).some(v => v != null && Math.abs(v) >= 0.005))
      .sort((a, b) => Math.abs(b.vals[at] || 0) - Math.abs(a.vals[at] || 0));
    const sn = shortNames(inWin.map(x => x.label), inWin.length <= 8 ? 24 : inWin.length <= 16 ? 14 : 10);
    ba.innerHTML = inWin.map((x, k) => `<label class="lc-chip" title="${esc(x.full || x.label)}"><input type="checkbox" data-k="${esc(x.key)}" ${d.off.has(x.key) ? '' : 'checked'}><i style="${swatch(x.color, x.hatch)}"></i><span class="nm">${esc(sn[k])}</span></label>`).join('');
  }
  bchBind();
  // a redraw (resize, new range) while the values are shown: show them again -- under the mouse, or the marked row
  const hov = BCH.hov; if (hov && !link) { if (hov.mark || !BCH.ptr) bchHover(Math.max(i0, Math.min(i1, hov.i)), hov.py, hov.mark); else bchRehover(); }
}
// Aligned with the table: the chart follows the table's columns (each value right above its column) and scrolls with it
function bchLinkPan(svg) {
  // swiping (trackpad) or dragging (mouse, finger) anywhere on the chart – plot and axes – scrolls the table sideways
  if (!svg || svg._lnk) return; svg._lnk = true;
  const tbl = () => bchLinked() ? $('#main .wrap.snap') : null;
  svg.addEventListener('wheel', e => { const w = tbl(); if (!w || e.target.classList.contains('bch-yax') || Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return; e.preventDefault(); tablePan(w, e.deltaX); }, {passive: false});
  let drag = null;
  svg.addEventListener('pointerdown', e => { if (!tbl() || e.button > 0 || e.target.classList.contains('bch-yax')) return; drag = {id: e.pointerId, x: e.clientX}; try { svg.setPointerCapture(e.pointerId); } catch (x) {} });
  svg.addEventListener('pointermove', e => { const w = tbl(); if (!drag || e.pointerId !== drag.id || !w) return; e.preventDefault(); tablePan(w, drag.x - e.clientX); drag.x = e.clientX; });
  const end = e => { if (drag && e.pointerId === drag.id) drag = null; };
  svg.addEventListener('pointerup', end); svg.addEventListener('pointercancel', end);
}
function tablePan(w, dx) {
  // move a snapping table freely (snapping off meanwhile), then let it settle on the nearest column
  if (!w._pan) { w._pan = true; w.style.scrollSnapType = 'none'; }
  w.scrollLeft += dx;
  clearTimeout(w._panT);
  w._panT = setTimeout(() => {
    w._pan = false;
    const sw = $('thead th', w).offsetWidth, max = w.scrollWidth - w.clientWidth, cur = w.scrollLeft;
    const starts = colHeads(w).map(th => Math.round(colX(w, th) - sw));
    const best = starts.reduce((b, v) => Math.abs(v - cur) < Math.abs(b - cur) ? v : b, 0);
    w.style.scrollSnapType = ''; w.scrollTo({left: Math.max(0, Math.min(max, best)), behavior: 'smooth'});
  }, 180);
}
const bchLinked = () => !!S.bchLink;
const bchKeyLabel = k => k.length === 4 ? k : `${MONATE_LANG[+k.slice(5) - 1]} ${k.slice(0, 4)}`;
function bchIndex(key) {
  // month index of a table column (year column: the current month for the running year, otherwise its last month)
  const d = BCH.d, i = d.months.indexOf(key); if (i >= 0 || key.length !== 4) return i;
  const cur = d.ist - 1; if (d.months[cur] && d.months[cur].startsWith(key + '-')) return cur;
  return d.months.reduce((k, m, j) => m.startsWith(key + '-') ? j : k, -1);
}
function bchCols(svg) {
  // the table's columns as points: month index and the x of the column centre in the chart; l/r = visible part of the table
  const w = $('#main .wrap.snap'), first = w && $('thead th', w), sr = svg.getBoundingClientRect(); if (!first || !sr.width) return null;
  const cols = [];
  for (const th of $$('thead th[data-key]', w)) { const i = bchIndex(th.dataset.key); if (i < 0) continue; const r = th.getBoundingClientRect(); cols.push({i, key: th.dataset.key, label: th.textContent.trim(), x: r.left + r.width / 2 - sr.left}); }
  return cols.length > 1 ? {cols, l: first.getBoundingClientRect().right - sr.left, r: w.getBoundingClientRect().left + w.clientLeft + w.clientWidth - sr.left} : null;
}
// range buttons by view: months → 6 M, 1 J, 2 J (+ all), years → 1 J, 3 J, 10 J (+ all); the small charts without "all"
const bchDefault = () => S.mode === 'years' ? 36 : 12;      // default range of all charts: months view 1 year, years view 3 years
const bigDefault = () => S.mode === 'years' ? 36 : 12;       // the large chart: months view 1 year, years view 3 years
function bchRanges(all) {
  // the large chart (all) has one more range (months: 3 years, years: 5 years) and "Alle"
  const y = S.mode === 'years';
  const r = y ? [[12, t('bch_jahre', 1)], [36, t('bch_jahre', 3)], ...(all ? [[60, t('bch_jahre', 5)]] : []), [120, t('bch_jahre', 10)]]
    : [[6, t('bch_monate_n', 6)], [12, t('bch_jahre', 1)], [24, t('bch_jahre', 2)], ...(all ? [[36, t('bch_jahre', 3)]] : [])];
  return all ? [...r, [0, t('alle')]] : r;
}
// smooth curve through the month ends (monotone cubic, Fritsch-Carlson): exact at every point and never beyond its neighbours,
// so no invented bumps; areas use the same curve for the shared edge of two neighbouring bands (forwards and backwards)
function smoothD(p, back) {
  const f = v => v.toFixed(1);
  if (p.length < 3) { const q = back ? p.slice().reverse() : p; return q.map((v, k) => (k || back ? 'L' : 'M') + f(v[0]) + ' ' + f(v[1])).join(''); }
  const n = p.length, dl = [], m = [];
  for (let k = 0; k < n - 1; k++) { const dx = p[k + 1][0] - p[k][0]; dl.push(dx ? (p[k + 1][1] - p[k][1]) / dx : 0); }
  for (let k = 0; k < n; k++) m.push(k === 0 ? dl[0] : k === n - 1 ? dl[n - 2] : dl[k - 1] * dl[k] <= 0 ? 0 : (dl[k - 1] + dl[k]) / 2);
  for (let k = 0; k < n - 1; k++) {
    if (!dl[k]) { m[k] = 0; m[k + 1] = 0; continue; }
    const a = m[k] / dl[k], b = m[k + 1] / dl[k], s = a * a + b * b;
    if (s > 9) { const tt = 3 / Math.sqrt(s); m[k] = tt * a * dl[k]; m[k + 1] = tt * b * dl[k]; }
  }
  const seg = [];
  for (let k = 0; k < n - 1; k++) { const dx = (p[k + 1][0] - p[k][0]) / 3; seg.push([p[k], [p[k][0] + dx, p[k][1] + m[k] * dx], [p[k + 1][0] - dx, p[k + 1][1] - m[k + 1] * dx], p[k + 1]]); }
  if (!back) return `M${f(p[0][0])} ${f(p[0][1])}` + seg.map(s => `C${f(s[1][0])} ${f(s[1][1])} ${f(s[2][0])} ${f(s[2][1])} ${f(s[3][0])} ${f(s[3][1])}`).join('');
  return `L${f(p[n - 1][0])} ${f(p[n - 1][1])}` + seg.reverse().map(s => `C${f(s[2][0])} ${f(s[2][1])} ${f(s[1][0])} ${f(s[1][1])} ${f(s[0][0])} ${f(s[0][1])}`).join('');
}
// a band of a stacked chart: its colour fading slightly downwards (depth without getting loud); hatched ones keep their pattern
function bandFill(defs, pid, color, hatch) {
  if (hatch) { if (!defs.s.includes(pid + 'p"')) defs.s += `<pattern id="${pid}p" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="2.5" height="5" style="fill:${color}"/></pattern>`; return `url(#${pid}p)`; }
  if (!defs.s.includes(pid + 'g"')) defs.s += `<linearGradient id="${pid}g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style="stop-color:${color}"/><stop offset="1" style="stop-color:${color};stop-opacity:.72"/></linearGradient>`;
  return `url(#${pid}g)`;
}
// the line of a chart (net worth or a position): a soft outline in the card colour lets it stand out above the areas;
// a dot marks today's value
function runGrad(gid) {
  // the veil over the running month (large and small charts): a light one from the cut (a visible step there), rising softly
  // into the plan's without a step -- the running month is not closed yet, much like a plan month; the further the month has
  // gone, the further right the rise
  const now = new Date(), dim = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const p = Math.min(1, (now.getDate() - 1 + now.getHours() / 24) / dim), w = 0.35, c = Math.max(w, Math.min(1 - w, p)), a = c - w, b = c + w;     // always from .10 at the cut to .45 at the plan
  const op = o => (.10 + .35 * Math.max(0, Math.min(1, (o - a) / (b - a)))).toFixed(3);
  return `<linearGradient id="${gid}" x1="0" x2="1">${[0, Math.max(0, a), Math.min(1, b), 1].map(o => `<stop offset="${o.toFixed(3)}" style="stop-color:var(--head);stop-opacity:${op(o)}"/>`).join('')}</linearGradient>`;
}
function heroLine(p, cls0, color, dot) {
  if (p.length < 2) return '';
  const dd = smoothD(p), st = color ? ` style="stroke:${color}"` : '';
  return `<path class="${cls0} halo" d="${dd}"/><path class="${cls0}" d="${dd}"${st}/>`
    + (dot ? `<circle class="bch-end" cx="${p[p.length - 1][0].toFixed(1)}" cy="${p[p.length - 1][1].toFixed(1)}" r="3.5"${color ? ` style="fill:${color}"` : ''}/>` : '');
}
function monthAxis(d, i0, i1, x, P, W, H, ticks) {
  // month axis: the first and the last month of the range are always labelled ("Nov 25"), so the period the values and the
  // change refer to can be read off directly; in between labels at even steps, only where they do not touch the end labels
  const n = i1 - i0, ppm = (W - P.l - P.r) / Math.max(1, n), step = [1, 2, 3, 6, 12, 24, 60, 120].find(st => st * ppm >= 62) || 120, pf = v => v.toFixed(1);
  const a = ML(d.months[i0]), z = ML(d.months[i1]), ea = x(i0) + textW(a) + 10, ez = x(i1) - textW(z) - 10;
  let g = `<text class="bch-x end" x="${pf(x(i0))}" y="${H - 6}" style="text-anchor:start">${a}</text>` + (i1 > i0 ? `<text class="bch-x end" x="${pf(x(i1))}" y="${H - 6}" style="text-anchor:end">${z}</text>` : '');
  for (let i = i0; i <= i1; i++) {
    const m = d.months[i], mo = +m.slice(5), yr = +m.slice(0, 4), xi = pf(x(i));
    if (mo === 1 && i > i0) g += `<line class="bch-year" x1="${xi}" x2="${xi}" y1="${P.t}" y2="${H - P.b}"/>`;
    if (ticks && ppm >= 5) g += `<line class="bch-tick" x1="${xi}" x2="${xi}" y1="${H - P.b}" y2="${H - P.b + (mo === 1 ? 5 : 3)}"/>`;
    const lab = step < 12 ? (mo - 1) % step === 0 : mo === 1 && yr % (step / 12) === 0, txt = String(step < 12 ? (mo === 1 ? yr : ML(m)) : yr), half = textW(txt) / 2 + 4;
    if (lab && i > i0 && i < i1 && x(i) - half > ea && x(i) + half < ez) g += `<text class="bch-x" x="${xi}" y="${H - 6}">${txt}</text>`;
  }
  return g;
}
function valChange(vals, a, z) {
  // value at the end of the shown actual months and the change since their start (in € and %), as in the small charts
  if (z == null) return '';
  const ch = a != null && a < z ? vals[z] - vals[a] : null, pc = ch != null ? pctGrowth(vals[a], ch) : '';
  return `${F0(vals[z])} €` + (ch != null ? ` <span class="delta ${ch >= 0 ? 'pos' : 'neg'}">${ch >= 0 ? '+' : ''}${F0(ch)} €${pc ? ` (${pc})` : ''}</span>` : '');
}
function bchPastEnd(i0, i1) {
  // the end the month field counts to: the last completed month while the balance sheet shows the plan ahead of it
  const done = BCH.d.ist - 2;
  return bigType() === 'balance' && S.bchPlan !== false && i0 < done && i1 > done ? done : i1;
}
function bchBigWindow(d, m) {
  // the large chart: as bchWindow; the balance sheet (no change shown there) also about a third of the range ahead -- the running
  // month and the plan (1 J: 4 months, 3 J: a year), unless "Plan" is switched off
  const [a, z] = bchWindow(d, m), extra = bigType() === 'balance' && S.bchPlan !== false ? Math.round(m / 3) : 0;
  return [a, Math.min(d.months.length - 1, z + extra)];
}
function bchWindow(d, m) {
  // m months up to the current month, from month end to month end: "1 J" runs from November last year to November (13 points),
  // so the change shown is exactly that of twelve months; the plan is reached by swiping to the right or with "Alle"
  const last = d.months.length - 1, i1 = Math.min(last, Math.max(0, d.ist - 2)), i0 = Math.max(0, i1 - m);
  return [i0, Math.min(last, Math.max(i1, i0 + 1))];
}
function bchSet(i0, i1, btn, sh = 0) {
  const d = BCH.d, n = d.months.length; i0 = Math.max(0, Math.min(i0, n - 2)); i1 = Math.max(i0 + 1, Math.min(i1, n - 1));
  if (i0 === 0 && sh < 0 || i1 === n - 1 && sh > 0) sh = 0;          // no shift past the first or last month
  BCH.f0 = i0; BCH.f1 = i1;
  if (i0 === BCH.i0 && i1 === BCH.i1 && (btn || null) === S.bchBtn && sh === (BCH.sh || 0)) return;
  BCH.i0 = i0; BCH.i1 = i1; BCH.sh = sh; S.bchRange = i0 === 0 && i1 === n - 1 ? null : [d.months[i0], d.months[i1]]; S.bchBtn = btn || null; bchDraw();
}
function bchView(f0, span, keepBtn) {
  // Ausschnitt in Bruchteilen von Monaten (fliessendes Wischen und Zoomen); am Rand wird verschoben, nicht gestaucht
  const last = BCH.d.months.length - 1; span = Math.max(1, Math.min(last, span)); f0 = Math.max(0, Math.min(f0, last - span));
  const i0 = Math.round(f0), i1 = Math.min(last, i0 + Math.round(span));
  bchSet(i0, i1, keepBtn ? S.bchBtn : null);
  BCH.f0 = f0; BCH.f1 = f0 + span;
}
function bchZoom(c, factor) {
  // um den Monat c (Bruchteil) vergroessern (factor < 1) bzw. verkleinern
  const span = BCH.f1 - BCH.f0, ns = Math.max(1, Math.min(BCH.d.months.length - 1, span * factor));
  bchView(c - (c - BCH.f0) * ns / span, ns, false);
}
// the stacked area under the pointer at month i (stacked as drawn: from the last series up/down from zero); null outside
function stackHit(series, i, v) {
  if (v == null || !isFinite(v)) return null;
  let up = 0, dn = 0;
  for (const sx of series.slice().reverse()) {
    const x = sx.vals[i] || 0;
    if (x > 0) { if (v >= up && v <= up + x) return sx; up += x; }
    else if (x < 0) { if (v <= dn && v >= dn + x) return sx; dn += x; }
  }
  return null;
}
// that area stands out in the chart (the others fade) and its row in the tip
function stackMark(svg, cls, d, hit) {
  if (!svg) return;
  const sis = (Array.isArray(hit) ? hit : hit ? [hit] : []).map(h => String(d.series.indexOf(h)));
  const shown = sis.filter(k => svg.querySelector(`.${cls}[data-s="${k}"]`));
  svg.classList.toggle('hl', shown.length > 0);
  svg.querySelectorAll('.' + cls).forEach(p => p.classList.toggle('hl', shown.includes(p.dataset.s)));
}
function bchHover(i, py, mark) {
  const d = BCH.d, G = BCH.geo, hv = $('#bch-hover'), tip = $('#bch-tip'); if (!hv || !tip) return;
  BCH.hov = i == null ? null : {i, py, mark};            // kept across a redraw (bchDraw shows it again)
  if (i == null) { hv.innerHTML = ''; tip.classList.add('hidden'); bchMark(null); stackMark($('#bch-svg'), 'bch-area', d, null); return; }
  const xi = G.x(i).toFixed(1), m = d.months[i], plan = i >= d.ist;
  let dots = `<line class="bch-cross" x1="${xi}" x2="${xi}" y1="${G.P.t}" y2="${G.H - G.P.b}"/>`;
  if (d.nw[i] != null) dots += `<circle class="bch-dot" cx="${xi}" cy="${G.y(d.nw[i]).toFixed(1)}" r="4"${d.lineColor ? ` style="stroke:${d.lineColor}"` : ''}/>`;
  hv.innerHTML = dots;
  const list = d.parts && d.parts.length > 1 ? d.parts : d.series;
  const hit = list === d.series && !d.adaptive && py != null ? stackHit(d.series, i, G.inv(py)) : null, hits = mark || (hit ? [hit] : []);
  stackMark($('#bch-svg'), 'bch-area', d, hits);
  const rows = list.filter(x => x.vals[i] != null && Math.abs(x.vals[i]) >= (d.all ? 0.005 : 0.5)).map(x => `<div${hits.includes(x) ? ' class="on"' : ''}><i style="${swatch(x.color, x.hatch)}"></i><span>${esc(x.label)}</span><b>${Math.abs(x.vals[i]) < 1 ? F(x.vals[i]) : F0(x.vals[i])}</b></div>`).join('');
  const part = d.off && d.off.size && d.series.length ? `<div class="bch-tip-nw"><span>${t('lc_summe_auswahl')}</span><b>${F0(d.series.reduce((s0, x) => s0 + (x.vals[i] || 0), 0))}</b></div>` : '';
  tip.innerHTML = `<div class="bch-tip-h">${MONATE_LANG[+m.slice(5) - 1]} ${m.slice(0, 4)}${plan ? ` <span class="pill neutral">${t('plan')}</span>` : i === d.ist - 1 ? ` <span class="pill neutral">${t('laufender_monat')}</span>` : ''}</div>${rows}${part}<div class="${rows ? 'bch-tip-nw' : ''}"><i class="nw-sw" style="background:${d.lineColor || 'var(--c-nw)'}"></i><span>${esc(d.lineLabel || t('nettovermoegen'))}</span><b>${F0(d.nw[i])}</b></div>`;
  tip.classList.remove('hidden');
  const bw = $('#bch-plot').clientWidth, tw = tip.offsetWidth, px = G.x(i);
  tip.style.left = (px + 14 + tw > bw ? px - 14 - tw : px + 14) + 'px';
  bchMark(m);
}
function bchMark(m) {
  // passende Spalte der Tabelle hervorheben (Monat bzw. Jahr)
  $$('.wrap th.bch-on').forEach(th => th.classList.remove('bch-on'));
  if (!m) return;
  const th = $(`.wrap th[data-key="${m}"]`) || $(`.wrap th[data-key="${m.slice(0, 4)}"]`); if (th) th.classList.add('bch-on');
}
function bchJump(m) {
  const w = $('.wrap.snap'), th = w && ($(`th[data-key="${m}"]`, w) || $(`th[data-key="${m.slice(0, 4)}"]`, w));
  // a month before the table's months: show from its year on, then go there
  if (!th) { const D = B(); if (D && S.mode !== 'years' && +m.slice(0, 4) < firstYear(D)) { S.vonJahr = +m.slice(0, 4); route().then(() => bchJump(m)); } return; }
  const sw = $('thead th', w).offsetWidth, target = colX(w, th) - sw - (w.clientWidth - sw - th.offsetWidth) / 2;
  w.scrollTo({left: snapLeft(w, target), behavior: 'smooth'});
  const idx = [...th.parentNode.children].indexOf(th);
  $$('tr', w).forEach(tr => { const c = tr.children[idx]; if (c) { c.classList.remove('flash'); void c.offsetWidth; c.classList.add('flash'); } });
}
function bchFocus(key, blink) {
  // a month heading (or a net worth value) clicked: the large chart moves (same span) so that this month lands exactly above
  // the column and lights up once (net worth: its dot blinks); the small charts keep their length and end with this month,
  // so they show the change up to it (year column: the current month for the running year, otherwise its last month)
  const d = BCH.d; if (!d) return;
  const i = bchIndex(key); if (i < 0) return;
  if (!bchLinked()) {
    const span = BCH.i1 - BCH.i0, last = d.months.length - 1, G = BCH.geo, svg = $('#bch-svg'), th = $(`#main .wrap thead th[data-key="${key}"]`);
    let frac = 0.5;                                     // share of the plot width where the month should land
    if (G && svg && th) { const sr = svg.getBoundingClientRect(), r = th.getBoundingClientRect(); if (sr.width) frac = ((r.left + r.width / 2 - sr.left) * G.W / sr.width - G.P.l) / Math.max(1, G.W - G.P.l - G.P.r); }
    const f = Math.max(0, Math.min(last - span, i - Math.max(0, Math.min(1, frac)) * span)), a = Math.round(f), z = Math.min(last, a + span);
    bchSet(a, z, z - a === BCH.i1 - BCH.i0 ? S.bchBtn : null, f - a);   // same length: the range button stays (as when moving)
    bchBlink(i, blink && ['balance', 'nw'].includes(bigType()));
  }
  const m = d.months[i];
  for (const id of Object.keys(LC)) {
    const st = LC[id], j = st && st.d && $(`#lc-${id}-svg`) ? st.d.months.indexOf(m) : -1; if (j < 0) continue;
    const sp = st.i1 - st.i0; lcSet(id, j - sp, j, null);      // stays there (the range button is marked by the length)
  }
}
// Touch and drag on a chart, attached once to the (persistent) <svg>; the plot inside is redrawn on every change.
// - one finger or the mouse on the x-axis strip (.bch-pan): drag sideways to move the range; the mouse over it shows the
//   values (as above the plot, without marking an area), a click jumps to the table, two fingers sideways move the range
// - on the y-axis strip (.bch-yax): drag up/down zooms the value range in/out around that point, the wheel moves it
//   (with Ctrl or a pinch on the trackpad: zoom); a tap or click there restores the automatic range
// - two fingers in the plot: move = shift, spread/pinch = zoom; the value tip stays hidden meanwhile
// o: {pt(e) -> x in svg units, pty(e) -> y in svg units, geo(), ygeo(), range() -> [f0, f1], view(f0, span, keepBtn),
//     yview(lo, hi) / yview(null), hide()}
function chartGestures(svg, o) {
  if (!svg || svg._gest) return svg && svg._gest;
  const tp = new Map(); let two = null, pan = null, yz = null;
  const width = G => Math.max(1, G.W - G.P.l - G.P.r);
  const both = () => { const v = [...tp.values()]; return [(v[0] + v[1]) / 2, Math.abs(v[0] - v[1])]; };
  const onY = e => e.target.classList && e.target.classList.contains('bch-yax');
  const valAt = (G, yy) => G.max - (yy - G.P.t) * (G.max - G.min) / Math.max(1, G.H - G.P.t - G.P.b);
  const yscale = (G, a, f) => o.yview(a - (a - G.min) * f, a + (G.max - a) * f);
  svg.addEventListener('touchstart', e => { if (onY(e)) e.preventDefault(); }, {passive: false});      // no page scrolling there
  const onX = e => e.target.classList && e.target.classList.contains('bch-pan');
  svg.addEventListener('wheel', e => {
    if (onX(e) && Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      const G = o.geo(); if (!G) return; const [f0, f1] = o.range(); e.preventDefault(); o.view(f0 + e.deltaX * (f1 - f0) / width(G), f1 - f0, true); return;
    }
    if (!onY(e)) return; const G = o.ygeo(); if (!G) return; e.preventDefault();
    if (e.ctrlKey) yscale(G, valAt(G, o.pty(e)), Math.exp(e.deltaY * 0.01));
    else { const sh = e.deltaY * (G.max - G.min) / Math.max(1, G.H - G.P.t - G.P.b); o.yview(G.min - sh, G.max - sh); }
  }, {passive: false});
  svg.addEventListener('pointerdown', e => {
    if (onY(e)) {
      const G = o.ygeo(); if (!G) return;
      yz = {id: e.pointerId, y: o.pty(e), G: Object.assign({}, G), moved: false};
      try { svg.setPointerCapture(e.pointerId); } catch (x) {}
      e.preventDefault(); return;
    }
    const G = o.geo(); if (!G) return;
    if (e.target.classList && e.target.classList.contains('bch-pan')) {
      const [f0, f1] = o.range(); pan = {id: e.pointerId, x: o.pt(e), f0, span: f1 - f0, moved: false};
      try { svg.setPointerCapture(e.pointerId); } catch (x) {}
      e.preventDefault(); return;
    }
    if (e.pointerType !== 'touch') return;
    tp.set(e.pointerId, o.pt(e));
    if (tp.size === 2) { o.hide(); const [m, d] = both(), [f0, f1] = o.range(); two = {d: Math.max(d, 24), span: f1 - f0, c: f0 + (m - G.P.l) * (f1 - f0) / width(G)}; }
  });
  svg.addEventListener('pointermove', e => {
    if (yz && e.pointerId === yz.id) {
      const dy = o.pty(e) - yz.y; if (Math.abs(dy) > 3) yz.moved = true;
      if (yz.moved) { e.preventDefault(); yscale(yz.G, valAt(yz.G, yz.y), Math.exp(dy * 0.01)); }       // down: wider range, up: closer
      return;
    }
    const G = o.geo(); if (!G) return;
    if (pan && e.pointerId === pan.id) {
      if (Math.abs(o.pt(e) - pan.x) > 4) pan.moved = true;
      if (pan.moved) { e.preventDefault(); o.hide(); o.view(pan.f0 - (o.pt(e) - pan.x) * pan.span / width(G), pan.span, true); }
      return;
    }
    if (onX(e) && e.pointerType !== 'touch' && !tp.size && o.panHover) { o.panHover(o.pt(e)); return; }
    if (!tp.has(e.pointerId)) return;
    tp.set(e.pointerId, o.pt(e));
    if (!two || tp.size < 2) return;
    e.preventDefault(); o.hide();
    const [m, d] = both(), ns = two.span * two.d / Math.max(d, 24);
    o.view(two.c - (m - G.P.l) * ns / width(G), ns, false);
  });
  let lastTwo = 0;
  const end = e => {
    if (yz && e.pointerId === yz.id) { if (!yz.moved && e.type === 'pointerup') o.yview(null); yz = null; return; }    // tap: automatic range again
    if (pan && e.pointerId === pan.id) { if (!pan.moved && e.type === 'pointerup' && o.panTap) o.panTap(o.pt(e)); pan = null; } tp.delete(e.pointerId); if (tp.size < 2 && two) { two = null; lastTwo = Date.now(); }
  };
  svg.addEventListener('pointerup', end); svg.addEventListener('pointercancel', end);
  svg.addEventListener('pointerout', e => { if (onX(e) && !pan && !(e.relatedTarget && e.relatedTarget.classList && e.relatedTarget.classList.contains('bch-hit'))) o.hide(); });
  // busy also shortly after two fingers: lifting the last finger is not a tap
  svg._gest = {busy: () => !!pan || !!yz || tp.size >= 2 || Date.now() - lastTwo < 500, multi: () => tp.size >= 2};
  return svg._gest;
}
function bchBind() {
  const hit = $('#bch-hit'); if (!hit) return;
  const pt = e => { const r = $('#bch-svg').getBoundingClientRect(); return (e.clientX - r.left) * BCH.geo.W / r.width; };
  const pty = e => { const r = $('#bch-svg').getBoundingClientRect(); return (e.clientY - r.top) * BCH.geo.H / r.height; };
  const gest = chartGestures($('#bch-svg'), {pt, pty, geo: () => bchLinked() ? null : BCH.geo, ygeo: () => BCH.geo, range: () => [BCH.f0, BCH.f1],
    view: (f0, span, keep) => bchView(f0, span, keep), yview: (lo, hi) => { S.bchYr = lo == null ? null : [lo, hi]; bchDraw(); }, hide: () => bchHover(null),
    panHover: px => bchHover(BCH.geo.idx(px)), panTap: px => { bchHover(null); bchJump(BCH.d.months[BCH.geo.idx(px)]); }});
  // aligned with the table: no value tip (the table shows the same), no zoom; swiping sideways scrolls the table
  if (bchLinked()) return;                              // aligned: swiping and dragging scroll the table (bchLinkPan)
  hit.addEventListener('pointermove', e => {
    BCH.ptr = e.pointerType === 'touch' ? null : {x: e.clientX, y: e.clientY};
    if (BCH.flash) { clearTimeout(BCH.flashT); BCH.flash = false; }
    if (gest.busy()) { bchHover(null); return; }
    const px = pt(e), G = BCH.geo;
    if (BCH.drag) { const sel = $('#bch-sel'), a = Math.max(G.P.l, Math.min(BCH.drag.x, px)), b = Math.min(G.W - G.P.r, Math.max(BCH.drag.x, px)); sel.setAttribute('x', a); sel.setAttribute('width', b - a); sel.classList.toggle('hidden', b - a < 4); }
    bchHover(G.idx(px), pty(e));
  });
  hit.addEventListener('pointerleave', () => { if (!BCH.drag) { BCH.ptr = null; bchHover(null); } });
  hit.addEventListener('pointerdown', e => { if (e.pointerType === 'touch') { BCH.tap = pt(e); return; } BCH.drag = {x: pt(e)}; hit.setPointerCapture(e.pointerId); });
  hit.addEventListener('pointerup', e => {
    if (e.pointerType === 'touch' && (gest.busy() || BCH.tap == null || Math.abs(pt(e) - BCH.tap) > 10)) { BCH.tap = null; bchHover(null); return; }   // only a tap jumps to the column
    const G = BCH.geo, px = pt(e), dr = BCH.drag; BCH.drag = null;
    if (dr && Math.abs(px - dr.x) > 6) { const a = G.idx(Math.min(px, dr.x)), b = G.idx(Math.max(px, dr.x)); bchSet(a, b); return; }
    $('#bch-sel') && $('#bch-sel').classList.add('hidden');
    // with the mouse on an area of the balance sheet: open it up (or close it again), otherwise jump to the month in the table
    const h = e.pointerType !== 'touch' && bigType() === 'balance' ? stackHit(BCH.d.series, G.idx(px), G.inv(pty(e))) : null;
    if (h && bchToggle(h, BCH.d.months[G.idx(px)])) return;
    bchJump(BCH.d.months[G.idx(px)]);
  });
  const at = px => { const G = BCH.geo; return BCH.f0 + (px - G.P.l) * (BCH.f1 - BCH.f0) / Math.max(1, G.W - G.P.l - G.P.r); };   // Monat (Bruchteil) unter dem Zeiger
  hit.addEventListener('dblclick', e => { if (Date.now() - (BCH.lastToggle || 0) > 700) bchZoom(at(pt(e)), 0.5); });     // not after a click that opened an area          // Doppelklick: auf den halben Zeitraum um diese Stelle
  hit.addEventListener('wheel', e => {
    // Trackpad: Zusammen-/Auseinanderziehen (bzw. Strg + Rad) zoomt um den Zeiger; waagerechtes Wischen verschiebt den Ausschnitt
    // bei gleicher Laenge (wie eine Tabelle); senkrechtes Wischen bleibt beim Seitenrollen
    if (BCH.gesture) return;
    if (e.ctrlKey) { e.preventDefault(); bchZoom(at(pt(e)), Math.exp(e.deltaY * 0.01)); return; }
    if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
    const span = BCH.f1 - BCH.f0, G = BCH.geo;
    if (span >= BCH.d.months.length - 1) return;
    e.preventDefault();
    bchView(BCH.f0 + e.deltaX * span / Math.max(1, G.W - G.P.l - G.P.r), span, true);
  }, {passive: false});
  // Safari: Zusammen-/Auseinanderziehen kommt als eigenes Gesten-Ereignis
  hit.addEventListener('gesturestart', e => { e.preventDefault(); bchHover(null); BCH.gesture = gest.multi() ? null : {c: at(pt(e)), span: BCH.f1 - BCH.f0, f0: BCH.f0}; });
  hit.addEventListener('gesturechange', e => {
    e.preventDefault(); const g = BCH.gesture; if (!g || !e.scale || gest.multi()) return;
    const ns = Math.max(1, Math.min(BCH.d.months.length - 1, g.span / e.scale));
    bchView(g.c - (g.c - g.f0) * ns / g.span, ns, false);
  });
  hit.addEventListener('gestureend', e => { e.preventDefault(); BCH.gesture = null; });
}
const bchRowSeries = tr => { const d = BCH.d, p = tr.dataset.pos, a = tr.dataset.id, w = tr.dataset.wp;
  return d ? d.series.filter(x => p ? x.role === p : w ? x.wp === w : a ? x.acc === a : false) : []; };
function bchTableHover(tr) {
  // the mouse over the name of a row marks the same position, account or security in the large chart (where it shows it)
  if (!BCH.d || bigType() !== 'balance' || BCH.flash) return;
  stackMark($('#bch-svg'), 'bch-area', BCH.d, tr ? bchRowSeries(tr) : []);
}
function bchBlink(i, dot) {
  // a month lights up once in the large chart (line and table column), with the net worth dot if wanted; nothing stays
  const d = BCH.d, G = BCH.geo, hv = $('#bch-hover'); if (!G || !hv) return;
  clearTimeout(BCH.flashT2); bchHover(null);
  const xi = G.x(i).toFixed(1);
  hv.innerHTML = `<line class="bch-cross pulse" x1="${xi}" x2="${xi}" y1="${G.P.t}" y2="${G.H - G.P.b}"/>`
    + (dot && d.nw[i] != null ? `<circle class="bch-dot blink" cx="${xi}" cy="${G.y(d.nw[i]).toFixed(1)}" r="4"${d.lineColor ? ` style="stroke:${d.lineColor}"` : ''}/>` : '');
  bchMark(d.months[i]);
  BCH.flashT2 = setTimeout(() => { if (BCH.hov) return; const h2 = $('#bch-hover'); if (h2) h2.innerHTML = ''; bchMark(null); }, 1300);
}
function bchFlash(tr, td) {
  // a click on a value in the table: the row's area and the month light up once in the large chart, short and soft (the chart
  // moves there, with the same range, when the month is outside it)
  const d = BCH.d, svg = $('#bch-svg'); if (!d || !svg || bigType() !== 'balance') return;
  const th = td.closest('table').querySelector('thead tr').children[td.cellIndex], i = th && th.dataset.key ? bchIndex(th.dataset.key) : -1;
  if (i < 0) return;
  if (!bchLinked() && (i < BCH.i0 || i > BCH.i1)) { const span = BCH.i1 - BCH.i0, last = d.months.length - 1, a = Math.max(0, Math.min(last - span, i - Math.round(span / 2))); bchSet(a, Math.min(last, a + span), S.bchBtn); }
  clearTimeout(BCH.flashT); clearTimeout(BCH.flashT2); bchHover(null);
  const G = BCH.geo, hv = $('#bch-hover');
  svg.classList.add('pulse'); stackMark(svg, 'bch-area', BCH.d, bchRowSeries(tr)); BCH.flash = true;
  if (hv && G && !bchLinked()) hv.innerHTML = `<line class="bch-cross pulse" x1="${G.x(i).toFixed(1)}" x2="${G.x(i).toFixed(1)}" y1="${G.P.t}" y2="${G.H - G.P.b}"/>`;
  BCH.flashT = setTimeout(() => { stackMark(svg, 'bch-area', BCH.d, []); BCH.flash = false; }, 650);
  BCH.flashT2 = setTimeout(() => { svg.classList.remove('pulse'); const h2 = $('#bch-hover'); if (h2 && !BCH.hov) h2.innerHTML = ''; }, 1100);
}
function bchToggle(x, m) {
  // a click on an area of the balance sheet chart, as in the table: a position opens into its accounts, a portfolio into its
  // securities; a click on what cannot be split further (an account, a security) closes the whole position again
  const r = x.role, D = B(); if (!r || !D) return false;
  S.posOpen = S.posOpen || {}; S.depOpen = S.depOpen || {};
  if (x.pos) S.posOpen[r] = true;
  else if (x.acc && x.dep && !x.wp && !S.depOpen[x.acc]) S.depOpen[x.acc] = true;
  else { S.posOpen[r] = false; for (const a of D.balance.rows) if (!a.group && a.role === r) S.depOpen[a.id] = false; }
  BCH.lastToggle = Date.now(); bchHover(null);
  // afterwards: the table stays where it was (and moves to the month only if needed); what just opened (or closed) is marked
  // until the mouse moves, then again only the area under it
  const w = $('#main .wrap.snap'), sl = w ? w.scrollLeft : null;
  const pick = x.pos ? (y => y.role === r) : x.acc && x.dep && !x.wp && S.depOpen[x.acc] ? (y => y.acc === x.acc) : (y => y.pos && y.role === r);
  Promise.resolve(route()).then(() => requestAnimationFrame(() => {
    const w2 = $('#main .wrap.snap'); if (w2 && sl != null) w2.scrollLeft = sl;
    if (m) bchJump(m);
    const d = BCH.d, G = BCH.geo, svg = $('#bch-svg'), p = BCH.ptr; if (!d || !G || !svg) return;
    let i = m ? d.months.indexOf(m) : -1;
    if (p) { const rc = svg.getBoundingClientRect(); if (rc.width) i = G.idx((p.x - rc.left) * G.W / rc.width); }
    if (i >= BCH.i0 && i <= BCH.i1) bchHover(i, null, d.series.filter(pick));
  }));
  return true;
}
function bchRehover() {
  // after a redraw: the values (and the area) under the mouse, without waiting for it to move -- so clicking again closes it
  const p = BCH.ptr, svg = $('#bch-svg'), G = BCH.geo; if (!p || !svg || !G || bchLinked()) return;
  const r = svg.getBoundingClientRect(); if (!r.width || p.x < r.left || p.x > r.right || p.y < r.top || p.y > r.bottom) return;
  const px = (p.x - r.left) * G.W / r.width, py = (p.y - r.top) * G.H / r.height;
  if (px >= G.P.l && px <= G.W - G.P.r) bchHover(G.idx(px), py <= G.H - G.P.b ? py : null);
}
function bindBilanzChart(main) {
  if (!$('#bch', main)) return;
  $$('#bch-rb button', main).forEach(b => b.addEventListener('click', () => {
    const d = BCH.d, m = +b.dataset.m;
    if (!m) bchSet(0, d.months.length - 1); else { const [a, z] = bchBigWindow(d, m); bchSet(a, z, m); }
  }));
  const bp = $('#bch-plan', main); if (bp) bp.addEventListener('click', () => {      // the balance sheet: plan on the right on/off
    S.bchPlan = S.bchPlan === false; bp.classList.toggle('on', S.bchPlan !== false);
    if (S.bchBtn) { const [a, z] = bchBigWindow(BCH.d, S.bchBtn); bchSet(a, z, S.bchBtn); }
  });
  const nf = $('#bch-n', main);
  if (nf) nf.addEventListener('change', () => {
    // eigene Anzahl Monate: rechter Rand bleibt, der Ausschnitt waechst bzw. schrumpft nach links
    const d = BCH.d, m = Math.max(1, Math.min(d.months.length - 1, Math.round(+nf.value) || 12)), z = BCH.i1;
    // with the plan ahead of the balance sheet: like a range button of that length (a third ahead), otherwise the right edge stays
    let [a, e] = bchPastEnd(BCH.i0, z) !== z ? bchBigWindow(d, m) : [z - m, z]; if (a < 0) { e = Math.min(d.months.length - 1, e - a); a = 0; }
    const btn = bchRanges().some(([k]) => k === m) && bchBigWindow(d, m).join() === [a, e].join() ? m : null;
    bchSet(a, e, btn); nf.blur();
  });
  // a small chart shown large: its own controls (positions to add up, position and breakdown, accounts to leave out)
  const grip = $('.bil-tbl .col-grip', main);
  if (grip) {
    // the first column of the balance table: drag its edge to make it wider or narrower (double click: back to the default)
    grip.addEventListener('pointerdown', e => {
      e.preventDefault(); e.stopPropagation();
      const wrap = grip.closest('.bil-tbl'), x0 = e.clientX, w0 = grip.closest('th').getBoundingClientRect().width;
      grip.setPointerCapture(e.pointerId); grip.classList.add('on');
      const move = ev => { const w = Math.round(Math.max(150, Math.min(520, w0 + ev.clientX - x0))); wrap.style.setProperty('--bil-w', w + 'px'); S.bilW = w; };
      const up = () => { grip.classList.remove('on'); grip.removeEventListener('pointermove', move); grip.removeEventListener('pointerup', up); grip.removeEventListener('pointercancel', up); if (bchLinked()) bchDraw(); };
      grip.addEventListener('pointermove', move); grip.addEventListener('pointerup', up); grip.addEventListener('pointercancel', up);
    });
    grip.addEventListener('click', e => e.stopPropagation());
    grip.addEventListener('dblclick', e => { e.stopPropagation(); S.bilW = null; grip.closest('.bil-tbl').style.removeProperty('--bil-w'); if (bchLinked()) bchDraw(); });
  }
  $$('.th-mv[data-blk]', main).forEach(b => b.addEventListener('click', e => {     // move the table or the large chart up or down
    e.stopPropagation(); const o = bilBlocks(), k = o.indexOf(b.dataset.blk), n = k + +b.dataset.mv; if (k < 0 || n < 0 || n > 2) return;
    [o[k], o[n]] = [o[n], o[k]]; S.blocks = o;
    Promise.resolve(route()).then(() => { const el = b.dataset.blk === 'chart' ? $('#bch') : $('#main .wrap'); if (el) el.scrollIntoView({block: 'nearest', behavior: 'smooth'}); });
  }));
  const vs = $('#view-save', main); if (vs) vs.addEventListener('click', () => {
    // one default each for months and years; the one saved last opens at the start
    const v = viewLoad() || {views: {}}; v.views[S.mode] = viewSnap(); v.mode = S.mode;
    try { LS.set(VIEW_KEY, JSON.stringify(v)); toast(t(S.mode === 'years' ? 'ansicht_gespeichert_j' : 'ansicht_gespeichert_m')); } catch (e) { toast(e.message, 5000); }
  });
  const vr = $('#view-reset', main); if (vr) vr.addEventListener('click', () => { try { LS.del(VIEW_KEY); } catch (e) {} viewApply(null); route(); toast(t('ansicht_zurueckgesetzt')); });
  $$('#big-chips input', main).forEach(cb => cb.addEventListener('change', () => { S.lcSel = $$('#big-chips input:checked', main).map(x => x.dataset.r); route(); }));
  const bps = $('#big-pos-sel', main); if (bps) bps.addEventListener('change', () => { S.lcPos = bps.value; route(); });
  const bpm = $('#big-pos-mode', main); if (bpm) bpm.addEventListener('click', () => {
    S.lcPosModes = Object.assign({}, S.lcPosModes, {[bps.value]: lcPosMode(B(), bps.value) === 'depot' ? 'accounts' : 'depot'}); route();
  });
  const bac = $('#big-accs', main); if (bac) bac.addEventListener('change', e => {
    const cb = e.target.closest('input[data-k]'); if (!cb || !BCH.d || !BCH.d.off) return;
    if (cb.checked) BCH.d.off.delete(cb.dataset.k); else BCH.d.off.add(cb.dataset.k);
    BCH.d = bchData(B()); bchDraw();
  });
  const lb = $('#bch-link', main); if (lb) lb.addEventListener('click', () => { S.bchLink = !bchLinked(); route(); });
  const tb = $('.wrap tbody', main);
  if (tb) {
    tb.addEventListener('mouseover', e => { const td = e.target.closest('td'); if (td) bchTableHover(td.cellIndex === 0 ? td.parentNode : null); });
    tb.addEventListener('mouseleave', () => bchTableHover(null));
  }
  bchDraw();
  if (bchLinked()) {
    // the chart follows the table when it scrolls sideways; swiping or dragging on the chart scrolls the table
    const w = $('.wrap.snap', main); if (w) w.addEventListener('scroll', () => { if (!BCH.raf) BCH.raf = requestAnimationFrame(() => { BCH.raf = 0; bchDraw(); }); }, {passive: true});
    bchLinkPan($('#bch-svg', main));
  } else $$('.wrap thead th[data-key]', main).forEach(th => { th.classList.add('jump'); th.addEventListener('click', () => bchFocus(th.dataset.key)); });
  if (BCH.ro) BCH.ro.disconnect();
  // drawn at this width just now: only another width draws again (the observer reports once at the start -- a second drawing
  // would wipe what a click on the table marks right after the page is drawn anew)
  let last = $('#bch-plot', main).clientWidth; BCH.ro = new ResizeObserver(onResizeFrame(() => { if (PRINT.on) return; const w = $('#bch-plot'); if (w && Math.abs(w.clientWidth - last) > 2) { last = w.clientWidth; bchDraw(); } }));
  BCH.ro.observe($('#bch-plot', main));
}

// ---------------------------------------------------------------- Balance sheet: single curves below the table
// Net worth alone and a freely chosen sum of positions (default: cash + tradable + fixed-term investments). Each chart has
// its own range (1/3/10 years, all, drag to zoom, pinch, double click) and fits the y-axis to the visible values, so even
// a flat curve shows its development.
const LC = {};
const LC_DEFAULT = ['cash', 'securities', 'term_investments'];
// title of the selection chart, in words (no codes): one position by its name, all of them as net worth, typical combinations
// by their name (Finanzvermögen …), otherwise the shorter of "group + rest" (Finanzvermögen + Verbindlichkeiten) and "net worth
// or gross assets without …" (Nettovermögen ohne Beteiligungen); in the small chart long words are shortened (Verbindl.),
// the tip names every position (no "Auswahl:" before it: the title follows the chips anyway)
function lcSelTitle(sel, avail, long) {
  const s = avail.filter(r => sel.includes(r)), all = s.map(r => ROLE[r][0]).join(' + ');
  if (!s.length) return [t('lc_summe_auswahl'), ''];
  const w = lcSelWords(s, avail), word = (k, sh) => sh ? KURZW[k] || ROLE[k][0] : k === 'net_worth' ? t('nettovermoegen') : k.startsWith('grp_') ? t(k) : ROLE[k][0];
  const text = sh => w.minus ? t('lc_ohne', word(w.base, sh), w.minus.map(k => word(k, sh)).join(t('lc_und'))) : w.plus.map(k => word(k, sh)).join(' + ');
  const full = text(false), short = !long && full.length > 26;
  const now = [short ? full : '', all !== full ? all : ''].filter(Boolean).join(' = ');
  // the tip also says what the names stand for: written as one sum, step by step (only positions this area has)
  const defs = lcSumTip(avail);
  return [short ? text(true) : full, [now, defs ? t('lc_gruppen') + '\n' + defs : ''].filter(Boolean).join('\n\n')];
}
function lcSumTip(avail) {
  // the named combinations as a written sum, each word once:   Bankguthaben / + Wertpapiere / = Liquides Vermögen / + Festanlagen /
  // = Geldanlagen / + Beteiligungen / + Forderungen / = Geldvermögen / + Sachvermögen (Immobilien + Sachwerte) / + Sonstiges /
  // = Bruttovermögen / + Verbindlichkeiten / = Nettovermögen   (gross = financial + real assets, as usual)
  const G = lcGroups(avail, true), has = r => avail.includes(r), lines = [], sum = [], used = new Set();
  const nameOf = set => { const sig = avail.filter(r => set.includes(r)).join(), g = G.find(([, l]) => l.join() === sig); return g ? g[0] : null; };
  const word = k => k === 'net_worth' ? t('nettovermoegen') : t(k);
  const add = (label, rs) => { lines.push((sum.length ? '+ ' : '\u2007 ') + label); sum.push(...rs); };
  const sach = has('real_estate') && has('tangibles') && nameOf(['real_estate', 'tangibles']) === 'grp_sach';
  for (const stage of [LC_LIQUID, ['term_investments'], ['participations', 'receivables'], ['real_estate', 'tangibles', 'other'], ['liabilities']]) {
    let added = false;
    for (const r of stage) {
      if (!has(r) || (sach && r === 'tangibles')) continue;
      if (sach && r === 'real_estate') { add(`${t('grp_sach')} (${ROLE.real_estate[0]} + ${ROLE.tangibles[0]})`, ['real_estate', 'tangibles']); used.add('grp_sach'); }
      else add(ROLE[r][0], [r]);
      added = true;
    }
    const k = !added || sum.length < 2 ? null : sum.length === avail.length ? 'net_worth' : nameOf(sum);
    if (k) { lines.push('= ' + word(k)); used.add(k); }
  }
  // tied-up assets do not lie on the way: what is left of the assets without the liquid part (shortened to fit one line)
  if (G.some(([k]) => k === 'grp_gebunden') && !used.has('grp_gebunden')) {
    const liq = avail.filter(r => LC_LIQUID.includes(r)), all = avail.filter(r => r !== 'liabilities');
    const a = all.length === avail.length ? 'net_worth' : nameOf(all), b = liq.length > 1 ? nameOf(liq) : liq[0];
    if (a && b) lines.push('', `${KURZW.grp_gebunden} = ${KURZW[a]} − ${b.startsWith('grp_') ? KURZW[b] : ROLE[b][0]}`);
  }
  return lines.length > 1 ? lines.join('\n') : '';
}
function lcGroups(avail, show) {
  // the named combinations of positions this area has (at least two of their positions each; the same set only once):
  // largest first for naming a selection, in a fixed order for showing them
  const order = [['grp_liquide', LC_LIQUID], ['grp_geldanlagen', [...LC_LIQUID, 'term_investments']], ['grp_geldvermoegen', [...LC_LIQUID, 'term_investments', 'participations', 'receivables']],
    ['grp_sach', ['real_estate', 'tangibles']], ['grp_gebunden', LC_ILLIQUID], ['grp_brutto', avail.filter(r => r !== 'liabilities')]];
  const seen = new Set(), out = [];
  for (const [k, l0] of order) { const l = avail.filter(r => l0.includes(r)), sig = l.join(); if (l.length > 1 && !seen.has(sig)) { seen.add(sig); out.push([k, l]); } }
  return show ? out : out.slice().sort((a, b) => b[1].length - a[1].length);
}
function lcSelWords(s, avail) {
  // {plus: [words]} joined by "+", or {base, minus: [positions]} for "… ohne …" -- whichever needs fewer words
  if (s.length === avail.length) return {plus: ['net_worth']};
  if (s.length === 1) return {plus: [s[0]]};
  const groups = lcGroups(avail);
  let rest = s.slice(); const plus = [];
  for (const [k, l] of groups) if (l.every(r => rest.includes(r))) { plus.push(k); rest = rest.filter(r => !l.includes(r)); }
  plus.push(...rest);
  const base = !avail.includes('liabilities') || s.includes('liabilities') ? 'net_worth' : 'grp_brutto';
  const minus = avail.filter(r => !s.includes(r) && !(base === 'grp_brutto' && r === 'liabilities'));
  return minus.length && 1 + minus.length < plus.length ? {base, minus} : {plus};
}
// shortened words for the small chart (never single letters)
const KURZW = {cash: t('kurzw_liquiditaet'), securities: t('kurzw_wertpapiere'), term_investments: t('kurzw_anlagen'), real_estate: t('kurzw_immobilien'),
  participations: t('kurzw_beteiligungen'), tangibles: t('kurzw_sachwerte'), receivables: t('kurzw_forderungen'), other: t('kurzw_sonstiges'),
  liabilities: t('kurzw_verbindlichkeiten'), net_worth: t('kurzw_nettovermoegen'), grp_brutto: t('kurzw_brutto'), grp_geldanlagen: t('kurzw_geldanlagen'),
  grp_geldvermoegen: t('kurzw_geldvermoegen'), grp_gebunden: t('kurzw_gebunden'), grp_liquide: t('kurzw_liquide'), grp_sach: t('kurzw_sach')};
// positions of the typical combinations (names in lcSelWords)
const LC_LIQUID = ['cash', 'securities'], LC_ILLIQUID = ['term_investments', 'real_estate', 'participations', 'tangibles', 'receivables', 'other'];
function lcSelection(D) {
  const avail = D.balance.rows.filter(r => r.group && ROLE[r.role]).map(r => r.role);
  let sel = S.lcSel ? S.lcSel.slice() : null;
  return {avail, sel: (Array.isArray(sel) ? sel : LC_DEFAULT).filter(r => avail.includes(r))};
}
function lcData(D, rollen) {
  const pr = D.balance.projection || null, proj = pr ? Object.fromEntries(pr.rows.map(r => [r.id, r.amounts])) : {};
  const months = [...D.months, ...(pr ? (D.plan_months || []) : [])];
  let vals;
  if (!rollen) {
    const nw = pr ? Object.assign({}, D.balance.net_worth, pr.net_worth) : D.balance.net_worth;
    vals = months.map(m => nw[m] == null ? null : nw[m] * defl(m));
  } else {
    const groups = D.balance.rows.filter(r => r.group && rollen.includes(r.role));
    const rows = groups.map(r => Object.assign({}, r.amounts, proj[r.id] || {}));
    vals = months.map(m => { let s = null; for (const w of rows) if (w[m] != null) s = (s || 0) + w[m]; return s == null ? null : s * defl(m); });
    // the single positions, for the tooltip
    const parts = groups.map((r, k) => ({label: ROLE[r.role][0], color: ROLE[r.role][1], vals: months.map(m => rows[k][m] == null ? null : rows[k][m] * defl(m))}));
    return {months, ist: D.months.length, vals, parts};
  }
  return {months, ist: D.months.length, vals};
}
// third chart: one position split into its accounts (stacked), in the account colours of the table and the main chart
// (first account on top)
function lcStack(D, rolle, mode) {
  // series: the accounts of the position, or (mode "depot") portfolios broken down into their securities; the total line is
  // always the whole position, whatever is broken down or deselected
  const pr = D.balance.projection || null, proj = pr ? Object.fromEntries(pr.rows.map(r => [r.id, r.amounts])) : {};
  const months = [...D.months, ...(pr ? (D.plan_months || []) : [])];
  const color = (ROLE[rolle] || [0, 'var(--c-neutral)'])[1], vs = w => months.map(m => w[m] == null ? null : w[m] * defl(m));
  const accs = D.balance.rows.filter(x => !x.group && x.role === rolle), series = [];
  accs.forEach((a, i) => {
    const sh = accShade(color, i);
    if (mode === 'depot' && a.securities && a.securities.length)
      a.securities.forEach((p, j) => series.push(Object.assign({key: p.id, label: p.name, full: wpTip(p, a.name), vals: vs(p.amounts)}, accShade(sh.color, j + 1))));
    else series.push(Object.assign({key: a.id, label: a.name, full: a.path || a.name, vals: vs(Object.assign({}, a.amounts, proj[a.id] || {}))}, sh));
  });
  const tot = accs.map(a => vs(Object.assign({}, a.amounts, proj[a.id] || {})));
  const vals = months.map((m, k) => { let v = null; for (const x of tot) if (x[k] != null) v = (v || 0) + x[k]; return v; });
  return {months, ist: D.months.length, vals, series: series.filter(x => x.vals.some(v => v != null && Math.abs(v) >= 0.005))};   // small amounts too (e.g. 0.29 € cash)
}
const lcHasDepot = (D, rolle) => D.balance.rows.some(x => !x.group && x.role === rolle && x.securities && x.securities.length);
function lcPosMode(D, rolle) {
  // "konten" or "depot" (securities), remembered per position; only where a portfolio of the position can be broken down
  if (!lcHasDepot(D, rolle)) return 'accounts';
  const m = S.lcPosModes || {};
  return m[rolle] === 'depot' ? 'depot' : 'accounts';
}
// short names for crowded legends: brackets, legal forms and fund words go, and of the remaining words the most distinctive
// ones are kept (words many names share, e.g. a fund family or index provider, only if nothing else is left) -- e.g.
// "MSCI ACWI USD (Acc)" next to other MSCI funds becomes "ACWI"; then cut to max characters. Works for any name.
const SHORT_STOP = new Set(('ag se inc incorporated plc nv sa ltd limited gmbh corp corporation co kgaa spa oyj ab asa llc lp holding holdings group '
  + 'etf etc etn ucits acc accumulating dist distributing distribution fund fonds index shares share class core usd eur gbp chf jpy hedged hdg '
  + 'the of and und de la le du der die das a b c d 1c 1d 2c').split(' '));
function shortNames(names, max) {
  const toks = names.map(n => (String(n || '').replace(/\([^)]*\)|\[[^\]]*\]/g, ' ').match(/[\p{L}\p{N}][\p{L}\p{N}.'&-]*/gu) || [])
    .map(w => w.replace(/[.'-]+$/, '')).filter(w => w && !SHORT_STOP.has(w.toLowerCase())));
  const df = {}; toks.forEach(ws => new Set(ws.map(w => w.toLowerCase())).forEach(w => { df[w] = (df[w] || 0) + 1; }));
  return names.map((n, i) => {
    const full = String(n || '').trim();
    if (full.length <= max) return full;
    const ws = toks[i]; if (!ws.length) return full.slice(0, max - 1).trimEnd() + '…';
    // the most distinctive words first, as many as fit, shown in their original order
    // (equally distinctive: a word that fits first); further words only if just as distinctive as the first
    const order = ws.map((w, k) => [df[w.toLowerCase()], w.length > max ? 1 : 0, k]).sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]).map(x => x[2]), take = [];
    for (const k of order) {
      const len = take.reduce((s0, x) => s0 + ws[x].length + 1, 0) + ws[k].length;
      if (!take.length || (len <= max && df[ws[k].toLowerCase()] <= df[ws[take[0]].toLowerCase()])) take.push(k);
    }
    const x = take.sort((a, b) => a - b).map(k => ws[k]).join(' ');
    return x.length > max ? x.slice(0, max - 1).trimEnd() + '…' : x;
  });
}
function lcOffSet(id, k) {
  // deselected series of a composition chart (per chart, the same whether shown small or large); all selected again
  // whenever its position or the breakdown changes
  S.lcOff = S.lcOff || {};
  if (!S.lcOff[id] || S.lcOff[id].k !== k) S.lcOff[id] = {k, off: new Set()};
  return S.lcOff[id].off;
}
const lcPosOff = st => lcOffSet(st.id, st.stack + '|' + st.mode);
function lcBil(D) {
  // the balance sheet as a small chart: positions stacked, net worth as the line
  const pr = D.balance.projection || null, proj = pr ? Object.fromEntries(pr.rows.map(r => [r.id, r.amounts])) : {};
  const months = [...D.months, ...(pr ? (D.plan_months || []) : [])], vs = w => months.map(m => w[m] == null ? null : w[m] * defl(m));
  const series = D.balance.rows.filter(r => r.group && ROLE[r.role]).map(r => ({key: r.id, label: ROLE[r.role][0], color: ROLE[r.role][1], vals: vs(Object.assign({}, r.amounts, proj[r.id] || {}))}))
    .filter(x => x.vals.some(v => v != null && Math.abs(v) >= 0.005));
  const nwAll = pr ? Object.assign({}, D.balance.net_worth, pr.net_worth) : D.balance.net_worth;
  return {months, ist: D.months.length, vals: vs(nwAll), series};
}
// which of the four charts is the large one at the top (the others are the small ones below the table)
// (S.lcOrder: the large one first, then the small ones in their order; enlarging a small one swaps it with the large one)
const VIEW_ORDER = ['balance', 'nw', 'sel', 'pos'];
const BIL_BLOCKS = ['chart', 'table', 'lines'];          // the balance sheet page from the top: large chart, table, small charts (opening rows does not move the chart)
const bilBlocks = () => Array.isArray(S.blocks) && S.blocks.length === 3 && BIL_BLOCKS.every(k => S.blocks.includes(k)) ? S.blocks.slice() : BIL_BLOCKS.slice();
const bigType = () => (S.lcOrder || VIEW_ORDER)[0];
// The balance sheet view: changes while using it last for this session only. "Ansicht speichern" keeps the current view on this
// device (ranges, expanded rows, the eye, which chart is large, selections) -- one for months and one for years; the one saved
// last opens at the start, and switching between months and years takes the ranges saved for that view. "Zurücksetzen" goes
// back to Kontor's default. Only what makes sense to keep: a range is kept as its length and always ends today (like "1 J"),
// the table always scrolls to the current month, a zoom on the y axis is not kept. The area is chosen elsewhere.
const VIEW_KEY = 'kontor.balanceView';
function viewLoad() {
  let v = null; try { v = JSON.parse(LS.get(VIEW_KEY) || 'null'); } catch (e) { v = null; }
  return v && v.views ? v : null;
}
const viewSaved = m => ((viewLoad() || {}).views || {})[m] || null;
function viewBchRange(b) {
  b = b || {}; S.bchRange = b.all ? null : undefined; S.bchBtn = b.btn || (b.all ? null : bigDefault()); S.bchLen = b.len || null;
}
function viewLcRange(lc) {
  S.lcRange = {}; S.lcLen = {};
  for (const [id, r] of Object.entries(lc || {})) { if (r && r.btn) S.lcRange[id] = [null, null, r.btn]; else if (r && r.len) S.lcLen[id] = r.len; }
}
function viewApply(saved) {
  const m = saved && saved.mode === 'years' ? 'years' : 'months', v = (saved && saved.views && saved.views[m]) || {};
  const keys = o => Object.fromEntries(Object.entries(o && typeof o === 'object' ? o : {}).filter(([, x]) => x));
  S.mode = m;
  S.lcOrder = Array.isArray(v.order) && v.order.length === VIEW_ORDER.length && VIEW_ORDER.every(x => v.order.includes(x)) ? v.order.slice() : VIEW_ORDER.slice();
  S.bchLink = !!v.link; S.alleB = !!v.all; S.posOpen = keys(v.posOpen); S.depOpen = keys(v.depOpen);
  S.blocks = Array.isArray(v.blocks) ? v.blocks.slice() : null;
  S.bchPlan = !v.noPlan; S.bilW = +v.bilW || null;
  S.lcSel = Array.isArray(v.sel) ? v.sel.slice() : null; S.lcPos = typeof v.pos === 'string' ? v.pos : null; S.lcPosModes = keys(v.posMode);
  S.lcOff = Object.fromEntries(Object.entries(v.off || {}).map(([id, o]) => [id, {k: o.k, off: new Set(o.off || [])}]));
  // ranges: a button (months), all, or a length of its own -- each ending today
  S.bchModus = S.mode; viewBchRange(v.bch); S.bchYr = null;
  S.lcModus = S.mode; viewLcRange(v.lc);
}
function viewSnap() {
  const len = (i0, i1) => i1 - i0, v = {mode: S.mode, order: (S.lcOrder || VIEW_ORDER).slice()};     // months, as for the buttons
  if (bchLinked()) v.link = 1;
  if (S.alleB) v.all = 1;
  if (bilBlocks().join() !== BIL_BLOCKS.join()) v.blocks = bilBlocks();
  if (S.bchPlan === false) v.noPlan = 1;
  if (S.bilW) v.bilW = S.bilW;
  const on = o => Object.keys(o || {}).filter(k => o[k]);
  if (on(S.posOpen).length) v.posOpen = Object.fromEntries(on(S.posOpen).map(k => [k, 1]));
  if (on(S.depOpen).length) v.depOpen = Object.fromEntries(on(S.depOpen).map(k => [k, 1]));
  if (S.lcSel) v.sel = S.lcSel.slice();
  if (S.lcPos) v.pos = S.lcPos;
  if (on(S.lcPosModes).length) v.posMode = Object.assign({}, S.lcPosModes);
  const off = Object.entries(S.lcOff || {}).filter(([, o]) => o.off && o.off.size);
  if (off.length) v.off = Object.fromEntries(off.map(([id, o]) => [id, {k: o.k, off: [...o.off]}]));
  v.bch = S.bchRange === null ? {all: 1} : S.bchBtn ? {btn: S.bchBtn} : BCH.d ? {len: len(BCH.i0, BCH.i1)} : {};
  v.lc = {};
  for (const [id, st] of Object.entries(LC)) if (st && st.d) v.lc[id] = st.btn ? {btn: st.btn} : {len: len(st.i0, st.i1)};
  return v;
}
const viewBtns = () => `<span class="view-btns" data-ex="balance.toolbar.view"><button class="small secondary" id="view-save" title="${t('ansicht_standard_tip')}">${ICON.pin}<span class="lbl">${t('ansicht_standard')}</span></button>`
  + `<button class="small secondary" id="view-reset" title="${t('ansicht_reset_tip')}">${ICON.reset}<span class="lbl">${t('ansicht_reset')}</span></button></span>`;
// colour of the selection chart: the selected positions' colours mixed in equal parts (one position: its own colour)
const lcMix = rollen => (rollen || []).map(r => ROLE[r] && ROLE[r][1]).filter(Boolean)
  .reduce((m, c, k) => k ? `color-mix(in oklab, ${m} ${Math.round(k / (k + 1) * 100)}%, ${c})` : c, '') || 'var(--muted)';
function lcPosRole(D) {
  const roles = D.balance.rows.filter(r => r.group && ROLE[r.role]).map(r => r.role);
  const r = S.lcPos;
  if (roles.includes(r)) return r;
  const n = x => D.balance.rows.filter(a => !a.group && a.role === x).length;
  return roles.find(x => x === 'cash' && n(x) > 1) || roles.find(x => n(x) > 1) || roles[0] || null;
}
function vBilanzLines(D) {
  if ((D.months || []).length < 2) return '';
  const {avail, sel} = lcSelection(D);
  const rb = bchRanges(false);          // small charts: range in the top right corner
  const typeOf = {nw: 'nw', sel: 'sel', pos: 'pos', bil: 'balance'};
  const head = (id, title, extra, noVal) => `<div class="lc-head"><b class="lc-title">${title}</b><button class="lc-big" data-big="${typeOf[id]}" title="${t('lc_gross')}">${ICON.expand}</button><div class="seg small lc-rb" data-lc="${id}">${rb.map(([m, l]) => `<button data-m="${m}">${l}</button>`).join('')}</div></div>${noVal ? '' : `<div class="lc-row2" data-ex="balance.value">${extra || ''}<span class="lc-val" id="lc-${id}-val"></span><span class="lc-span" id="lc-${id}-span" title="${t('lc_span_tip')}"></span></div>`}`;
  const plot = id => `<div class="bch-plot lc-plot" id="lc-${id}-plot"><svg class="bch-svg" id="lc-${id}-svg"></svg><div class="bch-tip hidden" id="lc-${id}-tip"></div></div>`;
  const chips = avail.map(r => `<label class="lc-chip"><input type="checkbox" data-r="${r}" ${sel.includes(r) ? 'checked' : ''}><i style="background:${ROLE[r][1]}"></i>${esc(ROLE[r][0])}</label>`).join('');
  const card = {
    nw: () => `<div class="card bch lc" data-lc="nw" data-ex="balance.nw">${head('nw', t('nettovermoegen'))}${plot('nw')}<div class="lc-stats" id="lc-nw-stats" data-ex="balance.nw.stats"></div></div>`,
    bil: () => `<div class="card bch lc" data-lc="bil" data-ex="balance.bil">${head('bil', t('lc_bilanz'), '', true)}${plot('bil')}<div class="lc-legend" id="lc-bil-legend"></div></div>`,
    sel: () => `<div class="card bch lc" data-lc="sel" data-ex="balance.sel">${head('sel', (([tx, tip]) => `<span id="lc-sel-title" class="${tip ? 'tipped' : ''}" data-tip="${esc(tip)}" tabindex="0">${esc(tx)}</span>`)(lcSelTitle(sel, avail)))}${plot('sel')}<div class="lc-chips below" id="lc-chips">${chips}</div></div>`,
    pos: () => `<div class="card bch lc" data-lc="pos" data-ex="balance.pos">${head('pos', `<select id="lc-pos-sel" class="lc-pos-sel" title="${t('lc_pos_tip')}">${avail.map(r => `<option value="${r}" ${r === lcPosRole(D) ? 'selected' : ''}>${esc(ROLE[r][0])}</option>`).join('')}</select><button class="lc-mode hidden" id="lc-pos-mode" title="${t('lc_depot_tip')}">${t('lc_depot')}</button>`)}${plot('pos')}<div class="lc-chips below" id="lc-pos-accs"></div></div>`};
  // the small ones in their order (enlarging one swaps it with the large one, so any order is possible)
  return `<div class="cards lc-grid" id="lc-grid" data-ex="balance.lines">${(S.lcOrder || VIEW_ORDER).slice(1).map(x => card[x === 'balance' ? 'bil' : x]()).join('')}</div>`;
}
// growth in percent, short: 7,6 % · 13,7 % · 340 % · 2400 % (no thousands separator) · 12T % / 12k % (from 10 000 %);
// from a start of (almost) zero, or from 100 000 % on, it says nothing: no figure
const pctGrowth = (from, change) => {
  if (Math.abs(change) < 0.5 || Math.abs(from) < 1) return '';
  const p = change / Math.abs(from) * 100, sign = p > 0 ? '+' : '−', a = Math.abs(p);
  if (a >= 100000) return '';
  if (a >= 10000) return sign + Math.round(a / 1000).toLocaleString(LOCALE, {useGrouping: false}) + t('tsd_kurz') + ' %';
  return sign + a.toLocaleString(LOCALE, {maximumFractionDigits: a >= 100 ? 0 : 1, useGrouping: false}) + ' %';
};
function lcDraw(id) {
  const st = LC[id], box = $(`#lc-${id}-plot`), svg = $(`#lc-${id}-svg`); if (!st || !box || !svg) return;
  const d = st.d, W = Math.max(260, box.clientWidth), H = id === 'bil' ? 218 : 190, P = {l: 58, r: 10, t: 14, b: 24};     // the balance sheet: also the room of the value line
  const i0 = st.i0, i1 = st.i1, n = i1 - i0, ist = d.ist - 1;
  const vis = d.vals.slice(i0, i1 + 1).filter(v => v != null);
  // composition: only accounts that are not 0 € throughout the shown range (colours stay with the account)
  // composition: accounts (or securities) not 0 € throughout the range can be deselected; the total line stays the position
  const inWin = st.stack ? d.series.filter(x => x.vals.slice(i0, i1 + 1).some(v => v != null && Math.abs(v) >= 0.005)) : [];
  const off = st.stack ? lcPosOff(st) : new Set(), shown = inWin.filter(x => !off.has(x.key));
  // chips: at most three rows -- the more there are, the shorter the names (full name with the account on hover); the largest
  // first, the rest can be scrolled within the three rows
  if (st.stack) { const lgd = $(`#lc-${id}-legend`); if (lgd) lgd.innerHTML = inWin.map(x => `<span><i style="${swatch(x.color, x.hatch)}"></i>${esc(x.label)}</span>`).join(''); }
  if (st.stack) { const lg = $(`#lc-${id}-accs`); if (lg) {
    const n = inWin.length, max = n <= 6 ? 18 : n <= 9 ? 12 : n <= 15 ? 9 : 7, at = Math.min(i1, ist);
    const ord = inWin.slice().sort((a, b) => Math.abs(b.vals[at] || 0) - Math.abs(a.vals[at] || 0)), sn = shortNames(ord.map(x => x.label), max);
    lg.innerHTML = ord.map((x, k) => `<label class="lc-chip" title="${esc(x.full || x.label)}"><input type="checkbox" data-k="${esc(x.key)}" ${off.has(x.key) ? '' : 'checked'}><i style="${swatch(x.color, x.hatch)}"></i><span class="nm">${esc(sn[k])}</span></label>`).join(''); } }
  if (!vis.length) { svg.innerHTML = ''; svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('width', W); svg.setAttribute('height', H); ($(`#lc-${id}-val`) || {}).textContent = id === 'sel' && !st.title ? t('lc_nichts_gewaehlt') : t('keine_werte'); return; }
  let max = Math.max(...vis), min = Math.min(...vis);
  const ups = [], dns = [];
  if (st.stack) {                                       // stacked: positive parts up from zero, negative ones down
    for (let i = i0; i <= i1; i++) { let u = 0, l = 0; for (const s2 of shown) { const v = s2.vals[i] || 0; if (v > 0) u += v; else l += v; } ups.push(u); dns.push(l); }
    max = Math.max(0, ...ups, ...vis); min = Math.min(0, ...dns, ...vis);      // the position line always fits
  }
  if (max - min < 1) { max += 50; min -= 50; }
  const pad = (max - min) * 0.08; max += pad; if (!st.stack || min < 0) min -= pad;
  const yr = (S.lcYr || {})[id]; if (yr) [min, max] = yr;    // range set on the y axis (a tap there resets it)
  const ticks = axisTicks(min, max, 4, 4);                // at least four lines (finer round steps when needed)
  P.l = Math.max(30, Math.ceil(Math.max(...ticks.map(([v, r]) => textW(Fk(v, false, r))))) + 12);      // axis only as wide as its labels
  const x = i => P.l + (i - i0) * (W - P.l - P.r) / Math.max(1, n), y = v => P.t + (max - v) * (H - P.t - P.b) / (max - min), pf = v => v.toFixed(1);
  let g = '', pl = '';
  for (const [tk, ref] of ticks) g += `<line class="bch-grid${Math.abs(tk) < 1e-9 ? ' zero' : ''}" x1="${P.l}" x2="${W - P.r}" y1="${pf(y(tk))}" y2="${pf(y(tk))}"/><text class="bch-y" x="${P.l - 6}" y="${pf(y(tk) + 4)}">${Fk(tk, false, ref)}</text>`;
  g += monthAxis(d, i0, i1, x, P, W, H, false);          // first and last month labelled: the period of value and change
  // completed months solid, the running month dotted, the plan dashed; as in the large chart a veil lies over the areas of the
  // plan, and over the running month it leads softly from none to the plan's; the dashed vertical line marks the cut
  const done = ist - 1, run = ist >= i0 && ist <= i1 && ist > 0;
  let veil = '', gdef = '';
  if (run && done >= i0) { gdef = runGrad(`lc-${id}-rung`);
    veil += `<rect class="bch-run" fill="url(#lc-${id}-rung)" x="${pf(x(done))}" y="${P.t}" width="${pf(x(ist) - x(done))}" height="${H - P.t - P.b}"/>`; }
  if (ist < i1) { const xs = Math.max(P.l, x(Math.max(ist, i0))); veil += `<rect class="bch-plan" x="${pf(xs)}" y="${P.t}" width="${pf(W - P.r - xs)}" height="${H - P.t - P.b}"/>`; }
  if (done >= i0 && done <= i1) g += `<line class="bch-today" x1="${pf(x(done))}" x2="${pf(x(done))}" y1="${P.t - 4}" y2="${H - P.b}"/>`;
  const line = (a, b, c, dot) => { const ps = []; for (let i = a; i <= b; i++) if (d.vals[i] != null) ps.push([x(i), y(d.vals[i])]); return heroLine(ps, c, st.color, dot); };
  // the area reaches into the plan too (under its veil)
  const area = () => { const ps = []; let first = null, last = null; for (let i = i0; i <= i1; i++) if (d.vals[i] != null) { ps.push([x(i), y(d.vals[i])]); if (first == null) first = i; last = i; }
    // filled towards zero (upwards when negative); with zero outside the axis up to the plot edge on its side
    const yb = pf(Math.max(P.t, Math.min(H - P.b, y(0))));
    return ps.length > 1 ? `<path class="lc-area" d="${smoothD(ps)}L${pf(x(last))} ${yb}L${pf(x(first))} ${yb}Z" style="fill:${st.color}"/>` : ''; };
  const lines = c => (ist < i1 ? line(Math.max(i0, ist), i1, c + ' plan') : '') + (run ? line(Math.max(i0, done), ist, c + ' run', true) : '') + line(i0, Math.min(i1, done), c);
  if (st.stack) {
    const df = {s: ''};
    const bands = sign => {
      const base = Array(n + 1).fill(0); let out = '';
      shown.slice().reverse().forEach(sx => {           // first account on top, as in the table
        const si = d.series.indexOf(sx), top = [], bot = [];
        for (let k = 0; k <= n; k++) { const v = sx.vals[i0 + k] || 0, part = sign > 0 ? Math.max(0, v) : Math.min(0, v); bot.push(base[k]); base[k] += part; top.push(base[k]); }
        if (top.every((tv, k) => Math.abs(tv - bot[k]) < 0.005)) return;
        const fill = bandFill(df, `lc-${id}-${si}`, sx.color, sx.hatch);
        out += `<path class="lc-band" data-s="${si}" d="${smoothD(top.map((tv, k) => [x(i0 + k), y(tv)]))}${smoothD(bot.map((bv, k) => [x(i0 + k), y(bv)]), true)}Z" fill="${fill}"/>`;
      });
      return out;
    };
    const b2 = bands(1) + bands(-1);
    // total as a solid line in the position colour above the lighter bands
    pl = b2 + veil + lines('lc-total');
    g = `<defs>${df.s}${gdef}</defs>` + g;
  } else { pl = area() + veil + lines('bch-nw'); if (gdef) g = `<defs>${gdef}</defs>` + g; }
  // with a range set on the y axis the curves are cut at the plot edges
  g += yr ? `<clipPath id="lcc-${id}"><rect x="${P.l}" y="${P.t}" width="${W - P.l - P.r}" height="${H - P.t - P.b}"/></clipPath><g clip-path="url(#lcc-${id})">${pl}</g>` : pl;
  g += `<g id="lc-${id}-hover"></g><rect class="bch-sel hidden" id="lc-${id}-brush" y="${P.t}" height="${H - P.t - P.b}"/><rect class="bch-hit" id="lc-${id}-hit" x="${P.l}" y="0" width="${W - P.l - P.r}" height="${H}"/><rect class="bch-yax${yr ? ' on' : ''}" x="0" y="0" width="${P.l - 2}" height="${H}"><title>${t('bch_yax_tip')}</title></rect><rect class="bch-pan" x="${P.l}" y="${H - P.b + 2}" width="${W - P.l - P.r}" height="${P.b - 2}"/>`;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('width', W); svg.setAttribute('height', H); svg.innerHTML = g; svg.classList.remove('hl');
  st.shown = shown;
  st.geo = {W, H, P, x, y, min, max, inv: py => max - (py - P.t) * (max - min) / Math.max(1, H - P.t - P.b), idx: px => Math.max(i0, Math.min(i1, Math.round(i0 + (px - P.l) * n / Math.max(1, W - P.l - P.r))))};
  // value today and change over the visible actual months
  let a = null, z = null; for (let i = i0; i <= Math.min(i1, ist); i++) if (d.vals[i] != null) { if (a == null) a = i; z = i; }
  const vEl = $(`#lc-${id}-val`);
  if (vEl) vEl.innerHTML = id === 'bil' ? '' : valChange(d.vals, a, z);      // the balance sheet: no change (the net worth chart shows it)
  // key figures of the reference period (net worth card): average change per month, highest and lowest month-end
  const stEl = $(`#lc-${id}-stats`);
  if (stEl) {
    let hi = null, lo = null; for (let i = a ?? 0; z != null && i <= z; i++) if (d.vals[i] != null) { if (hi == null || d.vals[i] > d.vals[hi]) hi = i; if (lo == null || d.vals[i] < d.vals[lo]) lo = i; }
    const avg = a != null && z > a ? (d.vals[z] - d.vals[a]) / (z - a) : null, cell = (l, v, m, c) => `<div><span>${l}</span><b${c ? ` class="${c}"` : ''}>${v}</b>${m ? `<small>${m}</small>` : ''}</div>`;
    stEl.innerHTML = hi == null ? '' : (avg != null ? cell(t('lc_avg_month'), `${avg >= 0 ? '+' : ''}${F0(avg)} €`, '', avg >= 0 ? 'pos' : 'neg') : '')
      + cell(t('lc_high'), `${F0(d.vals[hi])} €`, ML(d.months[hi])) + cell(t('lc_low'), `${F0(d.vals[lo])} €`, ML(d.months[lo]));
  }
  // the period the value (end) and the change (start) refer to: the actual months in view; compact, top right
  // a range button is marked whenever the range has its length (also after zooming back); below it the length in words
  const span = st.i1 - st.i0;
  $$(`.lc-rb[data-lc="${id}"] button`).forEach(b => b.classList.toggle('on', +b.dataset.m === (st.btn != null ? st.btn : span)));
  const spEl = $(`#lc-${id}-span`); if (spEl) spEl.textContent = spanText(span);
  lcBindPlot(id);
}
// the length of a range in words: months up to 2 years, beyond that years and months ("2 Jahre 8 Mon.", half a year as "2 ½ Jahre")
const spanText = m => m % 12 === 0 ? (m === 12 ? t('lc_span_1j') : t('lc_span_j', m / 12)) : m <= 24 ? (m === 1 ? t('lc_span_1m') : t('lc_span_m', m))
  : m % 12 === 6 ? t('lc_span_jh', Math.floor(m / 12)) : t('lc_span_jm', Math.floor(m / 12), m % 12);
function lcSet(id, i0, i1, btn) {
  const st = LC[id], n = st.d.months.length; i0 = Math.max(0, Math.min(i0, n - 2)); i1 = Math.max(i0 + 1, Math.min(i1, n - 1));
  // a range button stays anchored to today only while the range is exactly its own; a range of that length ending today gets it
  if (btn) { const [a, z] = bchWindow(st.d, btn); if (a !== i0 || z !== i1) btn = null; }
  if (!btn && bchRanges(false).some(([m]) => m === i1 - i0)) { const [a, z] = bchWindow(st.d, i1 - i0); if (a === i0 && z === i1) btn = i1 - i0; }
  st.f0 = i0; st.f1 = i1;
  if (i0 === st.i0 && i1 === st.i1 && (btn ?? null) === st.btn) return;
  st.i0 = i0; st.i1 = i1; st.btn = btn ?? null; S.lcRange = Object.assign(S.lcRange || {}, {[id]: [st.d.months[i0], st.d.months[i1], st.btn]}); lcDraw(id);
}
function lcView(id, f0, span, keepBtn) {
  const st = LC[id], last = st.d.months.length - 1; span = Math.max(1, Math.min(last, span)); f0 = Math.max(0, Math.min(f0, last - span));
  const i0 = Math.round(f0), i1 = Math.min(last, i0 + Math.round(span));
  lcSet(id, i0, i1, keepBtn ? st.btn : null); st.f0 = f0; st.f1 = f0 + span;
}
function lcZoom(id, c, factor) {
  const st = LC[id], span = st.f1 - st.f0, ns = Math.max(1, Math.min(st.d.months.length - 1, span * factor));
  lcView(id, c - (c - st.f0) * ns / span, ns, false);
}
function lcHover(id, i, py) {
  const st = LC[id], d = st.d, G = st.geo, hv = $(`#lc-${id}-hover`), tip = $(`#lc-${id}-tip`); if (!hv || !tip) return;
  if (i == null || d.vals[i] == null) { hv.innerHTML = ''; tip.classList.add('hidden'); bchMark(null); if (st.stack) stackMark($(`#lc-${id}-svg`), 'lc-band', d, null); return; }
  const xi = G.x(i).toFixed(1), m = d.months[i];
  hv.innerHTML = `<line class="bch-cross" x1="${xi}" x2="${xi}" y1="${G.P.t}" y2="${G.H - G.P.b}"/><circle class="bch-dot" cx="${xi}" cy="${G.y(d.vals[i]).toFixed(1)}" r="4" style="stroke:${st.color}"/>`;
  const off = st.stack ? lcPosOff(st) : new Set();
  const list = st.stack ? d.series.filter(x => !off.has(x.key) && x.vals.slice(st.i0, st.i1 + 1).some(v => v != null && Math.abs(v) >= 0.005)) : (d.parts && d.parts.length > 1 ? d.parts : []);
  // with deselected series: the sum of the selected ones, besides the whole position
  const part = st.stack && off.size && list.length ? `<div class="bch-tip-nw"><span>${t('lc_summe_auswahl')}</span><b>${F0(list.reduce((s0, x) => s0 + (x.vals[i] || 0), 0))} €</b></div>` : '';
  const hit = st.stack && py != null && st.shown ? stackHit(st.shown, i, G.inv(py)) : null;
  if (st.stack) stackMark($(`#lc-${id}-svg`), 'lc-band', d, hit);
  const rows = list.filter(x => x.vals[i] != null && Math.abs(x.vals[i]) >= (st.stack ? 0.005 : 0.5)).map(x => `<div${x === hit ? ' class="on"' : ''}><i style="${swatch(x.color, x.hatch)}"></i><span>${esc(x.label)}</span><b>${Math.abs(x.vals[i]) < 1 ? F(x.vals[i]) : F0(x.vals[i])}</b></div>`).join('');
  const mon = `${MONATE_LANG[+m.slice(5) - 1]} ${m.slice(0, 4)}`, pill = i >= d.ist ? ` <span class="pill neutral">${t('plan')}</span>` : i === d.ist - 1 ? ` <span class="pill neutral">${t('laufender_monat')}</span>` : '';
  // a single line (net worth, one account): just the month and the value -- the chart's title says what it is
  tip.innerHTML = list.length ? `<div class="bch-tip-h">${mon}${pill}</div>${rows}${part}<div class="bch-tip-nw"><i class="nw-sw" style="background:${st.color}"></i><span>${esc(!st.stack ? t('summe_label') : st.title)}</span><b>${F0(d.vals[i])} €</b></div>`
    : `<div class="bch-tip-h"><span class="tip-m">${mon}</span>${pill}<b>${F0(d.vals[i])} €</b></div>`;
  tip.classList.toggle('one', !list.length);
  tip.classList.remove('hidden');
  const bw = $(`#lc-${id}-plot`).clientWidth, tw = tip.offsetWidth, px = G.x(i);
  tip.style.left = (px + 14 + tw > bw ? px - 14 - tw : px + 14) + 'px';
  bchMark(m);
}
function lcBindPlot(id) {
  const st = LC[id], hit = $(`#lc-${id}-hit`); if (!hit) return;
  const pt = e => { const r = $(`#lc-${id}-svg`).getBoundingClientRect(); return (e.clientX - r.left) * LC[id].geo.W / r.width; };
  const at = px => { const G = st.geo; return st.f0 + (px - G.P.l) * (st.f1 - st.f0) / Math.max(1, G.W - G.P.l - G.P.r); };
  const pty = e => { const r = $(`#lc-${id}-svg`).getBoundingClientRect(); return (e.clientY - r.top) * LC[id].geo.H / r.height; };
  const gest = chartGestures($(`#lc-${id}-svg`), {pt, pty, geo: () => LC[id].geo, ygeo: () => LC[id].geo, range: () => [LC[id].f0, LC[id].f1], view: (f0, span, keep) => lcView(id, f0, span, keep),
    yview: (lo, hi) => { S.lcYr = Object.assign(S.lcYr || {}, {[id]: lo == null ? null : [lo, hi]}); lcDraw(id); }, hide: () => lcHover(id, null),
    panHover: px => lcHover(id, LC[id].geo.idx(px)), panTap: px => { lcHover(id, null); bchJump(LC[id].d.months[LC[id].geo.idx(px)]); }});
  hit.addEventListener('pointermove', e => {
    if (gest.busy()) { lcHover(id, null); return; }
    const px = pt(e), G = st.geo;
    if (st.drag) { const sel = $(`#lc-${id}-brush`), a = Math.max(G.P.l, Math.min(st.drag.x, px)), b = Math.min(G.W - G.P.r, Math.max(st.drag.x, px)); sel.setAttribute('x', a); sel.setAttribute('width', b - a); sel.classList.toggle('hidden', b - a < 4); }
    lcHover(id, G.idx(px), pty(e));
  });
  hit.addEventListener('pointerleave', () => { if (!st.drag) lcHover(id, null); });
  hit.addEventListener('pointerdown', e => { if (e.pointerType === 'touch') { st.tap = pt(e); return; } st.drag = {x: pt(e)}; hit.setPointerCapture(e.pointerId); });
  hit.addEventListener('pointerup', e => {
    if (e.pointerType === 'touch' && (gest.busy() || st.tap == null || Math.abs(pt(e) - st.tap) > 10)) { st.tap = null; lcHover(id, null); return; }   // only a tap jumps to the column
    const G = st.geo, px = pt(e), dr = st.drag; st.drag = null;
    if (dr && Math.abs(px - dr.x) > 6) { lcSet(id, G.idx(Math.min(px, dr.x)), G.idx(Math.max(px, dr.x))); return; }
    const sel = $(`#lc-${id}-brush`); if (sel) sel.classList.add('hidden');
    bchJump(st.d.months[G.idx(px)]);
  });
  hit.addEventListener('dblclick', e => lcZoom(id, at(pt(e)), 0.5));
  hit.addEventListener('wheel', e => {
    if (st.gesture) return;
    if (e.ctrlKey) { e.preventDefault(); lcZoom(id, at(pt(e)), Math.exp(e.deltaY * 0.01)); return; }
    if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
    const span = st.f1 - st.f0, G = st.geo; if (span >= st.d.months.length - 1) return;
    e.preventDefault(); lcView(id, st.f0 + e.deltaX * span / Math.max(1, G.W - G.P.l - G.P.r), span, true);
  }, {passive: false});
  hit.addEventListener('gesturestart', e => { e.preventDefault(); lcHover(id, null); st.gesture = gest.multi() ? null : {c: at(pt(e)), span: st.f1 - st.f0, f0: st.f0}; });
  hit.addEventListener('gesturechange', e => { e.preventDefault(); const g = st.gesture; if (!g || !e.scale || gest.multi()) return; const ns = Math.max(1, Math.min(st.d.months.length - 1, g.span / e.scale)); lcView(id, g.c - (g.c - g.f0) * ns / g.span, ns, false); });
  hit.addEventListener('gestureend', e => { e.preventDefault(); st.gesture = null; });
}
function lcInit(id, D, rollen, title, color, stack) {
  // range kept as months (survives rebuilds); a range button stays anchored to today
  const mode = stack && stack !== '__bil' ? lcPosMode(D, stack) : null, d = stack === '__bil' ? lcBil(D) : stack ? lcStack(D, stack, mode) : lcData(D, rollen), n = d.months.length, r = (S.lcRange || {})[id];
  let i0, i1, btn = r ? r[2] : bchDefault();             // default: 1 year (months view) or 3 years (years view) up to today
  const len = (S.lcLen || {})[id];
  if (len) {                                             // a length of its own (kept as default), ending today
    delete S.lcLen[id]; [i0, i1] = bchWindow(d, len); S.lcRange = Object.assign(S.lcRange || {}, {[id]: [d.months[i0], d.months[i1], null]});
    LC[id] = {id, d, i0, i1, f0: i0, f1: i1, btn: null, title, color, stack: stack || false, mode, drag: null, gesture: null, geo: null};
    return;
  }
  if (btn === 0 || (btn && !bchRanges(false).some(([m]) => m === btn))) btn = bchDefault();     // not offered in this view
  if (btn === 0) { i0 = 0; i1 = n - 1; }
  else if (btn) [i0, i1] = bchWindow(d, btn);
  else { i0 = d.months.indexOf(r[0]); i1 = d.months.indexOf(r[1]); if (i0 < 0 || i1 <= i0) { btn = bchDefault(); [i0, i1] = bchWindow(d, btn); } }
  LC[id] = {id, d, i0, i1, f0: i0, f1: i1, btn, title, color, stack: stack || false, mode, drag: null, gesture: null, geo: null};
}
function bindBilanzLines(main) {
  const grid = $('#lc-grid', main), D = B(); if (!grid || !D) return;
  if (S.lcModus !== S.mode) { S.lcModus = S.mode; viewLcRange((viewSaved(S.mode) || {}).lc); }      // view switched: its own default range
  const has = id => !!$(`.lc[data-lc="${id}"]`, grid);
  const draw = () => {
    const {sel} = lcSelection(D);
    if (has('nw')) { lcInit('nw', D, null, t('nettovermoegen'), 'var(--c-nw)'); lcDraw('nw'); }
    if (has('sel')) { lcInit('sel', D, sel, sel.map(r => ROLE[r][0]).join(' + '), lcMix(sel)); lcDraw('sel'); }
    const pr = lcPosRole(D);
    if (pr && has('pos')) { lcInit('pos', D, null, ROLE[pr][0], ROLE[pr][1], pr); lcDraw('pos'); }
    if (has('bil')) { lcInit('bil', D, null, t('nettovermoegen'), 'var(--c-nw)', '__bil'); lcDraw('bil'); }
  };
  $$('.lc-big', grid).forEach(b => b.addEventListener('click', () => {
    const o = (S.lcOrder || VIEW_ORDER).slice(), i = o.indexOf(b.dataset.big); if (i < 1) return;
    [o[0], o[i]] = [o[i], o[0]]; S.lcOrder = o; if (S.bchBtn) S.bchRange = undefined;      // a range button: its window for the new large chart (plan ahead only for the balance sheet)
    route();
  }));
  const ps = $('#lc-pos-sel', grid), pm = $('#lc-pos-mode', grid);
  const posMode = () => { if (!pm || !ps) return; const has = lcHasDepot(D, ps.value); pm.classList.toggle('hidden', !has); pm.classList.toggle('on', has && lcPosMode(D, ps.value) === 'depot'); };
  const posRedraw = () => {
    const keep = LC.pos ? [LC.pos.i0, LC.pos.i1, LC.pos.btn] : null;
    lcInit('pos', D, null, ROLE[ps.value][0], ROLE[ps.value][1], ps.value);
    if (keep) Object.assign(LC.pos, {i0: keep[0], i1: keep[1], f0: keep[0], f1: keep[1], btn: keep[2]});
    posMode(); lcDraw('pos');
  };
  if (ps) ps.addEventListener('change', () => { S.lcPos = ps.value; posRedraw(); });
  if (pm) pm.addEventListener('click', () => {
    S.lcPosModes = Object.assign({}, S.lcPosModes, {[ps.value]: lcPosMode(D, ps.value) === 'depot' ? 'accounts' : 'depot'});
    posRedraw();
  });
  posMode();
  const pa = $('#lc-pos-accs', grid);
  if (pa) pa.addEventListener('change', e => {
    const cb = e.target.closest('input[data-k]'); if (!cb || !LC.pos) return;
    const off = lcPosOff(LC.pos); if (cb.checked) off.delete(cb.dataset.k); else off.add(cb.dataset.k);
    lcDraw('pos');
  });
  $$('.lc-rb', grid).forEach(seg => seg.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return; const id = seg.dataset.lc, st = LC[id], m = +b.dataset.m;
    if (!m) lcSet(id, 0, st.d.months.length - 1, 0); else { const [a, z] = bchWindow(st.d, m); lcSet(id, a, z, m); }
  }));
  $$('#lc-chips input', grid).forEach(cb => cb.addEventListener('change', () => {
    const sel = $$('#lc-chips input:checked', grid).map(x => x.dataset.r);
    S.lcSel = sel.slice();
    const keep = LC.sel ? [LC.sel.i0, LC.sel.i1, LC.sel.btn] : null, [tx, tip] = lcSelTitle(sel, lcSelection(D).avail), te = $('#lc-sel-title', grid);
    if (te) { te.textContent = tx; te.dataset.tip = tip; te.classList.toggle('tipped', !!tip); }
    lcInit('sel', D, sel, sel.map(r => ROLE[r][0]).join(' + '), lcMix(sel));
    if (keep) Object.assign(LC.sel, {i0: keep[0], i1: keep[1], f0: keep[0], f1: keep[1], btn: keep[2]});
    lcDraw('sel');
  }));
  draw();
  if (LC.ro) LC.ro.disconnect();
  let last = 0; LC.ro = new ResizeObserver(onResizeFrame(() => { if (PRINT.on) return; const w = $('.lc-plot', grid); if (w && Math.abs(w.clientWidth - last) > 2) { last = w.clientWidth; ['nw', 'sel', 'pos', 'bil'].forEach(id => { if (has(id) && LC[id]) lcDraw(id); }); } }));
  LC.ro.observe(grid);
}

// ---------------------------------------------------------------- Tabellen: Spalten rasten ein (nichts angeschnitten)
const colX = (w, el) => el.getBoundingClientRect().left - w.getBoundingClientRect().left - w.clientLeft + w.scrollLeft;   // Lage im Inhalt
// the column headings of a table after its first (names) column -- not the end padding, not the empty cell of a frozen names column
const colHeads = w => $$('thead th', w).slice(1).filter(th => !th.classList.contains('snap-pad') && !th.classList.contains('cf-ph'));
// Safari draws every pinned cell as a layer of its own and, scrolling fast, hundreds of them too late: the figures are there,
// the names come after. So the names of a long table are a table of their own, pinned to the left as one piece and lying over
// the table's first column, which keeps its heading (the corner) and empty cells -- the same columns, the same handlers.
// Both get the same widths and row heights.
const syncNamesOf = el => { const p = el && el.closest('.cf-pair'), a = p && $(':scope > table:not(.cf-names)', p), b = p && $(':scope > .cf-names', p); if (a && b) syncRows(a, b); };          // a row grew (fields shown): both sides as high again
function freezeNames(t) {
  if (!t || t.dataset.frozen || !t.closest('.wrap') || !t.tBodies.length) return;
  const left = document.createElement('table'), pair = document.createElement('div');
  left.className = t.className + ' cf-names'; left.setAttribute('role', 'presentation'); pair.className = 'cf-pair';
  if (t.tHead) left.appendChild(document.createElement('thead')).appendChild(document.createElement('tr')).appendChild(document.createElement('th')).className = 'cf-ph';
  for (const part of t.tBodies) {
    const dst = left.appendChild(document.createElement('tbody'));
    for (const tr of [...part.rows]) {
      const row = dst.appendChild(document.createElement('tr')), c = tr.cells[0];
      for (const a of tr.attributes) row.setAttribute(a.name, a.value);
      const ph = document.createElement(c.tagName); ph.className = 'cf-ph';
      tr.replaceChild(ph, c); row.appendChild(c);
    }
  }
  t.dataset.frozen = '1';
  t.parentNode.insertBefore(pair, t); pair.append(t, left);
  syncRows(t, left);
}
function syncRows(t, left) {
  // widths: the names' column as wide as the wider of the names and the corner; then every row as high as the higher side
  const corner = t.tHead && t.tHead.rows[0] && t.tHead.rows[0].cells[0], cells = [...left.querySelectorAll('tbody td, tbody th')];
  [left, corner].forEach(e => { if (e) e.style.width = e.style.minWidth = ''; });
  const w = Math.max(left.getBoundingClientRect().width, corner ? corner.getBoundingClientRect().width : 0);
  if (corner) corner.style.width = corner.style.minWidth = w + 'px';
  left.style.width = left.style.minWidth = w + 'px'; left.style.marginRight = -w + 'px';
  if (!cells.length) return;
  const ra = [...t.rows], rb = [...left.rows];
  if (ra.length !== rb.length) return;
  ra.concat(rb).forEach(r => { r.style.height = ''; });
  const ha = ra.map(r => r.getBoundingClientRect().height), hb = rb.map(r => r.getBoundingClientRect().height);
  // both sides the same whole pixels: fractional heights round differently in two tables (Safari) -- the row lines would not meet
  ra.forEach((r, i) => { const h = Math.ceil(Math.max(ha[i], hb[i]) - 0.01) + 'px'; r.style.height = h; rb[i].style.height = h; });
}
let FROZEN_W = 0;
let OV_T = null;
window.addEventListener('resize', () => { clearTimeout(OV_T); OV_T = setTimeout(() => { if (S.tab === 'overview' && !PRINT.on) ovDraw(); }, 120); });
window.addEventListener('resize', () => {            // another width can break names onto two lines (or back)
  const w = window.innerWidth; if (PRINT.on || Math.abs(w - FROZEN_W) < 2) return; FROZEN_W = w;
  clearTimeout(syncRows.t); syncRows.t = setTimeout(() => $$('.cf-pair').forEach(p => { const a = $(':scope > table:not(.cf-names)', p), b = $(':scope > .cf-names', p); if (a && b) syncRows(a, b); }), 120);
});
// The cash flow opens on the last finished month, the most important one: as many columns as fit -- one: that month; two: and the
// running month; three: and the month before it; four or more: and the first plan month at the right; eight or more: two plan months
// (earlier months to the left)
function cfScrollTo(w, c) {
  const ths = colHeads(w), i = ths.indexOf(c), avail = w.clientWidth - $('thead th', w).offsetWidth;
  const L = th => colX(w, th), Rt = th => colX(w, th) + th.offsetWidth, isSum = th => S.mode !== 'years' && th.classList.contains('year');
  // in view first the last closed month, then the running one, then the months before; a plan month only where eight columns
  // fit (six closed months, the running one and the first plan month) -- as in the balance sheet, the past comes first
  const before = ths.slice(0, Math.max(0, i)).filter(th => !isSum(th)), prev = before[before.length - 1], prev6 = before[before.length - 6];
  const plan = ths.slice(i + 1).find(th => th.classList.contains('plan') && !isSum(th));
  const right = plan && prev6 && avail >= Rt(plan) - L(prev6) - 1 ? Rt(plan) : !prev || avail >= Rt(c) - L(prev) - 1 ? Rt(c) : Rt(prev);
  return snapLeft(w, right - w.clientWidth);
}
function snapLeft(w, target) {
  // naechster Spaltenanfang ab target (erste Spalte bleibt stehen)
  const ths = colHeads(w), sw = $('thead th', w).offsetWidth;
  const max = w.scrollWidth - w.clientWidth;
  const b = ths.map(th => Math.round(colX(w, th) - sw)).find(v => v >= target - 1);
  return Math.max(0, Math.min(max, b == null ? max : b));
}
// The table is put on a column's start once, when it is drawn; scrolling itself is left alone (snapping afterwards moved
// the figures a moment after you had stopped).
// where each value column starts (scroll position that puts it right after the first column)
function colStarts(w) {
  const first = $('thead th', w); if (!first) return [];
  return colHeads(w).map(th => Math.round(colX(w, th) - first.offsetWidth));
}
// A table drawn again stays where it was: the same column at the same distance from the first one (other figures can make
// the columns before it a little wider or narrower).
function scrollMark(w) { const x = w.scrollLeft, st = colStarts(w); let i = 0; st.forEach((v, k) => { if (v <= x + 1) i = k; }); return {x, n: w.querySelectorAll('thead th').length, i, off: st.length ? x - st[i] : 0}; }
function scrollBack(w, mark) { const st = colStarts(w); w.scrollLeft = mark.i < st.length ? Math.max(0, st[mark.i] + mark.off) : mark.x; }
function snapTable(w) {
  const t = $('table:not(.cf-names)', w), first = $('thead th', w); if (!t || !first) return;
  $$('.snap-pad', w).forEach(c => c.remove());
  w.classList.add('snap');
  const sw = first.offsetWidth, max = w.scrollWidth - w.clientWidth;
  if (max <= 0) return;
  // Leerspalte am Ende, damit auch ganz rechts die erste sichtbare Spalte vollstaendig ist
  const starts = colHeads(w).map(th => colX(w, th) - sw), b = starts.find(v => v >= max - 0.5);
  const padw = b == null ? 0 : b - max;
  if (padw > 0.5) $$('tr', t).forEach(tr => { const c = document.createElement(tr.parentNode.tagName === 'THEAD' ? 'th' : 'td'); c.className = 'snap-pad'; c.style.minWidth = c.style.width = padw + 'px'; tr.appendChild(c); });
}

// ---------------------------------------------------------------- Kapitalfluss / Planung
// Kapitalfluss-Zeilen: Schluessel (zeile/gruppe) bleiben deutsch, angezeigt wird der Text in deiner Sprache
const zLabel = z => z.lbl ? t(z.lbl[0], ...(z.lbl.slice(1).map(CP))) : CP(z.row);
const gLabel = z => z.glbl ? t(z.glbl[0], ...(z.glbl.slice(1).map(CP))) : CP(z.group);
// Gruende einer Abweichung (Pruefzeilen): je Monat, als Text fuer den Tooltip (mehrere Monate: mit Monatsnamen)
function ueGruende(ue, months, key) {
  const lines = [];
  for (const m of months) for (const [k, v, d] of (ue[m]?.[key] || [])) lines.push((months.length > 1 ? ML(m) + ': ' : '') + t(k, d) + ': ' + F(v) + ' €');
  return lines.join('\n');
}
const UE_OFFEN = new Set(['ue_rest', 'ue_unbekannt']);       // differences without a known cause: shown as a warning
// A cash flow statement: operating (income and expenses), investing, financing -- their sum is the change in cash; then what
// changed without a payment and the change in net worth. Keys stay German (sections of the data).
const SEC_LABEL = {operating: t('cf_operativ'), income: t('einnahmen'), expenses: t('ausgaben'), investing: t('cf_investitionen'), financing: t('cf_finanzierung'), valuation: t('cf_wertaenderungen'), unclear: t('cf_unklar')};
const SEC_HELP = {operating: 'cf_operativ', investing: 'cf_invest', financing: 'cf_finanz', valuation: 'cf_wert', unclear: 'cf_unklar'};
const SEC_ABBR = {operating: 'CFO', investing: 'CFI', financing: 'CFF'};     // the official short names (cash flow from operations, investing, financing)
const SEC_KEY = {operating: 'op', investing: 'inv', financing: 'fin', income: 'ein', expenses: 'aus', valuation: 'value'};          // the colour of the activity in the charts
const METH = {rolling12: t('12_monate'), rolling6: t('6_monate'), prev_year: t('vorjahresmonat'), fix: t('fester_betrag_monat'), yearly_amount: t('meth_jahresbetrag'), budget: t('meth_budget'), none: t('keine')};
// Planning: rules on three levels (the area's default, a position, a category -- the deepest one that sets a field counts) and
// how each plan cell came about, said in its tooltip (and given to the assistant with a right click on it)
const PLAN_AREA_METH = ['rolling12', 'rolling6', 'prev_year', 'budget', 'none'];
const PLAN_MODELS = ['even', 'careful', 'prev_year', 'budget'];
const PLAN_FIXED = {loans: 'darlehensplan_zins_auf_restsaldo', event: 'plan_aus_ereignis', property: 'plan_aus_kalkulation'};
const planPct = g => +g === 0 ? t('keine') : t('pw_pct_pa', FN(g, 1));
const planShare = s => FN(s * 100, s * 100 % 1 ? 1 : 0) + ' %';
function planSrc(from, isCat, P) {          // where a rule's field comes from
  if (from === 'category') return t('pw_von_eigen');
  if (from === 'position') return t(isCat ? 'pw_von_position' : 'pw_von_eigen');
  if (from === 'area') return P.model ? t('pw_von_modell', t(`pm_${P.model}`)) : t('pw_von_bereich');
  return from === 'kind' ? t('pw_von_art') : '';
}
function planIncSrc(r, isCat, sec, P) {
  if (r.inc_from !== 'standard') return planSrc(r.inc_from, isCat, P);
  return t(sec === 'income' ? 'pw_std_einnahmen' : sec === 'expenses' ? (P.expense_rate_own ? 'pw_std_ausgaben' : 'pw_std_inflation') : 'pw_std_sonst');
}
const planMethText = r => (METH[r.method] || r.method || '') + ((r.method === 'fix' || r.method === 'yearly_amount') && r.amount != null ? ' ' + F(r.amount) : '');
function planRuleLines(r, isCat, sec, P) {          // the rule in effect: method and increase, each with where it comes from
  if (!r || !r.method) return [];
  if (r.from === 'fixed') return [t(PLAN_FIXED[r.method] || 'plan')];
  return [t('pw_regel', planMethText(r), planSrc(r.from, isCat, P))].concat(r.method === 'none' ? [] : [t('pw_steig_regel', planPct(r.increase || 0), planIncSrc(r, isCat, sec, P))]);
}
// one plan month of a position (d: null) or of a category inside it: own value, the base, the increase, the rule
function planWhy(D, sec, z, d, m) {
  const P = D.plan || {}, x = d || z, p = x.plan || {}, r = p.rule || {}, b = p.base || {}, L = [];
  const v = (p.amounts || {})[m], s = (p.proposal || {})[m], own = (p.overwritten || []).includes(m) && !(p.ignored || []).includes(m);
  if (own) L.push(t('pw_eigener_wert', F(v), F(s)));
  if (r.from === 'fixed') return L.concat([t(PLAN_FIXED[r.method] || 'plan')]).join('\n');
  if (!d && p.cats) {          // a position with categories: their sum
    L.push(tn('pw_summe_kat', p.cats, F(s)));
    if (p.own_cats) L.push(tn('pw_kat_eigen', p.own_cats));
    if ((p.ignored || []).includes(m)) L.push(t('pw_ignoriert', F(((((D.plan || {}).rows || {})[sec + '/' + z.row] || {}).amounts || {})[m])));
    else if (own) L.push(t('pw_verteilt'));
    return L.concat(planRuleLines(r, false, sec, P)).join('\n');
  }
  if (d && (p.from_position || []).includes(m)) return L.concat([t('pw_aus_position', F((z.plan.amounts || {})[m]), F(v)), t('vorschlag_0', F(s))], planRuleLines(r, true, sec, P)).join('\n');
  const n = (D.plan_months || []).indexOf(m) + 1, g = +(r.increase || 0);
  if (r.method === 'none') L.push(t('pw_keine'));
  else if (r.method === 'prev_year') {
    const ly = (+m.slice(0, 4) - 1) + m.slice(4), act = !!x.amounts && ly in x.amounts;
    L.push(t('pw_vorjahr', ML(ly), F(act ? x.amounts[ly] : (p.amounts || {})[ly] ?? 0)) + (act ? '' : ' ' + t('pw_plan_kl')));
  } else if (b.share != null && b.budget_of) L.push(t('pw_anteil_budget', planShare(b.share), CP(b.budget_of), F(b.budget), F(b.value)));
  else if (b.share != null) L.push(t(b.of_kind === 'yearly_amount' ? 'pw_anteil_jahr' : 'pw_anteil', planShare(b.share), F(b.of), F(b.value)));
  else if (b.budget != null) L.push(t('pw_budget', F(b.budget)));
  else if (r.method === 'fix') L.push(t('pw_fest', F(b.amount)));
  else if (r.method === 'yearly_amount') L.push(t('pw_jahr', F(b.amount), F(b.value)));
  else { if (b.fallback) L.push(t('pw_kein_budget')); L.push(b.n ? tn('pw_avg', b.n, ML(b.months[0]), ML(b.months[1]), F(b.value)) : t('pw_avg_leer')); }
  if (r.method !== 'none') {
    if (g) L.push(r.method === 'prev_year' ? t('pw_faktor_vj', FN(1 + g / 100, 4), FN(g, 1)) : t('pw_faktor', FN(Math.pow(1 + g / 100, n / 12), 4), FN(g, 1), tn('pw_monate', n)));
    L.push(t('pw_ergebnis', F(s)));
  }
  return L.concat(planRuleLines(r, !!d, sec, P)).join('\n');
}
// a column of several months (a year): how many plan months it adds up, how many of them are your own, the rule
function planWhyCol(D, sec, z, d, c) {
  const p = (d || z).plan || {}, pm = new Set(D.plan_months || []), k = c.months.filter(m => pm.has(m)), own = k.filter(m => (p.overwritten || []).includes(m)).length;
  return [tn('pw_summe_monate', k.length)].concat(own ? [tn('pw_eigene_n', own)] : [], !d && p.cats ? [tn('pw_summe_kat_kurz', p.cats)] : [], planRuleLines(p.rule, !!d, sec, D.plan || {})).join('\n');
}
// the rule of a row as a tag beside its name (own: marked), its tooltip saying where each part comes from
function planTag(D, sec, z, d) {
  const p = (d || z).plan || {}, r = p.rule || {}; if (!r.method || r.from === 'fixed') return '';
  const own = r.from === (d ? 'category' : 'position') || r.inc_from === (d ? 'category' : 'position');
  const tip = planRuleLines(r, !!d, sec, D.plan || {}).concat(!d && p.own_cats ? [tn('pw_kat_eigen', p.own_cats)] : [], p.budget ? [t('pw_budget_mm', F0(p.budget))] : []).join('\n');
  return `<span class="tag tipped${own ? ' own' : ''}" tabindex="0" data-tip="${esc(tip)}">${esc(METH[r.method] || r.method)}${p.budget ? esc(t('budget') + F0(p.budget)) : ''}${!d && p.own_cats ? ' · ' + esc(tn('pw_kat_eigen_kurz', p.own_cats)) : ''}</span>`;
}
// the fields of a row's own rule: method (Standard / as the position), amount (fixed or annual amount only), increase (Standard / none / own)
function planEdit(key, cat, own, nOv) {
  const isCat = cat != null, m = own.method || '', g = own.increase_percent_pa, gs = g == null ? '' : +g === 0 ? '0' : 'own';
  return `<div class="edit" data-key="${esc(key)}"${isCat ? ` data-cat="${esc(cat)}"` : ''}>`
    + `<select class="meth" title="${esc(t('pr_methode_tip'))}"><option value="">${t(isCat ? 'pr_wie_position' : 'standard')}</option>${Object.entries(METH).map(([mm, ml]) => `<option value="${mm}" ${m === mm ? 'selected' : ''}>${ml}</option>`).join('')}</select>`
    + `<input class="amount${m === 'fix' || m === 'yearly_amount' ? '' : ' hidden'}" type="number" step="0.01" placeholder="${t('betrag')}" value="${own.amount ?? ''}" title="${esc(t('betrag_fuer_fester_betrag_jahresbetrag'))}">`
    + `<select class="steig-art" title="${esc(t('pr_steig_tip'))}"><option value="">${t(isCat ? 'pr_steig_wie_position' : 'pr_steig_standard')}</option><option value="0" ${gs === '0' ? 'selected' : ''}>${t('pr_steig_keine')}</option><option value="own" ${gs === 'own' ? 'selected' : ''}>${t('pr_steig_eigene')}</option></select>`
    + `<input class="pct steig${gs === 'own' ? '' : ' hidden'}" type="number" step="0.1" placeholder="% p.a." value="${gs === 'own' ? g : ''}" title="${esc(t('pr_steig_tip'))}">`
    + `<button class="save small" title="${t('uebernehmen')}">✓</button>${nOv ? `<button class="small secondary reset-row" data-key="${esc(key)}"${isCat ? ` data-cat="${esc(cat)}"` : ''} title="${t('alle_ueberschreibungen_loeschen')}">↺</button>` : ''}</div>`;
}
// the plan's key figures over its next 12 months, each with how it is computed in its tooltip
function vPlanFigures(D) {
  const f = D.plan_figures; if (!f || !f.n) return '';
  const span = `${ML(f.months[0])} – ${ML(f.months[1])}`, pc = x => x == null ? '–' : FN(x * 100, 1) + ' %';
  const k = (l, v, tip) => `<div class="k tipped" tabindex="0" data-tip="${esc(tip)}"><div class="l">${l}</div><div class="v">${v}</div></div>`;
  return `<div class="kpis plan-kpis" data-ex="planning.figures">`
    + k(t('pf_sparquote'), pc(f.saving_rate), t(f.saving_rate == null ? 'pf_ohne_einnahmen' : 'pf_sparquote_tip', F0(f.surplus), F0(f.income), span))
    + k(t('pf_reichweite'), f.runway_months == null ? '–' : tn('pf_monate', f.runway_months, FN(f.runway_months, 1)),
      t(f.runway_months == null ? 'pf_reichweite_waechst' : 'pf_reichweite_tip', F0(f.cash), ML(f.cash_month), F0(Math.abs(f.cash_change_month)), span))
    + k(t('pf_zinslast'), pc(f.interest_rate), t(f.interest_rate == null ? 'pf_ohne_einnahmen' : 'pf_zinslast_tip', F0(f.interest), F0(f.income), span))
    + '</div>';
}
// the area's settings: its planning model (the default rule with one click), the default rule per side, the rates and the horizon
function vPlanParams(D) {
  const P = D.plan || {}, d = P.defaults || {}, di = d.income || {}, de = d.expenses || {};
  const msel = (id, cur) => `<select id="${id}">${PLAN_AREA_METH.map(x => `<option value="${x}" ${cur === x ? 'selected' : ''}>${METH[x]}</option>`).join('')}</select>`;
  const gsel = (id, cur) => `<select id="${id}" title="${esc(t('pp_steig_tip'))}"><option value="">${t('pp_mit_steig')}</option><option value="0" ${cur != null && +cur === 0 ? 'selected' : ''}>${t('pp_ohne_steig')}</option></select>`;
  return `<div class="card" data-ex="planning.params" style="margin-bottom:12px"><h3>${t('parameter')}</h3>`
    + `<div class="row tight" data-ex="planning.params.model"><span>${t('pp_modell', hq('plan_modell'))}</span><div class="seg small" id="p_model" role="group" aria-label="${esc(t('pp_modell', ''))}">${PLAN_MODELS.map(k => `<button data-m="${k}" class="${P.model === k ? 'on' : ''}" title="${esc(t(`pm_${k}_tip`))}">${t(`pm_${k}`)}</button>`).join('')}</div>${P.model ? '' : `<span class="tag">${t('pm_eigenes')}</span>`}</div>`
    + `<div class="row tight"><label>${t('pp_einnahmen', hq('method'))} ${msel('p_m_in', di.method)}</label>${gsel('p_g_in', di.increase_percent_pa)}<span class="tb-sep"></span><label>${t('pp_ausgaben')} ${msel('p_m_out', de.method)}</label>${gsel('p_g_out', de.increase_percent_pa)}</div>`
    + `<div class="row tight"><label>${t('horizont')} <input id="p_horizont" type="number" min="1" max="240" value="${P.horizon_months ?? 24}" style="width:70px"> ${t('monate')}</label>
      <label>${t('inflation_0', hq('inflation'))} <input id="p_infl" type="number" step="0.1" value="${P.inflation_percent_pa ?? 2}" style="width:64px"> % p.a.</label>
      <label>${t('steigerung_einnahmen_0', hq('steig_ein'))} <input id="p_se" type="number" step="0.1" value="${P.income_increase_percent_pa ?? 0}" style="width:64px"> %</label>
      <label>${t('pp_steig_ausgaben')} <input id="p_sa" type="number" step="0.1" value="${P.expense_rate_own ? P.expense_increase_percent_pa ?? '' : ''}" placeholder="${t('inflation')}" style="width:112px"> %</label>
      <label>${t('rendite_wertpapiere_anlagen_0', hq('rendite'))} <input id="p_rendite" type="number" step="0.1" value="${P.return_percent_pa ?? 0}" style="width:64px"> %</label>
      <button id="p_save" class="small">${t('uebernehmen')}</button><button id="p_reset" class="small secondary" title="${t('alle_planeinstellungen_dieses_bereichs')}">${t('plan_zuruecksetzen')}</button></div></div>`;
}
// what a changed rule sits above (your own values and rules further down), for the question: keep them or replace them
function planConflictHtml(c) {
  const D = B(), zs = new Map(D.cashflow.sections.flatMap(x => x.rows.map(z => [x.name + '/' + z.row, z])));
  const name = (key, cat) => { const z = zs.get(key), n = z ? zLabel(z) : CP(key.split('/').slice(1).join('/')); return cat ? CP(cat) : cat == null ? n : n + ' › ' + t('cf_geschaetzt'); };          // a category by its own path
  const rule = r => { const inc = r.increase_percent_pa ?? r.increase; return [r.method ? planMethText(r) : '', inc != null ? t('pk_steig', planPct(inc)) : ''].filter(Boolean).join(' · ') || t('standard'); };
  const more = (n, k) => n > k ? `<div class="muted small">${t('pk_weitere', n - k)}</div>` : '';
  let h = `<b>${t('pk_frage')}</b>`;
  if (c.values.length) h += `<div class="pk-h">${tn('pk_werte', c.values.length)}</div><div class="pk-list"><table class="plain"><thead><tr><th>${t('pk_zeile')}</th><th>${t('monat_2')}</th><th class="num">${t('pk_eigener')}</th><th class="num">${t('pk_neu')}</th></tr></thead><tbody>`
    + c.values.slice(0, 500).map(v => `<tr><td>${esc(name(v.row, v.category))}</td><td>${ML(v.month)}</td><td class="num">${F(v.own)}</td><td class="num">${F(v.new)}</td></tr>`).join('') + `</tbody></table>${more(c.values.length, 500)}</div>`;
  if (c.rules.length) h += `<div class="pk-h">${tn('pk_regeln', c.rules.length)}</div><div class="pk-list"><table class="plain"><thead><tr><th>${t('pk_zeile')}</th><th>${t('pk_eigene_regel')}</th><th>${t('pk_neue_regel')}</th></tr></thead><tbody>`
    + c.rules.slice(0, 500).map(r => `<tr><td>${esc(name(r.row, r.category))}</td><td>${esc(rule(r.own))}</td><td>${esc(rule(r.new || {}))}</td></tr>`).join('') + `</tbody></table>${more(c.rules.length, 500)}</div>`;
  return h;
}
// How far the table is opened: 0 overview (activities with income, expenses and the kinds of investing and financing: one
// page), 1 positions (and the accounts and loans), 2 everything (MoneyMoney's categories). A row you open or close yourself
// keeps that until you choose a level again. depth: 0 activity, 1 income/expenses or a kind, 2 a position or account, 3 more.
// levels 0-3: main lines, overview, positions, details -- the cash flow opens at the overview, planning at the positions (its fields)
const cfLevel = () => S.tab === 'planning' ? S.planEbene : S.cfEbene;
const cfOpen = (id, depth) => S.cfTog[id] ?? (cfLevel() >= 3 || depth < cfLevel());
// the first year of the month view, one year back or forth (the year view shows all years)
function yearCtl() {
  const D = B(); if (!D || S.mode === 'years' || !(D.months || []).length) return '';
  const min = +D.months[0].slice(0, 4), max = +String(D.actual_until || D.months[D.months.length - 1]).slice(0, 4);
  if (min >= max) return '';
  const fy = Math.min(max, Math.max(min, firstYear(D)));
  return `<div class="stepper" id="von-jahr" data-min="${min}" data-max="${max}" data-y="${fy}" title="${t('von_jahr_tip')}"><button data-d="-1" ${fy <= min ? 'disabled' : ''} aria-label="${t('frueheres_jahr')}">‹</button>`
    + `<span>${t('ab_jahr', fy)}</span><button data-d="1" ${fy >= max ? 'disabled' : ''} aria-label="${t('spaeteres_jahr')}">›</button></div>`;
}
function vKapitalfluss(editable) {
  const D = B(); if (!D) return noData;
  const C = cols(), KF = D.cashflow, sums = KF.sums || {}, P = D.plan || {};
  CF.tblCols = C.map(c => ({months: c.months.filter(m => m <= D.actual_until), label: c.label})); CF.zs = [];          // a click on a category's figure: its transactions
  // actual and plan values of a row merged once (not per cell: a row has hundreds of months)
  const mv = new Map(), ms = new Map();
  const vOf = (z, c) => { let v = mv.get(z); if (!v) mv.set(z, v = Object.assign({}, z.amounts, (z.plan && z.plan.amounts) || {})); return sumOver(v, c.months); };
  const sOf = (z, c) => { let v = ms.get(z); if (!v) ms.set(z, v = Object.assign({}, z.amounts, (z.plan && z.plan.proposal) || {})); return sumOver(v, c.months); };
  const levels = [t('cf_hauptebenen'), t('cf_ueberblick'), t('cf_positionen'), t('cf_details')];
  // The header cell of the table: how far it is opened, right above the triangles (Mac: four small outline icons, named in
  // their tooltips; iPhone: one large triangle -- each tap opens a level more, after everything it closes again), and the gear to the
  // positions' settings.
  const lvTips = [t('cf_ebene_tip_0'), t('cf_ebene_tip_1'), t('cf_ebene_tip_2'), t('cf_ebene_tip_3')], nextLv = (cfLevel() + 1) % 4;
  // each level as a small outline: its lines indented as deep as the level opens the table (main lines: all flush left)
  const lvIcon = n => `<svg viewBox="0 0 18 16" width="18" height="16" aria-hidden="true" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">${[[0, 0, 0], [0, 1, 1], [0, 1, 2], [0, 1, 2, 3]][n].map((d, k, a) => { const y = 2 + k * (12 / (a.length - 1)), x = 1.2 + d * 3.2; return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="1.1" stroke="none"/><path d="M${(x + 2.6).toFixed(1)} ${y.toFixed(1)}h${(9.4 - d * 1.4).toFixed(1)}"/>`; }).join('')}</svg>`;
  const lvCtl = `<div class="cf-lv"><div class="seg small" id="cf-ebene" role="group" aria-label="${esc(t('cf_ebene_tip'))}">${levels.map((l, i) => `<button data-e="${i}" class="${cfLevel() === i ? 'on' : ''}" title="${esc(lvTips[i])}" aria-label="${esc(l)}">${lvIcon(i)}</button>`).join('')}</div>`
    + `<button class="cf-lv-btn lv${cfLevel()}" data-e="${nextLv}" title="${esc(t(nextLv ? 'cf_weiter_aufklappen' : 'cf_alles_zuklappen'))}" aria-label="${esc(t(nextLv ? 'cf_weiter_aufklappen' : 'cf_alles_zuklappen'))}"><i>▸</i><span>${levels[cfLevel()]}</span></button>`
    + `<a class="cf-set" href="#accounts/positions" title="${esc(t('cf_positionen_einstellen'))}" aria-label="${esc(t('cf_positionen_einstellen'))}">${ICON.gear}</a></div>`;
  let h = `<div class="toolbar">${viewCtl()}${yearCtl()}<span class="tb-sep"></span>${alleCtl(0)}${editable ? swCtl('realan', S.real, t('inflationsbereinigt'), t('inflationsbereinigt_tip')) : planCtl()}<span class="sp"></span>`
    + `${xlsxBtn(editable ? 'planning' : 'cashflow')}</div>`;
  // hatched = plan, faded = the running month: plain to see (it lies ahead), so no legend for it; planning names what you overrode
  if (editable) h += `<div class="legend"><span class="o">${t('ueberschrieben')}</span><label class="chk"><input type="checkbox" id="vorschlag-an" ` + (S.proposal ? 'checked' : '') + `${t('vorschlagswerte_zeigen')}</label>` + (S.real ? `<em class="pill info">${t('planwerte_in_heutiger_kaufkraft')}</em>` : '') + '</div>';
  if (editable) h += vPlanParams(D) + vPlanFigures(D);
  h += (editable ? '<div class="wrap" data-ex="planning.table">' : '<div class="wrap" data-ex="cashflow.table">') + '<table class="cf-tbl' + (editable ? ' ptable' : '') + '">' + thead(lvCtl, C) + '<tbody>';
  // what each kind of row is, for the assistant (docs/ui): the cash flow by its kinds of rows; planning by its rows with a method
  const EXS = editable ? {} : {income: ' data-ex="cashflow.table.operating"', expenses: ' data-ex="cashflow.table.operating"', investing: ' data-ex="cashflow.table.investing"',
    financing: ' data-ex="cashflow.table.financing"', valuation: ' data-ex="cashflow.table.valuation"', unclear: ' data-ex="cashflow.table.unclear"'};
  const exOf = name => EXS[name] || '', EXROW = editable ? ' data-ex="planning.table.row"' : '', EXDET = editable ? ' data-ex="planning.table.category"' : ' data-ex="cashflow.table.category"';
  const EXT = k => editable ? '' : {op: ' data-ex="cashflow.table.operating"', fcf: ' data-ex="cashflow.table.fcf"', cash: ' data-ex="cashflow.table.cash"', check: ' data-ex="cashflow.table.check"',
    moves: ' data-ex="cashflow.table.moves"', nw: ' data-ex="cashflow.table.networth"'}[k];
  const secTotal = name => C.map(c => c.months.reduce((a, m) => a + (sums[m]?.[name] ?? 0) * defl(m), 0));
  // movements with their sign (+ too), balances without; in planning the figures stay as you edit them
  const FV = v => (!editable && v > 0.005 ? '+' : '') + FC(v);
  // a figure with bookings behind it: a click shows them (side panel) -- a row's name opens or closes it
  const hasTx = (zs, c) => !editable && zs.some(z => z.n && c.months.some(m => m <= D.actual_until && z.n[m]));
  CF.zsec = new Map(KF.sections.flatMap(x => x.rows.map(z => [z, x.name])));          // a row's section (its key: section and row)
  const zsOf = (zs, label) => editable ? '' : ` data-zs="${CF.zs.push({zs, label}) - 1}"`;
  const nums = (vals, zs) => vals.map((v, i) => `<td class="${cls(v, C[i])}${zs && hasTx(zs, C[i]) ? ' tx' : ''}">${FV(v)}</td>`).join('');
  // the triangle that opens and closes a row (rows without one keep its room, so the names stand in a line)
  const caret = (id, depth, open) => `<button class="disc" data-tog="${esc(id)}" data-depth="${depth}" aria-expanded="${open ? 'true' : 'false'}" title="${t(open ? 'cf_zuklappen' : 'cf_aufklappen')}">${open ? '▾' : '▸'}</button>`;
  const NOCARET = '<span class="disc none"></span>';
  // a name with its "?": the mark stays with the last word (where a narrow screen breaks the name)
  // ... and the official short name of a cash flow small beside it (CFO, CFI, CFF)
  const named = (label, help, abbr) => { const q = help ? hq(help) : '', a = abbr ? `<span class="cf-abbr">${esc(abbr)}</span>` : '', i = label.lastIndexOf(' ');
    return !q && !a ? label : label.slice(0, i + 1) + `<span class="nw">${label.slice(i + 1)}${a}${q}</span>`; };
  const dot = k => k ? `<i class="cf-key ${k}" aria-hidden="true"></i>` : '';
  const ind = d => d ? ' ind' + Math.min(d, 4) : '';
  // a section of the data at depth d0 (0: an activity, 1: income or expenses within operating)
  const section = (name, d0 = 0) => {
    const sek = KF.sections.find(s => s.name === name);
    if (!sek || (!sek.rows.length && !S.all)) return '';
    const sid = 's:' + name, sOpen = cfOpen(sid, name === 'valuation' || name === 'unclear' ? d0 + 1 : d0);      // overview: their sum only
    let o = `<tr class="${d0 ? 'sec2' : 'sec'}${ind(d0)}"${exOf(name)} data-tog="${esc(sid)}" data-depth="${d0}"${zsOf(sek.rows, SEC_LABEL[name] || name)}><td>${caret(sid, d0, sOpen)}${dot(SEC_KEY[name])}${named(SEC_LABEL[name] || esc(name), SEC_HELP[name], d0 ? '' : SEC_ABBR[name])}</td>${nums(secTotal(name), sek.rows)}</tr>`;
    if (!sOpen) return o;
    const groups = [];
    for (const z of sek.rows) { let g = groups.find(x => x.name === z.group); if (!g) groups.push(g = {name: z.group, label: gLabel(z), rows: []}); g.rows.push(z); }
    for (const g of groups) {
      const gvals = C.map(c => g.rows.reduce((a, z) => a + vOf(z, c), 0));
      const single = g.rows.length === 1 && g.rows[0].row === g.name;
      if (!S.all && gvals.every(v => Math.abs(v) < 0.005)) continue;
      const gd = d0 + 1, gid = 'g:' + name + '|' + g.name, gOpen = single || cfOpen(gid, gd);
      if (!single) o += `<tr class="sub${ind(gd)}"${exOf(name)} data-tog="${esc(gid)}" data-depth="${gd}"${zsOf(g.rows, g.label)}><td>${caret(gid, gd, gOpen)}${esc(g.label)}</td>${nums(gvals, g.rows)}</tr>`;
      if (!gOpen) continue;
      for (const z of g.rows) {
        const vals = C.map(c => vOf(z, c));
        if (!S.all && vals.every(v => Math.abs(v) < 0.005)) continue;
        const key = name + '/' + z.row, did = 'd:' + key, depth = single ? gd : gd + 1;
        const full = zLabel(z), label = single ? full : full.startsWith(g.label + ' › ') ? full.slice(g.label.length + 3) : full;
        let e = '';
        const p = z.plan || {}, ov = new Set((p.overwritten || []).filter(m => !(p.ignored || []).includes(m)));          // (a value of the position that does not count: no bar)
        if (editable) {
          // rows the plan takes from elsewhere -- the loan plan, a planned event, a property calculation: no rule of their own
          e = PLAN_FIXED[p.method] ? `<div class="edit"><span class="tag">${t(PLAN_FIXED[p.method])}</span>${ov.size ? ` <button class="small secondary reset-row" data-key="${esc(key)}" title="${t('alle_ueberschreibungen_loeschen')}">↺</button>` : ''}</div>`
            : planEdit(key, null, (D.plan.rows || {})[key] || {}, (p.overwritten || []).length);
        }
        const zu = editable || !z.lbl ? '' : z.lbl[0] === 'cf_ohne_kategorie' ? ` <a href="#categories" class="small">${t('zuordnen')}</a>`
          : z.lbl[0] === 'cf_anlage_ohne_ziel' ? ` <a href="#accounts/positions" class="small">${t('cf_ziel_festlegen')}</a>` : '';
        const det = (z.details || []).length, open = det && cfOpen(did, depth);
        const tipOf = (zz, d, c) => !c.plan && !c.mixed || !(d || zz).plan || !editable && !c.plan ? '' : c.months.length === 1 ? planWhy(D, name, zz, d, c.key) : planWhyCol(D, name, zz, d, c);
        o += `<tr class="${ind(depth).trim()}${det ? ' has-det' : ''}"${EXROW || exOf(name)} data-key="${esc(key)}"${zsOf([z], zLabel(z))}${det ? ` data-tog="${esc(did)}" data-depth="${depth}"` : ''}><td title="${esc(full)}">${det ? caret(did, depth, open) : NOCARET}${esc(label)}${zu}${editable ? planTag(D, name, z, null) : ''}${e}</td>`
          + vals.map((v, i) => {
              const c = C[i], isOv = c.plan && c.months.some(mm => ov.has(mm)), tip = editable ? tipOf(z, null, c) : '';
              const sug = (S.proposal && c.plan) ? `<div class="small muted">${F(sOf(z, c))}</div>` : '';
              return `<td class="${cls(v, c)}${editable && c.plan && !c.year ? ' editable' : ''}${isOv ? ' ov' : ''}${hasTx([z], c) ? ' tx' : ''}${tip ? ' tipped' : ''}" data-month="${c.key}"${tip ? ` data-tip="${esc(tip + (editable && c.plan && !c.year ? '\n' + t('pw_doppelklick') : ''))}"` : ''}>${FV(v)}${sug}</td>`; }).join('') + '</tr>';
        // MoneyMoney's categories inside the position: actual figures, and in plan months their plan (each by its own rule or the position's)
        if (open) for (const d of z.details) {
          const dp = d.plan || null, dov = new Set((dp && dp.overwritten) || []), dvAll = Object.assign({}, d.amounts, (dp && dp.amounts) || {});
          const dv = C.map(c => (c.plan || c.months.some(m => m > D.actual_until)) && !dp ? null : sumOver(dvAll, c.months));
          if (!S.all && dv.every(v => v == null || Math.abs(v) < 0.005)) continue;
          const cat = d.category || '', nm = d.category ? esc(CP(d.category)) : `<span class="tipped" data-tip="${esc(t('cf_geschaetzt_tip'))}" tabindex="0">${t('cf_geschaetzt')}</span>${editable ? '' : ` <a href="#categories" class="small">${t('zuordnen')}</a>`}`;
          const de = editable && dp ? planTag(D, name, z, d) + planEdit(key, cat, ((((D.plan.rows || {})[key] || {}).categories) || {})[cat] || {}, dov.size) : '';
          o += `<tr class="det${ind(depth + 1)}"${EXDET}${editable ? ` data-key="${esc(key)}" data-cat="${esc(cat)}"` : ''}${d.category && !editable ? ` data-kat="${esc(d.category)}"` : ''}><td title="${esc(CP(d.category))}">${NOCARET}${nm}${de}</td>${dv.map((v, i) => {
            const c = C[i], tip = editable && dp ? tipOf(z, d, c) : '', isOv = c.plan && c.months.some(mm => dov.has(mm)), ed = editable && dp && c.plan && !c.year;
            return `<td class="${cls(v ?? null, c)}${ed ? ' editable' : ''}${isOv ? ' ov' : ''}${tip ? ' tipped' : ''}" data-month="${c.key}"${tip ? ` data-tip="${esc(tip + (ed ? '\n' + t('pw_doppelklick') : ''))}"` : ''}>${v == null ? '' : FV(v)}</td>`; }).join('')}</tr>`;
        }
      }
    }
    return o;
  };
  // check rows: the difference to the balance sheet (bank balance, net worth); the reason is in the cell's tooltip.
  // ✓ only where every month of the column up to today was checked and adds up; a difference with a known cause is shown calmly
  // (its reason in the tooltip), one without a cause as a warning
  const ue = KF.reconciliation || {};
  const check = (help, val, why) => `<tr class="check"${EXT('check')}><td>${named(t('cf_abgleich'), help)}</td>${C.map(c => {
    const ms = c.plan ? [] : c.months.filter(m => m <= D.actual_until);
    if (!ms.length || ms.some(m => !ue[m])) return `<td class="${cls(null, c)}"></td>`;
    const v = ms.reduce((a, m) => a + ue[m][val], 0), off = ms.some(m => Math.abs(ue[m][val]) >= 0.005);
    if (!off) return `<td class="${cls(0, c)}">✓</td>`;
    const warn = ms.some(m => (ue[m][why] || []).some(g => UE_OFFEN.has(g[0])));
    // a click: the reasons and the bookings behind them, in the side panel
    return `<td class="${cls(v || 1, c)} tipped tx ${warn ? 'warn' : 'info'}" data-chk="${why}" data-tip="${esc(ueGruende(ue, ms, why))}" tabindex="0">${(v > 0.005 ? '+' : '') + F(v)}</td>`; }).join('')}</tr>`;
  // bank balance at the start and the end of a column (end of the month before / of its last month); unknown stays unknown
  const allM = [...(D.months || []), ...(D.plan_months || [])];
  // inflation-adjusted the balances would not add up (each month has its own factor): only in today's money they are left out
  const bal = (label, at) => editable && S.real ? '' : `<tr class="bal"${EXT('cash')}><td title="${esc(t('cf_bal_tip', (D.balance.positions || {}).cash || ROLE.cash[0]))}">${label}</td>${C.map(c => {
    const m = at(c), b = m ? sums[m]?.bank : undefined;
    if (b === undefined) return `<td class="${cls(null, c)}"></td>`;
    return b === null ? `<td class="${cls(null, c)} muted small">${t('unbekannt')}</td>` : `<td class="${cls(b * defl(m), c)} to-bal" data-bal="liq|${m}" title="${esc(t('cf_zur_bilanz_liq', ML(m)))}">${FC(b * defl(m))}</td>`; }).join('')}</tr>`;
  // operating: income and expenses within; then investing, financing and what could not be placed
  const opOpen = cfOpen('s:operating', 0), opZs = ['income', 'expenses'].flatMap(n => (KF.sections.find(x => x.name === n) || {rows: []}).rows);
  h += `<tr class="sec"${EXT('op')} data-tog="s:operating" data-depth="0"${zsOf(opZs, SEC_LABEL.operating)}><td>${caret('s:operating', 0, opOpen)}${dot('op')}${named(SEC_LABEL.operating, SEC_HELP.operating, SEC_ABBR.operating)}</td>${nums(secTotal('operating'), opZs)}</tr>`;
  if (opOpen) h += section('income', 1) + section('expenses', 1);
  // the check with the balance sheet per column: ✓ beside the figure; a row of its own only where something differs
  const colState = (c, val) => { const ms = c.plan || c.mixed ? [] : c.months.filter(m => m <= D.actual_until);
    if (!ms.length || ms.some(m => !ue[m])) return null; return ms.some(m => Math.abs(ue[m][val]) >= 0.005) ? 'off' : 'ok'; };
  const anyOff = val => C.some(c => colState(c, val) === 'off');
  // all adding up is the normal case: no mark; where it does not, a small "!" (the difference in the row "check against the balance sheet")
  const checked = (vals, val, zs) => vals.map((v, i) => `<td class="${cls(v, C[i])} chk${zs && hasTx(zs, C[i]) ? ' tx' : ''}">${FV(v)}${colState(C[i], val) === 'off' ? `<span class="off-mark" title="${esc(t('cf_abgleich_ab'))}">✱</span>` : ''}</td>`).join('');
  // Free Cashflow (CFO + CFI): what is left after living and investing -- or what had to be financed (from the level "positions")
  const fcf = (() => { const o = secTotal('operating'), i2 = secTotal('investing'); return o.map((v, i) => v + i2[i]); })();
  const fcfZs = [...opZs, ...(KF.sections.find(x => x.name === 'investing') || {rows: []}).rows];
  h += section('investing') + (cfLevel() >= 2 ? `<tr class="fcf"${EXT('fcf')}${zsOf(fcfZs, t('cf_fcf'))}><td>${NOCARET}${named(t('cf_fcf'), 'cf_fcf', 'FCF')}</td>${nums(fcf, fcfZs)}</tr>` : '') + section('financing') + section('unclear');
  // the change in cash -- the bank balance at the start and the end inside it (open from the level "positions")
  const bOpen = cfOpen('t:bank', 1);
  const cashZs = KF.sections.filter(x => x.name !== 'valuation').flatMap(x => x.rows);
  h += `<tr class="total"${EXT('cash')} data-tog="t:bank" data-depth="0"${zsOf(cashZs, t('zahlungsfluss_gesamt_veraenderung_liqu'))}><td>${caret('t:bank', 0, bOpen)}${named(t('zahlungsfluss_gesamt_veraenderung_liqu'), 'cf_bank')}</td>${checked(secTotal('cash_change'), 'diff_cash', cashZs)}</tr>`;
  // inside it: start + change + difference to the balance sheet = end (the difference before the end: it is added)
  if (bOpen) h += bal(t('bankguthaben_anfang'), c => allM[allM.indexOf(c.months[0]) - 1])
    + (anyOff('diff_cash') ? check('cf_abgleich_bank', 'diff_cash', 'reasons_cash') : '') + bal(t('bankguthaben_ende'), c => c.months[c.months.length - 1]);
  // from the change in cash to the change in net worth: investing, repaying and loans only move money between your accounts --
  // added back here, then the changes in value: the rows above add up to the change in net worth
  const moves = [];
  for (const sek of KF.sections) if (sek.name !== 'valuation') for (const z of sek.rows) if (!z.nw) { const l = gLabel(z); let m = moves.find(x => x.l === l); if (!m) moves.push(m = {l, zs: []}); m.zs.push(z); }
  const mv2 = moves.map(m => ({l: m.l, zs: m.zs, v: C.map(c => -m.zs.reduce((a, z) => a + vOf(z, c), 0))})).filter(m => S.all || m.v.some(v => Math.abs(v) >= 0.005));
  const h0 = h.length;          // from here on no longer the cash flow statement: from cash to net worth
  if (mv2.length) {
    const uOpen = cfOpen('t:umsch', 2), uv = C.map((_, i) => mv2.reduce((a, m) => a + m.v[i], 0));
    const uZs = mv2.flatMap(m => m.zs);
    h += `<tr class="sec umsch"${EXT('moves')} data-tog="t:umsch" data-depth="0"${zsOf(uZs, t('cf_umschichtungen'))}><td>${caret('t:umsch', 0, uOpen)}${dot('umsch')}${named(t('cf_umschichtungen'), 'cf_umsch')}</td>${nums(uv, uZs)}</tr>`;
    if (uOpen) for (const m of mv2) h += `<tr class="ind1"${EXT('moves')}${zsOf(m.zs, m.l)}><td>${NOCARET}${esc(m.l)}</td>${nums(m.v, m.zs)}</tr>`;
  }
  // what changed without a payment, and net worth
  // the change in net worth -- like the change in cash: the net worth at the start and the end inside it, the check with the balance sheet too
  const nOpen = cfOpen('t:nv', 1), nwAt = m => (D.balance.net_worth || {})[m] ?? ((D.balance.projection || {}).net_worth || {})[m];
  const nvbal = (label, at) => editable && S.real ? '' : `<tr class="bal"${EXT('nw')}><td title="${esc(t('cf_nv_bal_tip'))}">${label}</td>${C.map(c => {
    const m = at(c), b = m ? nwAt(m) : undefined; if (b == null) return `<td class="${cls(null, c)}"></td>`;
    return `<td class="${cls(b * defl(m), c)} to-bal" data-bal="nw|${m}" title="${esc(t('cf_zur_bilanz_nv', ML(m)))}">${FC(b * defl(m))}</td>`; }).join('')}</tr>`;
  const nvZs = KF.sections.flatMap(x => x.rows.filter(z => z.nw));
  h += section('valuation') + `<tr class="total"${EXT('nw')} data-tog="t:nv" data-depth="0"${zsOf(nvZs, t('cf_veraenderung_nv'))}><td>${caret('t:nv', 0, nOpen)}${named(t('cf_veraenderung_nv'), 'cf_nv')}</td>${checked(secTotal('net_worth_delta'), 'unexplained', nvZs)}</tr>`;
  if (nOpen) h += nvbal(t('cf_nv_anfang_z'), c => allM[allM.indexOf(c.months[0]) - 1])
    + (anyOff('unexplained') ? check('cf_abgleich_nv', 'unexplained', 'reasons') : '') + nvbal(t('cf_nv_ende_z'), c => c.months[c.months.length - 1]);
  h = h.slice(0, h0) + h.slice(h0).split('<tr class="').join('<tr class="nwp ');          // from cash to net worth: a little lighter, the focus on the cash flow
  h += '</tbody></table></div>';
  if (editable) h += vPlanExtras(D);
  else h += vCfCharts(D);
  return h;
}
function vPlanExtras(D) {
  const P = D.plan || {}, loans = D.loan_config || {};
  const fin = (D.cashflow.sections.find(s => s.name === 'financing') || {rows: []}).rows;
  const accName = id => (D.balance.rows.find(r => r.id === id) || {}).name;
  const loanNames = [...new Set(fin.filter(z => z.account && (z.kind === 'repayment' || z.kind === 'interest')).map(z => accName(z.account)).filter(Boolean))];
  let h = `<h2>${t('darlehensplan')}</h2><div class="note">${t('zins_auf_den_fortgeschriebenen_restsal')}</div><div class="wrap auto" data-ex="planning.loans"><table class="plain"><thead><tr><th>${t('darlehen')}</th><th>${t('zins_p_a')}</th><th>${t('modell')}</th><th>${t('zahlung_je_monat_leer_durchschnitt')}</th><th></th></tr></thead><tbody>`;
  for (const name of loanNames) {
    const d = (P.loans || {})[name] || {}; const cfgLoan = Object.values(loans).find(l => l.name === name);
    // the model as it is calculated: set here, else the booking rule's -- a click on ✓ (to change the payment) keeps it
    const MODEL = {remaining_debt_monthly: t('restschuld_monatlich'), yearly_base: t('jahresbasis_31_12')}, md = d.model || (cfgLoan || {}).model || 'remaining_debt_monthly';
    h += `<tr data-loan="${esc(name)}"><td>${esc(name)}${cfgLoan ? `<span class="tag">${t('regel')} ` + esc(MODEL[cfgLoan.model] || cfgLoan.model || '') + '</span>' : ''}</td><td class="num"><input type="number" step="0.01" class="lz" value="${d.interest_percent_pa ?? ''}" style="width:90px"></td><td><select class="lm">${Object.entries(MODEL).map(([k, l]) => `<option value="${k}" ${md === k ? 'selected' : ''}>${l}</option>`).join('')}</select></td><td class="num"><input type="number" step="0.01" class="lp" value="${d.payment ?? ''}" style="width:110px"></td><td><button class="small save-loan">✓</button></td></tr>`;
  }
  if (!loanNames.length) h += `<tr><td colspan="5" class="muted">${t('keine_darlehenszeilen_im_kapitalfluss')}</td></tr>`;
  h += '</tbody></table></div>';
  const leafs = D.balance.rows.filter(r => !r.group && r.role !== 'cash');
  const others = Object.entries((S.DATA && S.DATA.area_names) || {}).filter(([k]) => k !== S.area);
  h += `<h2>${t('wertentwicklung_je_konto_0', hq('rendite'))}</h2><div class="note">${t('jaehrliche_wertaenderung_in_prozent_ba', hq('wert_bereich'))}</div><div class="wrap auto" data-ex="planning.appreciation"><table class="plain"><thead><tr><th>${t('konto_2')}</th><th>${t('position')}</th><th>% p.a.</th><th>${t('basis_optional')}</th><th>${t('kopplung_an_bereich')}</th><th>${t('anteil')}</th><th></th></tr></thead><tbody>`;
  for (const r of leafs) {
    const w = (P.appreciation || {})[r.name] || {};
    h += `<tr data-acct="${esc(r.name)}"><td>${esc(r.path)}${r.inactive ? `<span class="tag">${t('ausgeblendet')}</span>` : ''}</td><td class="small">${(ROLE[r.role] || [r.role])[0]}</td><td class="num"><input type="number" step="0.1" class="wp" value="${w.percent_pa ?? ''}" style="width:80px"></td><td class="num"><input type="number" step="1" class="wb" value="${w.base ?? ''}" style="width:130px"></td><td><select class="wbr"><option value="">–</option>${others.map(([k, n]) => `<option value="${esc(k)}" ${w.area === k ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></td><td class="num"><input type="number" step="0.01" min="0" max="1" class="wa" value="${w.share ?? ''}" placeholder="1" style="width:70px"></td><td><button class="small save-wert">✓</button></td></tr>`;
  }
  h += '</tbody></table></div>';
  // Ereignisse
  const evs = P.events || [];
  const konten = D.balance.rows.filter(r => !r.group);
  const kOpt = sel => `<option value="">${t('liquiditaet_bereich')}</option>` + konten.map(k => `<option value="${k.id} | ${esc(k.name)}" ${sel && sel.split('|')[0].trim() === k.id ? 'selected' : ''}>${esc(k.name)}${k.role ? ' · ' + (ROLE[k.role] || [k.role])[0] : ''}</option>`).join('');
  const WH = {once: t('einmalig'), monthly: t('monatlich'), quarterly: t('je_quartal'), yearly: t('jaehrlich')};
  const nextM = (() => { const d = new Date(); d.setMonth(d.getMonth() + 1); return d.toISOString().slice(0, 7); })();
  const evRow = (e, isNew) => `<div class="ev-row item" data-id="${esc(e.id || '')}"><div class="grow">
    <div class="row tight"><input type="text" class="ev-text" value="${esc(e.text || '')}" placeholder="${t('bezeichnung_z_b_rueckzahlung_unternehm')}" style="width:260px">
      <select class="ev-art">${[['reallocation', t('umschichtung')], ['expense', t('ausgabe')], ['income', t('einnahme')]].map(([v, l]) => `<option value="${v}" ${(e.kind || 'reallocation') === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <label class="chk small">${t('betrag')} <input type="number" step="0.01" class="ev-betrag" value="${e.amount ?? ''}" style="width:120px"></label>
      <label class="chk small">${t('monat_2')} <input type="month" class="ev-monat" value="${esc(e.month || (isNew ? nextM : ''))}"></label>
      <select class="ev-wdh">${Object.entries(WH).map(([v, l]) => `<option value="${v}" ${(e.recurrence || 'once') === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <label class="chk small">${t('bis')} <input type="month" class="ev-bis" value="${esc(e.date_to || '')}" title="${t('enddatum_bei_wiederholung_leer_horizon')}"></label></div>
    <div class="row tight"><label class="chk small">${t('von')} <select class="ev-von">${kOpt(e.date_from)}</select></label><span class="muted">→</span><label class="chk small">${t('nach')} <select class="ev-nach">${kOpt(e.after)}</select></label>
      <label class="chk small"><input type="checkbox" class="ev-aktiv" ${e.active !== false ? 'checked' : ''}> ${t('aktiv')}</label>
      <button class="small ev-save">${e.id ? t('speichern') : t('hinzufuegen')}</button>${e.id ? `<button class="small danger ev-del">${t('loeschen')}</button>` : ''}</div></div></div>`;
  h += `<h2>${t('geplante_ereignisse_0', hq('event'))}</h2><div class="note">${t('umschichtung_betrag_geht_von_von')}</div><div class="list" data-ex="planning.events">`;
  for (const e of evs) h += evRow(e, false);
  h += evRow({}, true) + '</div>';
  return h;
}

// ---------------------------------------------------------------- Cashflow: Diagramme
// One period for all of them (the row above): the last 12 months, a calendar year, or everything; actual figures of closed
// months only -- the running month is half booked and would look cheap next to whole ones (it counts from the 1st of the next
// month at midnight, as in the balance sheet; the table shows it hatched). Colour stands for the activity (operating,
// investing, financing) as at the table's sections; the table holds every figure.
const CF = {ro: null, tips: []};
const cfDone = D => (D.months || []).filter(m => m < D.actual_until);
// what can be chosen: the closed months, the running one and (with the plan on) the plan months -- the last two hatched in the charts
const cfPick = D => [...new Set([...(D.months || []), ...(planOn() ? D.plan_months || [] : [])])].sort();
const cfIsOpen = (D, m) => m >= D.actual_until;
// the presets: the last 12 months, the running year (so far) and the two before
function cfPeriods(D) {
  const y0 = +String(D.actual_until || '').slice(0, 4), done = cfDone(D);
  return [['12m', t('cf_12_monate')], ...[y0, y0 - 1, y0 - 2].map(String).filter(y => done.some(m => m.startsWith(y))).map(y => [y, y])];
}
const mShift = (m, n) => { const k = +m.slice(0, 4) * 12 + +m.slice(5) - 1 + n; return `${Math.floor(k / 12)}-${String(k % 12 + 1).padStart(2, '0')}`; };
// the months of the period -- the last 12, a calendar year or a range of your own (von/bis) -- and those to compare with: the
// same months a year earlier (a period longer than a year: whole years further back, so it does not overlap and the seasons match)
function cfMonths(D, key) {
  const ms = cfDone(D), all = cfPick(D);
  let cur = /^\d{4}$/.test(key) ? ms.filter(m => m.startsWith(key)) : key === 'custom' && S.cfVon && S.cfBis ? all.filter(m => m >= S.cfVon && m <= S.cfBis) : ms.slice(-12);
  if (!cur.length || (key === 'custom' && S.cfBis && !all.includes(S.cfBis))) { cur = ms.slice(-12); if (key === 'custom') S.cfZeit = '12m'; }
  const back = Math.max(1, Math.ceil(cur.length / 12)) * 12, prev = cur.map(m => mShift(m, -back)).filter(m => all.includes(m));
  return [cur, prev.length === cur.length ? prev : []];
}
const cfSum = (D, name, months) => months.reduce((a, m) => a + ((D.cashflow.sums || {})[m]?.[name] ?? 0), 0);
// a row's values: actual figures, for plan months the plan (as in the table)
const cfVals = z => { const w = CF.vals || (CF.vals = new WeakMap()); let v = w.get(z); if (!v) w.set(z, v = Object.assign({}, z.amounts, (z.plan && z.plan.amounts) || {})); return v; };
const cfRowSum = (z, months) => { const v = cfVals(z); return months.reduce((a, m) => a + (v[m] ?? 0), 0); };
// a row's categories (in plan months their plan); where a row's plan is not by its categories (a property calculation) it stands
// as a part of its own ("as planned") -- the parts add up
const cfDet = z => { const w = CF.dets || (CF.dets = new WeakMap()); let r = w.get(z); if (r) return r;
  const ds = z.details || [], pv = (z.plan && z.plan.amounts) || {}, rest = {};
  for (const m of Object.keys(pv)) { const x = (cfVals(z)[m] ?? 0) - ds.reduce((a, d) => a + (cfVals(d)[m] ?? 0), 0); if (Math.abs(x) >= 0.005) rest[m] = x; }
  r = Object.keys(rest).length && ds.length ? [...ds, {category: null, rest: true, amounts: rest}] : ds; w.set(z, r); return r; };
const cfDetName = d => d.rest ? t('cf_laut_plan') : d.category ? d.category.split(' / ').slice(-2).join(' › ') : t('cf_geschaetzt');
const cfPct = (part, whole) => whole ? Math.round(part / whole * 100) : null;
// change against the period before as a short text ("+12 %"), and whether that is good
function cfChange(cur, prev, upGood) {
  if (prev == null || Math.abs(prev) < 0.005) return null;
  const d = (cur - prev) / Math.abs(prev) * 100;
  if (Math.abs(d) >= 100000) return null;                     // from almost nothing: says nothing
  if (Math.abs(cur - prev) < 0.5) return {txt: '±0 %', cls: '', d: 0};      // only the same amount is unchanged; a small change keeps its sign
  const a = Math.abs(d), txt = a >= 999.5 ? (a / 1000).toLocaleString(LOCALE, {maximumFractionDigits: a >= 10000 ? 0 : 1}) + t('tsd_kurz')      // short, as in the balance sheet: +10T %
    : a < 0.01 ? '<' + (0.01).toLocaleString(LOCALE) : a.toLocaleString(LOCALE, {maximumFractionDigits: a < 0.1 ? 2 : a < 10 ? 1 : 0});
  return {txt: (d > 0 ? '+' : '−') + txt + ' %', cls: (d > 0) === upGood ? 'pos' : 'neg', d};
}
// the change in a narrow column (the bridges): from 1000 % on only the rounded thousands ("+2T%"), else as above without the space
const cfChgShort = ch => Math.abs(ch.d || 0) >= 999.5 ? (ch.d > 0 ? '+' : '−') + Math.round(Math.abs(ch.d) / 1000).toLocaleString(LOCALE) + t('tsd_kurz') + '%' : ch.txt.replace(' %', '%');
// the change of a signed amount (money in +, out −): of its size while the sign stays (expenses +10 %: more was spent), across
// zero of the amount itself; colour (better / worse for you) only where that is beyond doubt -- income and expenses (colour)
function cfChangeAmt(cur, prev, colour) {
  if (prev == null) return null;
  const c = cur * prev < 0 ? cfChange(cur, prev, true) : prev < 0 || (prev === 0 && cur < 0) ? cfChange(Math.abs(cur), Math.abs(prev), false) : cfChange(cur, prev, true);
  return c && !colour ? {...c, cls: ''} : c;
}
// the period before of a group of positions or categories ("Übrige"): only where each of them had one -- a sum with gaps would
// compare something else than it shows
const cfRestP = (list, has) => has && list.length && list.every(d => d.p != null && Math.abs(d.p) >= 0.5) ? list.reduce((a, d) => a + d.p, 0) : null;
// the groups of investing and financing in the period (their kinds: real estate, securities, loans taken up, repayment …)
function cfGroups(D, sec, months) {
  const sek = D.cashflow.sections.find(s => s.name === sec) || {rows: []}, out = [];
  for (const z of sek.rows) { let g = out.find(x => x.name === z.group); if (!g) out.push(g = {name: z.group, label: gLabel(z), v: 0, rows: []}); g.v += cfRowSum(z, months); g.rows.push(z); }
  return out.filter(g => Math.abs(g.v) >= 0.5);
}
// the order of the charts: chosen with ↑ ↓ (kept in this browser), the default the most important first
const CF_ORDER_KEY = 'kontor.cfOrder', CF_ORDER_DEF = ['bridge', 'months', 'wealth', 'flow', 'duo'];          // cash: bridge and months; below: net worth bridge and the total -- like ones above each other
function cfOrder() {
  let o = null; try { o = JSON.parse(LS.get(CF_ORDER_KEY) || 'null'); } catch (e) { o = null; }
  const avail = CF.avail || CF_ORDER_DEF;
  o = (Array.isArray(o) ? o : CF_ORDER_DEF).filter(id => avail.includes(id));
  return [...o, ...avail.filter(id => !o.includes(id))];
}
const cfOrderOwn = () => { try { return !!LS.get(CF_ORDER_KEY); } catch (e) { return false; } };
const cfMv = id => { const o = cfOrder(), k = o.indexOf(id);
  return `<span class="cf-mv"><button class="th-mv" data-cfmv="${id}" data-d="-1" title="${esc(t('cf_grafik_hoch'))}" aria-label="${esc(t('cf_grafik_hoch'))}"${k <= 0 ? ' disabled' : ''}>↑</button><button class="th-mv" data-cfmv="${id}" data-d="1" title="${esc(t('cf_grafik_runter'))}" aria-label="${esc(t('cf_grafik_runter'))}"${k >= o.length - 1 ? ' disabled' : ''}>↓</button></span>`; };
function vCfCharts(D) {
  const ist = cfDone(D);
  if (ist.length < 2) return '';
  const per = cfPeriods(D); if (S.cfZeit !== 'custom' && !per.some(p => p[0] === S.cfZeit)) S.cfZeit = '12m';
  const [cur] = cfMonths(D, S.cfZeit);
  if (!cur.length) return '';
  const pick = cfPick(D), mb = (id, v, lab) => `<button class="cf-mbtn${cfIsOpen(D, v) ? ' open' : ''}" id="${id}" data-m="${v}" aria-haspopup="dialog" aria-label="${esc(lab + ': ' + MLL(v))}">${esc(ML(v))}</button>`;
  let h = `<div class="cf-charts" data-ex="cashflow.charts"><div class="toolbar cf-period"><span class="cf-range"><button class="cf-shift icon" data-shift="-1" title="${esc(t('cf_monat_zurueck'))}" aria-label="${esc(t('cf_monat_zurueck'))}" ${pick.indexOf(cur[0]) <= 0 ? 'disabled' : ''}>‹</button>`
    + `<span class="cf-range-in" title="${esc(t('cf_zeitraum_tip'))}">${mb('cf-von', cur[0], t('cf_von'))}<span class="muted">–</span>${mb('cf-bis', cur[cur.length - 1], t('cf_bis'))}</span>`
    + `<button class="cf-shift icon" data-shift="1" title="${esc(t('cf_monat_vor'))}" aria-label="${esc(t('cf_monat_vor'))}" ${pick.indexOf(cur[cur.length - 1]) >= pick.length - 1 ? 'disabled' : ''}>›</button></span>`
    + `<div class="seg small" id="cf-zeit">${per.map(([k, l]) => `<button data-z="${k}" class="${S.cfZeit === k ? 'on' : ''}">${l}</button>`).join('')}</div>`
    + (cfOrderOwn() ? `<span class="view-btns"><button class="small secondary" id="cf-order-reset" title="${esc(t('cf_ansicht_reset_tip'))}">${ICON.reset}<span class="lbl">${t('ansicht_reset')}</span></button></span>` : '') + `</div>`;
  if (!['income', 'expenses', 'investing', 'financing', 'unclear'].some(n => cur.some(m => Math.abs((D.cashflow.sums || {})[m]?.[n] ?? 0) >= 0.005)))
    return h + `<div class="card cf-empty muted small">${t('cf_keine_zahlungen')}</div></div>`;          // nothing to draw
  CF.tips = [];
  // two rows of a three-column grid: the wide charts beside a narrow one (the bridge beside the expenses, the months beside sources
  // and uses); a narrow window stacks them
  const prev = cfMonths(D, S.cfZeit)[1];
  const su = cfSourcesUses(D, cur, prev);
  const card = (id, cls, key, extra, plot, ex) => `<div class="card bch cf-card ${cls}" data-cfid="${id}" ${ex}><div class="lc-head"><b class="lc-title">${t(key)}${hq(key)}</b>${cfMv(id)}${extra || ''}</div><div class="cf-plot" id="${plot}"></div></div>`;
  // the charts in the order you chose (↑ ↓ at each, on hover): two half ones side by side; a half one without a half neighbour
  // takes the whole width
  const pie = cfPie(D, cur, prev), hasW = cfWealthTree(D, cur, prev).some(r => r.kind !== 'tot');
  CF.avail = ['bridge', 'months', ...(su ? ['flow'] : []), ...(hasW ? ['wealth'] : []), 'duo'];
  const parts = {
    bridge: cls => card('bridge', cls, 'cf_bruecke', `<button id="cf-br-reset" class="small secondary hidden">${t('cf_br_ganz')}</button>`, 'cf-bridge', 'data-ex="cashflow.bridge"'),
    months: cls => card('months', cls, 'cf_je_monat_t', '', 'cf-months', 'data-ex="cashflow.months"'),          // no legend: the colours are the table's, the tooltip names them
    flow: cls => su.replace('__CLS__', cls),
    wealth: cls => card('wealth', cls, 'cf_verm_bruecke', `<button id="cf-wb-reset" class="small secondary hidden">${t('cf_br_ganz')}</button>`, 'cf-wbridge', 'data-ex="cashflow.wealth"'),
    duo: () => `<div class="card bch cf-card cf-full cf-duo${pie ? '' : ' solo'}" data-cfid="duo">${pie}${cfHeatCard(!pie)}</div>`,
  };
  const order = cfOrder(), half = id => id !== 'duo';
  let grid = '';
  for (let i = 0; i < order.length; i++) {
    const id = order[i];
    if (half(id) && half(order[i + 1] || 'duo')) { grid += parts[id]('cf-half') + parts[order[i + 1]]('cf-half'); i++; }
    else grid += parts[id](half(id) ? 'cf-full' : '');
  }
  h += `<div class="cf-grid">${grid}</div><div class="cf-tip hidden" id="cf-tip" role="tooltip"></div></div>`;
  return h;
}
// a tooltip with colour keys (the plain one shows text only): its HTML is built here, every name escaped
const cfTipRow = (key, name, val, extra) => `<div><i class="${key}"></i><span>${esc(name)}</span><b>${val}</b>${extra ? `<em class="${extra.cls}">${extra.txt}</em>` : ''}</div>`;
const cfTipTot = (name, val) => `<div class="tot"><i class="eq">=</i><span>${esc(name)}</span><b>${val}</b></div>`;          // a sum of the rows above: = instead of a colour, bold
function cfTip(html) { CF.tips.push(html); return CF.tips.length - 1; }

// 1. Bridge: from the cash at the start to the cash at the end -- income, expenses, each kind of investing and financing
const cfMonthBefore = (D, m) => { const all = [...new Set([...(D.months || []), ...(D.plan_months || [])])].sort(); return all[all.indexOf(m) - 1] || mShift(m, -1); };
// from a figure in the cash flow to the balance sheet: its month in view, the cell lights up (cash: the position of cash; net
// worth: its total row)
// the period of the charts: from–to, the preset lit when it matches (the last 12 closed months, a year so far)
function cfSetRange(v, b) {
  const D = B(), ms = cfDone(D), sel = cfPick(D).filter(m => m >= v && m <= b), y = v.slice(0, 4);
  S.cfVon = v; S.cfBis = b; S.cfBrZoom = S.cfWbZoom = null;
  S.cfZeit = sel.join() === ms.slice(-12).join() ? '12m' : sel.join() === ms.filter(m => m.startsWith(y)).join() && b.startsWith(y) && cfPeriods(D).some(p => p[0] === y) ? y : 'custom';
  CF.pieSel = null; return Promise.resolve(route()).then(() => cfTableShow(b));
}
// the table follows: the last month of the period in view (moved only when it is not)
function cfTableShow(m) {
  const w = $('#main .wrap'), th = w && ($(`thead th[data-key="${m}"]`, w) || $(`thead th[data-key="${m.slice(0, 4)}"]`, w)); if (!th) return;          // years: its year
  const sw = $('thead th', w).offsetWidth, x = colX(w, th);
  if (x < w.scrollLeft + sw || x + th.offsetWidth > w.scrollLeft + w.clientWidth) w.scrollTo({left: snapLeft(w, x + th.offsetWidth - w.clientWidth), behavior: 'smooth'});
}
const cfSpanLabel = ms => ms.length > 1 ? ML(ms[0]) + ' – ' + ML(ms[ms.length - 1]) : ML(ms[0]);
function cfToBalance(bal) { S.balFlash = bal; go('#balance'); }
function balFlash(main, tries = 0) {
  const f = S.balFlash; if (!f) return; const [kind, m] = f.split('|'), w = $('.wrap.snap', main); if (!w) { S.balFlash = null; return; }
  const th = $(`th[data-key="${m}"]`, w) || (S.mode === 'years' ? $(`th[data-key="${m.slice(0, 4)}"]`, w) : null);
  // a month before the table's first year (e.g. the start of an earlier year): show from its year on -- the new page runs this again
  // a plan month while the plan is hidden: shown -- the new page runs this again
  if (!th) { const D = B(); if (D && S.mode !== 'years' && +m.slice(0, 4) < firstYear(D)) { S.vonJahr = +m.slice(0, 4); route(); }
    else if (D && !S.plan && (D.plan_months || []).includes(m)) { S.plan = true; route(); } else S.balFlash = null; return; }
  S.balFlash = null; bchJump(m);
  const idx = [...th.parentNode.children].indexOf(th);
  const tr = kind === 'nw' ? [...$$('tr.total', w)].find(r => r.querySelector('.nw-sw')) : $('tr[data-pos="cash"]', w);
  const c = tr && tr.children[idx]; if (!c) return;
  c.classList.remove('flash-hit'); void c.offsetWidth; c.classList.add('flash-hit');
  // up or down only (scrollIntoView would also move the table sideways -- back to the row's start, away from the month)
  const sc = scrollParentY(w);
  const top = sc === document.scrollingElement ? 0 : sc.getBoundingClientRect().top, vh = sc === document.scrollingElement ? innerHeight : sc.clientHeight;
  sc.scrollBy({top: tr.getBoundingClientRect().top - top - vh / 2, behavior: 'smooth'});
  // then as a click on the cell: once the table stands still, the charts line up with the month (the bank: its area lights up too)
  scrollSettled(w, () => { if (!c.isConnected) return; bchFocus(th.dataset.key, kind === 'nw'); if (kind !== 'nw') bchFlash(tr, c); });
}
// the page scrolls in the window -- or, with the assistant's panel docked beside it, in itself (its scroll bar at its own edge)
const pageDocked = () => document.body.classList.contains('as-open') && matchMedia('(min-width:1280px)').matches;
const pageScroller = () => pageDocked() ? $('main') : document.scrollingElement;
const pageY = () => pageScroller().scrollTop;
const pageTo = y => { pageScroller().scrollTop = Math.max(0, y); };
const pageBy = d => { pageScroller().scrollTop += d; };
const pageTop = () => { const sc = pageScroller(); return sc === document.scrollingElement ? 0 : sc.getBoundingClientRect().top; };
// the panel docks or goes (or the window crosses the width where it docks): the page stays where it was, now scrolled the other
// way. The position is kept while it scrolls -- once the other one scrolls, the first has lost it (its height is gone)
let PAGE_DOCKED = false, PAGE_Y = 0;
const pageKeep = () => { if (pageDocked() === PAGE_DOCKED) PAGE_Y = pageY(); };
function pageHandover() {
  const now = pageDocked(); if (now === PAGE_DOCKED) return;
  const m = $('main'), doc = document.scrollingElement;
  if (now) { doc.scrollTop = 0; m.scrollTop = PAGE_Y; } else doc.scrollTop = PAGE_Y;
  PAGE_DOCKED = now;
}
window.addEventListener('scroll', pageKeep, {passive: true}); $('main').addEventListener('scroll', pageKeep, {passive: true});
matchMedia('(min-width:1280px)').addEventListener('change', pageHandover);
// what a ResizeObserver does, in the next frame and once per frame: a chart redrawn inside the observer changes sizes again in the
// same frame, and the browser reports a loop (e.g. while the assistant's panel slides in beside the page)
const onResizeFrame = fn => { let raf = 0; return () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; fn(); }); }; };
function scrollParentY(el) {
  for (let p = el.parentElement; p; p = p.parentElement) { const o = getComputedStyle(p).overflowY; if ((o === 'auto' || o === 'scroll') && p.scrollHeight > p.clientHeight) return p; }
  return document.scrollingElement;
}
// redraw without the page jumping: the element (found again afterwards by its selector) stays where it was on the screen
function keepPlace(el, sel, fn) {
  const sc = scrollParentY(el), y0 = el.getBoundingClientRect().top; fn();
  const now = $(sel()); if (now) sc.scrollTop += now.getBoundingClientRect().top - y0;
}
function scrollSettled(el, fn) {
  let last = null, same = 0; const t0 = performance.now();
  const step = () => { const v = el.scrollLeft; same = v === last ? same + 1 : 0; last = v;
    if (same >= 4 || performance.now() - t0 > 1500) fn(); else requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
function cfBridgeSteps(D, months, prev) {
  const sums = D.cashflow.sums || {}, allM = [...new Set([...(D.months || []), ...(D.plan_months || [])])].sort();
  const before = allM[allM.indexOf(months[0]) - 1], last = months[months.length - 1];
  const start = before ? sums[before]?.bank : null, end = sums[last]?.bank;
  const known = start != null && end != null;
  const steps = [];
  if (known) steps.push({label: t('bankguthaben_anfang'), v: start, total: true});
  const pv = (sec, g) => prev.length ? (g ? (cfGroups(D, sec, prev).find(x => x.name === g) || {v: 0}).v : cfSum(D, sec, prev)) : null;
  steps.push({label: t('einnahmen'), v: cfSum(D, 'income', months), act: 'op', p: pv('income')});
  steps.push({label: t('ausgaben'), v: cfSum(D, 'expenses', months), act: 'op', p: pv('expenses')});
  for (const [sec, act] of [['investing', 'inv'], ['financing', 'fin']])
    for (const g of cfGroups(D, sec, months)) steps.push({label: g.label, v: g.v, act, p: pv(sec, g.name)});
  const unk = cfSum(D, 'unclear', months); if (Math.abs(unk) >= 0.5) steps.push({label: t('cf_unklar'), v: unk, act: 'unk'});
  // what the balance sheet shows beyond the payments (left out on purpose, money in transit, corrections): its own step
  const off = known ? end - start - steps.reduce((a, s) => a + (s.total ? 0 : s.v), 0) : 0;
  if (Math.abs(off) >= 0.5) steps.push({label: t('cf_abgleich'), v: off, act: 'unk'});
  steps.push(known ? {label: t('bankguthaben_ende'), v: end, total: true} : {label: t('zahlungsfluss_gesamt_veraenderung_liqu'), v: cfSum(D, 'cash_change', months), total: true});
  let lvl = 0;
  for (const s of steps) { if (s.total) { s.a = 0; s.b = s.v; lvl = s.v; } else { s.a = lvl; s.b = lvl + s.v; lvl = s.b; } }
  return steps;
}
// the bridge as a tree: each activity, its steps (income, expenses; the kinds of investing and financing), their positions, their
// categories. An open node is drawn as a bracket over its parts -- they make it up --, a closed one (or a leaf) is a step of the
// waterfall. Opened at first: the activities; a click opens or closes any row with parts.
function cfBridgeTree(D, months, prev) {
  const steps = cfBridgeSteps(D, months, prev), has = prev.length > 0;
  const sek = name => D.cashflow.sections.find(s => s.name === name) || {rows: []};
  const sum = (list, f) => list.reduce((a, x) => a + f(x), 0);
  const pOf = list => has && list.every(x => x.p != null) ? sum(list, x => x.p) : null;
  const limit = (id, kids) => {          // at most eight parts: the smaller ones together as "the others"
    kids = kids.filter(k => Math.abs(k.v) >= 0.5).sort((a, b) => Math.abs(b.v) - Math.abs(a.v));
    if (kids.length <= 8) return kids;
    const rest = kids.slice(7);
    return kids.slice(0, 7).concat([{id: id + '|~', label: t('cf_uebrige', rest.length), v: sum(rest, k => k.v), p: cfRestP(rest, has), kids: null}]);
  };
  const cats = (id, zs) => { const m = new Map();
    for (const z of zs) for (const d of cfDet(z)) { const k = d.rest ? '~plan' : d.category || '~', c = m.get(k) || {id: id + '|' + k, label: cfDetName(d), v: 0, p: has ? 0 : null, kids: null};
      c.v += cfRowSum(d, months); if (has) c.p += cfRowSum(d, prev); m.set(k, c); }
    return limit(id, [...m.values()]); };
  const rows = (id, zs) => { const m = new Map();
    for (const z of zs) { const k = zLabel(z), r = m.get(k) || {id: id + '|' + k, label: k, v: 0, p: has ? 0 : null, zs: []}; r.v += cfRowSum(z, months); if (has) r.p += cfRowSum(z, prev); r.zs.push(z); m.set(k, r); }
    return limit(id, [...m.values()].map(r => { const c = cats(r.id, r.zs); return {...r, kids: c.length > 1 || (c.length === 1 && c[0].label !== r.label) ? c : null}; })); };
  const stepNode = s => {
    const id = s.act + '|' + s.label;
    let zs = [];
    if (s.act === 'op') zs = sek(s.label === t('einnahmen') ? 'income' : 'expenses').rows;
    else if (s.act === 'inv' || s.act === 'fin') { const g = cfGroups(D, s.act === 'inv' ? 'investing' : 'financing', months).find(x => x.label === s.label); zs = g ? g.rows : []; }
    const k = rows(id, zs);
    return {id, label: s.label, v: s.v, p: s.p ?? null, kids: k.length > 1 || (k.length === 1 && k[0].label !== s.label) ? k : null};
  };
  const ACT = {op: 'operating', inv: 'investing', fin: 'financing'}, out = [];
  for (const s of steps) {
    if (s.total) { const first = s === steps[0] && steps.length > 1, pl = !first && (D.plan_months || []).includes(months[months.length - 1]);
      out.push({id: s.label, kind: 'tot', bal: s.label === t('bankguthaben_anfang') ? 'liq|' + cfMonthBefore(D, months[0]) : s.label === t('bankguthaben_ende') ? 'liq|' + months[months.length - 1] : null, label: (s.label === t('bankguthaben_anfang') ? t('cf_anfangsbestand') : s.label === t('bankguthaben_ende') ? t('cf_endbestand') : s.label) + (pl ? ' ' + t('cf_plan_klammer') : ''), full: s.label, v: s.v, first }); continue; }
    if (!ACT[s.act]) { out.push({id: s.label, kind: 'one', label: s.label === t('cf_abgleich') ? t('cf_abgleich_kurz') : s.label, full: s.label, v: s.v, p: null, kids: null}); continue; }
    let g = out.find(r => r.act === s.act);
    if (!g) out.push(g = {id: s.act, kind: 'act', act: s.act, label: SEC_LABEL[ACT[s.act]], abbr: SEC_ABBR[ACT[s.act]], v: 0, kids: []});
    g.kids.push(stepNode(s));
  }
  for (const g of out) if (g.kind === 'act') { g.v = sum(g.kids, k => k.v); g.p = pOf(g.kids); }
  return out;
}
// 6. Net worth bridge: from the net worth at the start to that at the end -- what was saved (income, expenses, interest), what came
// in or went out between you and others (contributions, withdrawals), the changes in value per account. Only the rows that change
// net worth: investing or repaying a loan moves money from one account to another and is left out.
// what a row of the cash flow does to net worth: saved (income, expenses, interest), between you and others (contributions,
// withdrawals, money moved out of what Kontor sees), a change in value, unclear -- or nothing (investing, repaying: null)
const cfNwKind = (sec, z) => !z.nw ? null : sec === 'valuation' ? 'value' : z.kind === 'interest' ? 'spar' : sec === 'income' || sec === 'expenses' ? 'spar' : sec === 'unclear' ? 'unk' : 'ext';
function cfWealthTree(D, months, prev) {
  const has = prev.length > 0, bil = D.balance || {}, allM = cfPick(D), nwAt = m => (bil.net_worth || {})[m] ?? ((bil.projection || {}).net_worth || {})[m];
  const before = allM[allM.indexOf(months[0]) - 1] || (D.months || [])[(D.months || []).indexOf(months[0]) - 1], last = months[months.length - 1];
  const start = before ? nwAt(before) : null, end = nwAt(last), known = start != null && end != null;
  const sum = (list, f) => list.reduce((a, x) => a + f(x), 0);
  const limit = (id, kids) => {          // at most eight parts: the smaller ones together as "the others"
    kids = kids.filter(k => Math.abs(k.v) >= 0.5).sort((a, b) => Math.abs(b.v) - Math.abs(a.v));
    if (kids.length <= 8) return kids;
    const rest = kids.slice(7);
    return kids.slice(0, 7).concat([{id: id + '|~', label: t('cf_uebrige', rest.length), v: sum(rest, k => k.v), p: cfRestP(rest, has), kids: null}]);
  };
  const cats = (id, zs) => { const m = new Map();
    for (const z of zs) for (const d of cfDet(z)) { const k = d.rest ? '~plan' : d.category || '~', c = m.get(k) || {id: id + '|' + k, label: cfDetName(d), v: 0, p: has ? 0 : null, kids: null};
      c.v += cfRowSum(d, months); if (has) c.p += cfRowSum(d, prev); m.set(k, c); }
    return limit(id, [...m.values()]); };
  const node = (id, label, zs, by) => {          // a step and its parts: rows grouped by their name (or by the account, for values)
    const m = new Map();
    for (const z of zs) { const k = by(z), r = m.get(k) || {id: id + '|' + k, label: k, v: 0, p: has ? 0 : null, zs: []}; r.v += cfRowSum(z, months); if (has) r.p += cfRowSum(z, prev); r.zs.push(z); m.set(k, r); }
    const kids = limit(id, [...m.values()].map(r => { const c = cats(r.id, r.zs), more = r.zs.length > 1 ? limit(r.id, r.zs.map(z => ({id: r.id + '|' + z.row, label: zLabel(z), v: cfRowSum(z, months), p: has ? cfRowSum(z, prev) : null, kids: null}))) : [];
      const k = c.length ? c : more; return {...r, kids: k.length > 1 || (k.length === 1 && k[0].label !== r.label) ? k : null}; }));
    return {id, label, v: sum(zs, z => cfRowSum(z, months)), p: has ? sum(zs, z => cfRowSum(z, prev)) : null, kids: kids.length > 1 || (kids.length === 1 && kids[0].label !== label) ? kids : null};
  };
  const by = {ein: [], aus: [], interest: [], ext: [], value: [], unk: []};
  for (const sek of D.cashflow.sections) for (const z of sek.rows) { const k = cfNwKind(sek.name, z); if (k) by[k === 'spar' ? (z.kind === 'interest' ? 'interest' : sek.name === 'income' ? 'ein' : 'aus') : k].push(z); }
  // plan months: what the plan expects the assets to gain or lose beyond these rows (the table's changes in value hold it too)
  const sums = D.cashflow.sums || {}, wz = (D.cashflow.sections.find(x => x.name === 'valuation') || {rows: []}).rows, planW = {};
  for (const m of [...months, ...prev]) if ((D.plan_months || []).includes(m)) { const x = (sums[m]?.valuation ?? 0) - wz.reduce((a, z) => a + (cfVals(z)[m] ?? 0), 0); if (Math.abs(x) >= 0.005) planW[m] = x; }
  if (Object.keys(planW).length) by.value.push({row: t('cf_wert_plan'), group: t('cf_wert_plan'), kind: 'plan', nw: true, amounts: planW, details: []});
  // a group's amount and its year before from all its rows (parts under 50 cents are not shown, but count)
  const out = [], grp = (act, label, zs, kids, id = act) => { const v = sum(zs, z => cfRowSum(z, months)); if (Math.abs(v) < 0.005 && !kids.length) return;
    out.push({id, kind: 'act', act, label, v, p: has ? sum(zs, z => cfRowSum(z, prev)) : null, kids: kids.filter(k => Math.abs(k.v) >= 0.5)}); };
  if (known) out.push({id: 'nw0', kind: 'tot', bal: 'nw|' + before, label: t('cf_nv_anfang'), v: start});
  // as in the table: the surplus (income and expenses), then the interest (financing, but it costs net worth -- repaying does not)
  grp('op', SEC_LABEL.operating, [...by.ein, ...by.aus], [node('op|ein', t('einnahmen'), by.ein, zLabel), node('op|aus', t('ausgaben'), by.aus, zLabel)]);
  // colours only where the table has them (surplus, changes in value): interest and contributions without one
  grp('plain', t('zinsen'), by.interest, by.interest.length ? node('interest', '', by.interest, zLabel).kids || [] : [], 'interest');
  const opRow = out.find(r => r.id === 'op'); if (opRow) opRow.abbr = SEC_ABBR.operating;          // named as in the cash bridge
  grp('plain', t('cf_einlagen_entnahmen'), by.ext, by.ext.length ? node('ext', '', by.ext, zLabel).kids || [] : [], 'ext');
  grp('value', t('cf_wertaenderungen'), by.value, by.value.length ? node('value', '', by.value, gLabel).kids || [] : []);
  const unk = sum(by.unk, z => cfRowSum(z, months)); if (Math.abs(unk) >= 0.005) out.push({id: 'unk', kind: 'one', label: t('cf_unklar'), v: unk, p: null, kids: null});
  // what the balance sheet shows beyond these rows (unknown balances, corrections): its own step, as in the cash bridge
  const moved = sum(out, r => r.kind === 'tot' ? 0 : r.v), off = known ? end - start - moved : 0;
  if (Math.abs(off) >= 0.5) out.push({id: 'off', kind: 'one', label: t('cf_abgleich_kurz'), long: t('cf_abgleich'), v: off, p: null, kids: null});
  const pl = (D.plan_months || []).includes(last) ? ' ' + t('cf_plan_klammer') : '';          // ending in the plan: a planned figure, named so
  out.push(known ? {id: 'nw1', kind: 'tot', bal: 'nw|' + last, label: t('cf_nv_ende') + pl, v: end} : {id: 'nw1', kind: 'tot', label: t('cf_veraenderung_nv') + pl, v: moved});
  return out;
}
// both bridges are drawn alike: where each keeps its open rows and its zoom
const BRIDGES = {
  liq: {el: 'cf-bridge', reset: 'cf-br-reset', title: 'cf_bruecke', tree: (D, c, p) => cfBridgeTree(D, c, p), zoom: 'cfBrZoom', open: () => S.cfBrOpen || (S.cfBrOpen = {op: true, inv: true, fin: true})},
  nw: {el: 'cf-wbridge', reset: 'cf-wb-reset', title: 'cf_verm_bruecke', tree: (D, c, p) => cfWealthTree(D, c, p), zoom: 'cfWbZoom', open: () => S.cfWbOpen || (S.cfWbOpen = {})},
};
function cfDrawBridge(which = 'liq') {
  const P = BRIDGES[which], D = B(), el = $('#' + P.el); if (!D || !el) return;
  const [cur, prev] = cfMonths(D, S.cfZeit), has = prev.length > 0;
  const open = P.open(), ahead = cur.some(m => cfIsOpen(D, m));          // running month or plan in the period
  // the rows shown: an open node as a bracket, then its parts one level further in; every other node a step
  const list = [];
  const visit = (n, depth, act) => { const isOpen = !!(n.kids && n.kids.length && open[n.id]);
    list.push({...n, depth, act: n.act || act, br: isOpen, hasKids: !!(n.kids && n.kids.length)});
    if (isOpen) { const at = list.length - 1; n.kids.forEach(k => visit(k, depth + 1, n.act || act)); list[at].end = list.length; } };
  for (const r of P.tree(D, cur, prev)) if (r.kind === 'tot') list.push({...r, depth: 0}); else visit(r, 0, r.act);
  // the waterfall: every step starts where the one before ended; a bracket spans its parts
  let lvl = 0;
  list.forEach(r => { if (r.kind === 'tot') { r.a = 0; r.b = r.v; lvl = r.v; } else if (!r.br) { r.a = lvl; r.b = lvl + r.v; lvl = r.b; } });
  list.forEach((r, i) => { if (r.br) { const parts = list.slice(i + 1, r.end).filter(x => !x.br); r.a = parts.length ? parts[0].a : lvl; r.b = parts.length ? parts[parts.length - 1].b : lvl; } });
  const W = Math.max(280, el.clientWidth), rh = r => r.kind === 'tot' || r.depth === 0 ? 24 : r.depth === 1 ? 21 : 19, rowsH = list.reduce((a, r) => a + rh(r), 0) + 6, AX = 18, H = rowsH + AX;
  const cw = r => r.depth ? 6.1 : 6.9, ind = r => 3 + r.depth * 10, disc = 10;          // parts one step further in
  const need = r => ind(r) + disc + r.label.length * cw(r) + (r.act && !r.depth ? 11 : 0) + (r.abbr ? 24 : 0) + 4;
  // the names take the room of the main rows -- the same whatever is open (longer names of parts are shortened, the full name on hover)
  const nameW = Math.min(W * 0.45, Math.max(Math.min(W * 0.32, 180), ...P.tree(D, cur, prev).map(r => need({...r, depth: 0})))), numW = 66, chW = has ? 44 : 0, L = nameW + 6, R = W - numW - chW - 8;
  const lo0 = Math.min(0, ...list.map(r => Math.min(r.a, r.b))), hi0 = Math.max(0, ...list.map(r => Math.max(r.a, r.b)));
  // zoomed in (a range dragged on the chart): that range fills the width, longer bars are cut at the edge and marked
  const zs = S[P.zoom], z = zs && zs[1] > zs[0] && zs[0] < hi0 && zs[1] > lo0 ? zs : null;
  const lo = z ? z[0] : lo0, hi = z ? z[1] : hi0, sp = (hi - lo) || 1, clamp = v => Math.max(lo, Math.min(hi, v));
  const X = v => L + (clamp(v) - lo) / sp * (R - L);
  CF['br_' + which] = {L, R, lo, hi, rowsH, top: AX};
  const rb = $('#' + P.reset); if (rb) rb.classList.toggle('hidden', !z);
  // a quiet amount axis at the top, beside the button that undoes the zoom: a few round values as thin vertical lines
  let lastX = -Infinity;          // labels never on top of each other (a narrow screen: fewer of them)
  const ticks = niceTicks(lo, hi, Math.max(2, Math.min(5, Math.floor((R - L) / 70))), 3).filter(v => v >= lo - sp * 1e-6 && v <= hi + sp * 1e-6)
    .filter(v => { const x = X(v); if (x - lastX < 38) return false; lastX = x; return true; });
  let g = ticks.map(v => `<line class="cf-br-grid${Math.abs(v) < sp * 1e-6 ? ' zero' : ''}" x1="${X(v).toFixed(1)}" x2="${X(v).toFixed(1)}" y1="${AX}" y2="${AX + rowsH}"/><text class="cf-tick" x="${X(v).toFixed(1)}" y="${AX - 6}" text-anchor="middle">${esc(Fk(v, false, Math.max(Math.abs(lo), Math.abs(hi))))}</text>`).join('')
    + `<rect class="cf-br-axis" x="${L}" y="0" width="${(R - L).toFixed(1)}" height="${AX}"/>`, y = AX + 3, prevEnd = null;
  list.forEach(r => {
    const h = rh(r), mid = y + h / 2, bh = r.kind === 'tot' ? 12 : r.depth === 0 ? 10 : r.depth === 1 ? 8 : 6, x0 = X(Math.min(r.a, r.b)), x1 = X(Math.max(r.a, r.b));
    const ch = r.kind === 'tot' ? null : cfChangeAmt(r.v, r.p, r.act === 'op'), kind = r.kind === 'tot' ? 'tot' : r.kind === 'one' ? 'one' : r.depth === 0 ? 'grp' : 'kid';          // investing, financing, interest, values: no colour (better or worse is not known)
    // a dashed line joins each step to the one before (a bracket is no step)
    if (!r.br && prevEnd != null) { const xj = X(r.kind === 'tot' ? r.b : r.a); g += `<line class="cf-br-link" x1="${xj.toFixed(1)}" x2="${xj.toFixed(1)}" y1="${prevEnd.toFixed(1)}" y2="${(mid - bh / 2).toFixed(1)}"/>`; }
    const dsc = r.hasKids ? `<text class="cf-br-disc" x="${ind(r)}" y="${(mid + 4).toFixed(1)}">${r.br ? '▾' : '▸'}</text>` : '';
    const nx = ind(r) + disc, room = Math.floor((nameW - nx - (r.kind === 'act' ? 11 : 0) - (r.abbr ? 24 : 0)) / cw(r));
    let mark = '';
    if (r.br) {          // a bracket over the parts: what they add up to, in the activity's colour (deeper: grey)
      const yb = mid, e0 = X(r.a), e1 = X(r.b), c = r.depth === 0 ? r.act : r.depth === 1 ? 'deep' : 'deep deeper';      // each level thinner
      mark = `<path class="cf-br-brace ${c}" d="M${e0.toFixed(1)},${(yb + 4).toFixed(1)}V${(yb - 1).toFixed(1)}H${e1.toFixed(1)}V${(yb + 4).toFixed(1)}"/>`;
    } else if (Math.abs(r.v) >= 0.005) {
      const cls = r.kind === 'tot' ? 'tot' : r.kind === 'one' ? 'unk' : r.v >= 0 ? 'in' : 'out';          // money in green, out red
      mark = `<rect class="cf-br-bar ${cls}${r.depth ? ' kid' : ''}" x="${x0.toFixed(1)}" y="${(mid - bh / 2).toFixed(1)}" width="${Math.max(2, x1 - x0).toFixed(1)}" height="${bh}" rx="${Math.min(3, bh / 2)}"/>`;
      // the running month or plan in the period: its bars hatched (a total: when its month is one of them)
      if (r.kind === 'tot' ? r.bal && cfIsOpen(D, r.bal.split('|')[1]) : ahead)
        mark += `<rect class="cf-br-hatch" fill="url(#cfbh-${which})" x="${x0.toFixed(1)}" y="${(mid - bh / 2).toFixed(1)}" width="${Math.max(2, x1 - x0).toFixed(1)}" height="${bh}" rx="${Math.min(3, bh / 2)}"/>`;
      // cut at the edge of the zoomed range: two slanted strokes
      for (const [cutAt, edge] of [[Math.min(r.a, r.b) < lo - sp * 1e-6, L], [Math.max(r.a, r.b) > hi + sp * 1e-6, R]]) if (cutAt)
        mark += `<path class="cf-break" d="M${(edge - 3).toFixed(1)},${(mid + bh / 2 + 2).toFixed(1)}L${(edge + 1).toFixed(1)},${(mid - bh / 2 - 2).toFixed(1)}M${(edge + 1).toFixed(1)},${(mid + bh / 2 + 2).toFixed(1)}L${(edge + 5).toFixed(1)},${(mid - bh / 2 - 2).toFixed(1)}"/>`;
    }
    // the amount and its change stand at the right, the parts open with a click (a shortened name: its full one); on the amount
    // or the change: both exact, with the period before and the parts
    const cutName = r.label.length > room;
    const tipI = chW && ch ? cfTip(`<div class="cf-tip-h">${esc(r.label)}</div><div class="cf-tip-kv"><span>${esc(t('betrag'))}</span><b>${cfEur(r.v)}</b><span>${esc(t('cf_vorjahr'))}</span><b class="pl">${r.p != null ? cfEur(r.p) : '–'}</b><span>${esc(t('cf_veraenderung'))}</span><b class="pl ${ch.cls}">${esc(ch.txt)}</b></div>`
        + (r.hasKids ? r.kids.map(k => cfTipRow('sw ' + (k.v >= 0 ? 'in' : 'out'), k.label, cfEur(k.v), cfChangeAmt(k.v, k.p, r.act === 'op') || {cls: '', txt: ''})).join('') : '')) : null;
    const balT = r.bal ? t(r.bal.startsWith('nw') ? 'cf_zur_bilanz_nv' : 'cf_zur_bilanz_liq', ML(r.bal.split('|')[1])) : '';          // a total: a click shows it in the balance sheet
    g += `<g class="cf-br-row ${kind}${r.br ? ' br' : ''}${r.hasKids || r.bal ? ' more' : ''}"${r.hasKids ? ` tabindex="0" role="button" data-br="${esc(r.id)}" aria-expanded="${r.br}"` : r.bal ? ` tabindex="0" role="link" data-bal="${esc(r.bal)}"` : ''} aria-label="${esc(r.label + ': ' + cfEur(r.v))}">${cutName || r.long || balT ? `<title>${esc(balT || r.long || r.label)}</title>` : ''}<rect class="cf-br-bg" x="0" y="${y}" width="${W}" height="${h}" rx="4"/>`
      + dsc + `<text class="cf-br-n" x="${nx}" y="${(mid + 4).toFixed(1)}">${esc(cutName ? r.label.slice(0, Math.max(3, room - 1)) + '…' : r.label)}${r.kind === 'act' && r.act !== 'plain' ? `<tspan class="cf-br-dot ${r.act}" dx="4" dy="-1">●</tspan>` : ''}${r.abbr ? `<tspan class="cf-br-abbr" dx="3" dy="${r.kind === 'act' ? 1 : 0}">${r.abbr}</tspan>` : ''}</text>`
      + mark + `<text class="cf-br-v" x="${(W - chW - 4).toFixed(1)}" y="${(mid + 4).toFixed(1)}" text-anchor="end"${tipI != null ? ` data-cftip="${tipI}"` : ''}>${(r.kind === 'tot' || r.v < 0 ? '' : '+') + esc(F0(r.v))}</text>`
      + (tipI != null ? `<text class="cf-br-c ${ch.cls}" x="${(W - 2).toFixed(1)}" y="${(mid + 4).toFixed(1)}" text-anchor="end" data-cftip="${tipI}">${esc(cfChgShort(ch))}</text>` : '') + `</g>`;
    if (!r.br) prevEnd = mid + bh / 2;
    y += h;
  });
  const defs = `<defs><pattern id="cfbh-${which}" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line class="cf-br-hatch-l" x1="0" y1="0" x2="0" y2="5"/></pattern></defs>`;
  el.innerHTML = `<svg class="cf-svg cf-br${z ? ' zoomed' : ''}" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(t(P.title))}">${defs}${g}</svg>`;
}

// 2. Per month (more than three years: per year): income, expenses, investing and financing stacked from one baseline --
// inflows up, outflows down. Below it, on a scale of its own, the change in cash: a big purchase does not flatten it. When a
// few months are far larger than the rest (a property bought), the scale follows the others and those bars are cut, marked
// and labelled -- the regular months stay readable.
function cfDrawMonths() {
  const D = B(), el = $('#cf-months'); if (!D || !el) return;
  const [cur] = cfMonths(D, S.cfZeit), byYear = cur.length > 36;
  const keys = byYear ? [...new Set(cur.map(m => m.slice(0, 4)))] : cur;
  const bs = keys.map(k => { const ms = byYear ? cur.filter(m => m.startsWith(k)) : [k];
    return {k, label: byYear ? k : ML(k), n: ms.length, part: byYear && ms.length < 12, net: cfSum(D, 'cash_change', ms), ein: cfSum(D, 'income', ms), aus: cfSum(D, 'expenses', ms),
      inv: cfSum(D, 'investing', ms), fin: cfSum(D, 'financing', ms), unk: cfSum(D, 'unclear', ms)}; });
  const parts = ['ein', 'aus', 'inv', 'fin', 'unk'];
  bs.forEach(b => { b.up = parts.reduce((a, k) => a + Math.max(0, b[k]), 0); b.dn = parts.reduce((a, k) => a + Math.min(0, b[k]), 0); });
  let hi = Math.max(0, ...bs.map(b => b.up)), lo = Math.min(0, ...bs.map(b => b.dn));
  if (hi - lo < 0.005) { el.innerHTML = `<div class="cf-empty muted small">${t('cf_keine_zahlungen')}</div>`; return; }
  // a few outliers (more than three times as high as most): the scale follows the regular months, those bars are cut
  const ext = bs.flatMap(b => [b.up, -b.dn]).filter(v => v > 0.5).sort((p, q) => p - q), q = ext[Math.floor((ext.length - 1) * 0.75)] || 0;
  const cut = ext.length >= 6 && ext[ext.length - 1] > 3 * q && q > 0 ? Math.max(...ext.filter(v => v <= 3 * q)) * 1.12 : null;     // just above the largest regular one
  if (cut) { hi = Math.min(hi, cut); lo = Math.max(lo, -cut); }
  // zoomed on its axis (drag up/down there): the range scaled -- bars beyond it cut and labelled like the outliers
  const Z = S.cfMoZ || {}, zUp = Z.up || 1, clip = !!cut || zUp !== 1; if (zUp !== 1) { hi *= zUp; lo *= zUp; }
  const downCut = clip && bs.some(b => b.dn < lo - 0.005);
  // below, on its own scale: the change in net worth -- saved (what came in less what went out, interest included) and changes
  // in value (portfolios, properties ...), stacked; the same months a year before as a dashed outline. Single huge months cut.
  const msOf = b => byYear ? cur.filter(m => m.startsWith(b.k)) : [b.k];
  bs.forEach(b => { const ms = msOf(b);
    b.nw = cfSum(D, 'net_worth_delta', ms); b.value = cfSum(D, 'valuation', ms);
    // as the table: the change in cash, plus investing and repaying moved back (they are no loss), plus the changes in value
    b.realloc = -D.cashflow.sections.reduce((a, sk) => sk.name === 'valuation' ? a : a + sk.rows.reduce((c, z) => z.nw ? c : c + cfRowSum(z, ms), 0), 0);
    b.bank = b.nw - b.value - b.realloc;
    b.nup = Math.max(0, b.bank) + Math.max(0, b.realloc) + Math.max(0, b.value); b.ndn = Math.min(0, b.bank) + Math.min(0, b.realloc) + Math.min(0, b.value); });
  const ends = bs.flatMap(b => [b.nup, -b.ndn]).filter(v => v > 0.5).sort((p, q) => p - q), q2 = ends[Math.floor((ends.length - 1) * 0.75)] || 0;
  const cut2 = ends.length >= 6 && ends[ends.length - 1] > 3 * q2 && q2 > 0 ? Math.max(...ends.filter(v => v <= 3 * q2)) * 1.12 : null;
  const nice = v => { const p = 10 ** Math.floor(Math.log10(v)), f = v / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p; };
  const zNw = Z.nw || 1, nmax = zNw !== 1 ? Math.max(1, (cut2 || ends[ends.length - 1] || 1) * zNw) : nice(Math.max(1, cut2 || ends[ends.length - 1] || 1)), clip2 = !!cut2 || zNw !== 1;
  const lowDown = clip2 && bs.some(b => -b.ndn > nmax);
  // no key: the tooltip names the colours; the room above the lower panel holds its title and the heights of cut bars
  const W = Math.max(280, el.clientWidth), H1 = W < 520 ? 170 : 200, H2 = 88, upCut2 = clip2 && bs.some(b => b.nup > nmax), gapH = (downCut ? 40 : 26) + 15 + (upCut2 ? 8 : 0), H = H1 + gapH + H2 + 20 + (lowDown ? 12 : 0), P = {l: W >= 640 ? 58 : 44, r: 8, t: 16};          // +18: the lower panel a little apart
  let ticks = niceTicks(lo, hi, 4, 4); const step = ticks.length > 1 ? ticks[1] - ticks[0] : (hi - lo);          // at least four lines
  if (!clip) { if (ticks[0] > lo + step * 1e-6) ticks.unshift(ticks[0] - step); if (ticks[ticks.length - 1] < hi - step * 1e-6) ticks.push(ticks[ticks.length - 1] + step); }
  else ticks = ticks.filter(v => v <= hi + step * 1e-6 && v >= lo - step * 1e-6);
  const y0 = clip ? lo : ticks[0], y1 = clip ? hi : ticks[ticks.length - 1], ref = Math.max(Math.abs(y0), Math.abs(y1));
  const y = v => P.t + (y1 - Math.max(y0, Math.min(y1, v))) / ((y1 - y0) || 1) * (H1 - P.t);
  const slot = (W - P.l - P.r) / bs.length, cutLab = v => { const l = (v > 0 ? '+' : '') + Fk(v, false, Math.abs(v)); return l.length * 6.2 > slot - 3 ? (v > 0 ? '+' : '') + Fs(v) : l; },          // a cut bar's height: short where columns are narrow
    bw = Math.max(2, Math.min(22, slot - 5)), x = i => P.l + slot * i + (slot - bw) / 2, cx = i => P.l + slot * (i + 0.5);
  // the running month and plan months: hatched behind their bars, as in the table
  let g = `<defs><pattern id="cf-m-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line class="cf-hatch-l" x1="0" y1="0" x2="0" y2="6"/></pattern></defs>`
    + bs.map((b, i) => msOf(b).some(m => cfIsOpen(D, m)) ? `<rect class="cf-ahead" x="${(P.l + slot * i + 1).toFixed(1)}" y="2" width="${(slot - 2).toFixed(1)}" height="${H - 20}" rx="3"/>` : '').join('');
  for (const v of ticks) g += `<line class="cf-grid-l${Math.abs(v) < step * 1e-6 ? ' zero' : ''}" x1="${P.l}" x2="${W - P.r}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/><text class="cf-tick" x="${P.l - 7}" y="${(y(v) + 3.5).toFixed(1)}" text-anchor="end">${(v > 0 ? '+' : '') + Fk(v, W >= 640, ref)}</text>`;
  bs.forEach((b, i) => {
    for (const sign of [1, -1]) {
      const ps = parts.filter(k => b[k] * sign > 0.005); let acc = 0;
      ps.forEach((k, j) => {
        const a = acc, e = acc + b[k]; acc = e;
        let ya = y(a), ye = y(e); if (sign > 0) { ya -= 1; ye += 1; } else { ya += 1; ye -= 1; }
        const top = Math.min(ya, ye), hgt = Math.abs(ye - ya); if (hgt < 0.6) return;
        const last = j === ps.length - 1, r = last ? Math.min(4, bw / 2, hgt) : 0, x0 = x(i), x1 = x0 + bw;
        const d = sign > 0
          ? `M${x0},${(top + hgt).toFixed(1)}L${x0},${(top + r).toFixed(1)}Q${x0},${top.toFixed(1)} ${(x0 + r).toFixed(1)},${top.toFixed(1)}L${(x1 - r).toFixed(1)},${top.toFixed(1)}Q${x1},${top.toFixed(1)} ${x1},${(top + r).toFixed(1)}L${x1},${(top + hgt).toFixed(1)}Z`
          : `M${x0},${top.toFixed(1)}L${x0},${(top + hgt - r).toFixed(1)}Q${x0},${(top + hgt).toFixed(1)} ${(x0 + r).toFixed(1)},${(top + hgt).toFixed(1)}L${(x1 - r).toFixed(1)},${(top + hgt).toFixed(1)}Q${x1},${(top + hgt).toFixed(1)} ${x1},${(top + hgt - r).toFixed(1)}L${x1},${top.toFixed(1)}Z`;
        g += `<path class="cf-col ${k}${b.part ? ' part' : ''}" d="${d}"/>`;
      });
      // cut: two slanted strokes across the bar near its end, the full height above (or below) it
      const tot = sign > 0 ? b.up : b.dn;
      if (clip && (sign > 0 ? tot > y1 + 0.005 : tot < y0 - 0.005)) {
        const ye = y(tot) + (sign > 0 ? 9 : -9), x0 = x(i) - 2, x1 = x(i) + bw + 2;
        g += `<path class="cf-break" d="M${x0},${(ye + 2).toFixed(1)}L${x1},${(ye - 2).toFixed(1)}M${x0},${(ye + 6).toFixed(1)}L${x1},${(ye + 2).toFixed(1)}"/>`
          + `<text class="cf-val-l" x="${cx(i).toFixed(1)}" y="${(sign > 0 ? P.t - 4 : H1 + 12).toFixed(1)}" text-anchor="middle">${cutLab(tot)}</text>`;
      }
    }
  });
  // the change in cash: a quiet short mark at its height -- only clear of the zero line and within the axis (bars cut: none, the tooltip has it)
  const over = Math.max(0, Math.min(3, (slot - bw) / 2 - 1.5));          // the marks a little wider than the bar -- never touching the next one
  bs.forEach((b, i) => { const yn = y(b.net); if (b.net >= y0 - 0.005 && b.net <= y1 + 0.005 && Math.abs(yn - y(0)) >= 4) g += `<line class="cf-net" x1="${(x(i) - over * 0.7).toFixed(1)}" x2="${(x(i) + bw + over * 0.7).toFixed(1)}" y1="${yn.toFixed(1)}" y2="${yn.toFixed(1)}"/>`; });
  const t2 = H1 + gapH, z2 = t2 + H2 / 2, y2 = v => z2 - Math.max(-nmax, Math.min(nmax, v)) / nmax * (H2 / 2 - 2);
  g += `<text class="cf-sub-l" x="4" y="${(t2 - (upCut2 ? 25 : 15)).toFixed(1)}">${esc(t('cf_veraenderung_nv'))}</text>`;          // a little room below the title
  // its scale: the top, the middle (0) and the bottom labelled, halfway a faint line
  for (const v of [nmax, nmax / 2, 0, -nmax / 2, -nmax]) {
    const yy = y2(v), lab = v === 0 || Math.abs(v) === nmax;
    g += `<line class="cf-grid-l${v === 0 ? ' zero' : ''}" x1="${P.l}" x2="${W - P.r}" y1="${yy.toFixed(1)}" y2="${yy.toFixed(1)}"/>` + (lab ? `<text class="cf-tick" x="${P.l - 7}" y="${(yy + 3.5).toFixed(1)}" text-anchor="end">${(v > 0 ? '+' : '') + Fk(v, W >= 640, nmax)}</text>` : '');
  }
  bs.forEach((b, i) => {
    for (const sign of [1, -1]) {
      let acc = 0;
      for (const [k, c] of [['bank', 'bank'], ['realloc', 'umsch'], ['value', 'value']]) {
        const v = b[k]; if (v * sign <= 0.005) continue;
        const a = y2(acc), e = y2(acc + v); acc += v;
        const top = Math.min(a, e), hgt = Math.abs(e - a); if (hgt < 0.6) continue;
        g += `<rect class="cf-col ${c}${b.part ? ' part' : ''}" x="${x(i).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${hgt.toFixed(1)}" rx="${Math.min(2, bw / 2)}"/>`;
      }
      const tot = sign > 0 ? b.nup : b.ndn;
      if (clip2 && Math.abs(tot) > nmax) {
        const ye = y2(tot) + (sign > 0 ? 7 : -7), x0 = x(i) - 2, x1 = x(i) + bw + 2;
        g += `<path class="cf-break nw" d="M${x0},${(ye + 2).toFixed(1)}L${x1},${(ye - 2).toFixed(1)}M${x0},${(ye + 6).toFixed(1)}L${x1},${(ye + 2).toFixed(1)}"/>`
          + `<text class="cf-val-l nw" x="${cx(i).toFixed(1)}" y="${(sign > 0 ? t2 - 5 : t2 + H2 + 11).toFixed(1)}" text-anchor="middle">${cutLab(tot)}</text>`;
      }
    }
    // the result -- the change in net worth -- as a short line at its height, across the bar (beyond the range: none, the tooltip has it)
    if (Math.abs(b.nup) + Math.abs(b.ndn) >= 0.5 && Math.abs(b.nw) <= nmax) { const yn = y2(b.nw); if (Math.abs(yn - y2(0)) >= 4) g += `<line class="cf-net" x1="${(x(i) - over * 0.7).toFixed(1)}" x2="${(x(i) + bw + over * 0.7).toFixed(1)}" y1="${yn.toFixed(1)}" y2="${yn.toFixed(1)}"/>`; }          // as above: only clear of the zero line
  });
  { const n = bs.length, lab = i => byYear || i === 0 || i === n - 1 || bs[i].k.endsWith('-01') ? bs[i].label : MONATE[+bs[i].k.slice(5) - 1];
    const order = [0, n - 1, ...bs.map((b, i) => i).filter(i => i > 0 && i < n - 1 && (byYear || bs[i].k.endsWith('-01'))), ...bs.map((b, i) => i).filter(i => i > 0 && i < n - 1)];
    // the first and the last month bold, as in the balance sheet's charts: the range shown at a glance
    const end = i => i === 0 || i === n - 1, cw = i => end(i) ? 6.8 : 6.2;
    const kept = []; for (const i of [...new Set(order)]) { const w = lab(i).length * cw(i) + 8, xc = Math.min(cx(i), W - lab(i).length * cw(i) / 2 - 2);
      if (kept.some(k => Math.abs(k.xc - xc) < (k.w + w) / 2)) continue; kept.push({i, w, xc}); }
    for (const {i, xc} of kept) g += `<text class="cf-tick${end(i) ? ' end' : ''}" x="${xc.toFixed(1)}" y="${H - 4}" text-anchor="middle">${esc(lab(i))}</text>`;
    g += `<rect class="cf-xaxis" x="${P.l}" y="${H - 16}" width="${W - P.l}" height="16" data-slot="${slot.toFixed(1)}"><title>${esc(t('cf_achse_ziehen'))}</title></rect>`
      // each scale: drag up/down (or scroll) on it to zoom, a click sets it back -- marked while changed
      + `<rect class="cf-yax${zUp !== 1 ? ' on' : ''}" data-p="up" x="0" y="0" width="${P.l - 2}" height="${H1 + 4}"><title>${esc(t('cf_yax_tip'))}</title></rect>`
      + `<rect class="cf-yax${zNw !== 1 ? ' on' : ''}" data-p="nw" x="0" y="${(t2 - 4).toFixed(1)}" width="${P.l - 2}" height="${H2 + 8}"><title>${esc(t('cf_yax_tip'))}</title></rect>`; }          // the axis: drag or scroll along it to move the period
  const sgn = v => (v > 0.5 ? '+' : '') + F0(v) + ' €', nz = (c, l, v) => Math.abs(v) >= 0.005 ? cfTipRow(c, l, sgn(v)) : '';          // rows of exactly 0,00: left out
  bs.forEach((b, i) => {
    const tip = cfTip(`<div class="cf-tip-h">${esc(byYear ? b.label : MLL(b.k))}${b.part ? ` <span class="muted">· ${b.n}${t('mon')}</span>` : ''}</div>`
      + nz('sw ein', t('einnahmen'), b.ein) + nz('sw aus', t('ausgaben'), b.aus) + nz('sw inv', SEC_LABEL.investing, b.inv) + nz('sw fin', SEC_LABEL.financing, b.fin) + nz('sw unk', t('cf_unklar'), b.unk)
      + `<div class="cf-tip-res">${cfTipTot(t('zahlungsfluss_gesamt_veraenderung_liqu'), sgn(b.net))}</div>`          // the sum of the bars above: no colour of its own, bold
      + `<div class="cf-tip-sum">${nz('sw bank', t('cf_bankguthaben_kurz'), b.bank) + nz('sw umsch', t('cf_umschichtungen'), b.realloc) + nz('sw value', t('cf_wertaenderungen'), b.value)}${cfTipTot(t('cf_veraenderung_nv'), sgn(b.nw))}`
      + `</div>`
      );
    g += `<rect class="cf-hit" data-cftip="${tip}" data-k="${b.k}" tabindex="0" x="${(P.l + slot * i).toFixed(1)}" y="0" width="${slot.toFixed(1)}" height="${H - 16}"/>`; });
  el.innerHTML = `<svg class="cf-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(t('cf_je_monat_t'))}">${g}</svg>`;
}

// 4. Expenses (or income) by position as a ring: how they are made up at a glance -- the positions in shades of red (income:
// green; darker = larger), the total and its change in the middle, each position named around the ring with its amount and
// change; hovering a slice (on the iPhone a tap) opens an outer ring with its categories
function cfPieItems(D, sec, months, prev) {
  const sek = D.cashflow.sections.find(s => s.name === sec) || {rows: []}, has = prev.length > 0, sg = sec === 'expenses' ? -1 : 1;
  let items = sek.rows.map(z => ({label: zLabel(z), v: sg * cfRowSum(z, months), p: has ? sg * cfRowSum(z, prev) : null,
    parts: cfDet(z).map(d => ({label: cfDetName(d), kat: d.category || null, plan: !!d.rest, v: sg * cfRowSum(d, months), p: has ? sg * cfRowSum(d, prev) : null})).filter(d => d.v >= 0.5)}))
    .filter(e => e.v >= 0.5).sort((a, b) => b.v - a.v);
  if (items.length > 7) { const rest = items.slice(6); items = items.slice(0, 6).concat([{label: t('cf_uebrige', rest.length), v: rest.reduce((a, e) => a + e.v, 0), p: cfRestP(rest, has), parts: rest.map(e => ({label: e.label, v: e.v, p: e.p, kats: e.parts.map(d => d.kat).filter(Boolean)})), rest: true}]); }
  return items;
}
function cfPie(D, months, prev) {
  const has = prev.length > 0, other = S.cfPieArt === 'ein' ? 'expenses' : 'income';
  const up = S.cfPieArt === 'ein', sec = up ? 'income' : 'expenses', sg = up ? 1 : -1, items = cfPieItems(D, sec, months, prev);
  if (!items.length && !cfPieItems(D, other, months, prev).length) { CF.pie = null; return ''; }
  const all = sg * cfSum(D, sec, months), before = has ? sg * cfSum(D, sec, prev) : null;
  const neg = ((D.cashflow.sections.find(s => s.name === sec) || {rows: []}).rows).reduce((a, z) => { const v = sg * cfRowSum(z, months); return v <= -0.5 ? a + v : a; }, 0);
  const span = cfSpanLabel;
  const yrs = has ? Math.round(((+months[0].slice(0, 4) - +prev[0].slice(0, 4)) * 12 + (+months[0].slice(5) - +prev[0].slice(5))) / 12) : 0;
  const title = !has ? t(up ? 'cf_einnahmen_kuchen' : 'cf_ausgaben_kuchen') : yrs === 1 ? t(up ? 'cf_einnahmen_vorjahr' : 'cf_ausgaben_vorjahr') : t(up ? 'cf_einnahmen_vorjahre' : 'cf_ausgaben_vorjahre', yrs);
  CF.pie = items.length ? {items, all, before, up, title, neg, tc: cfChange(all, before, up), prev: has, span: span(months), spanPrev: has ? span(prev) : '', n: months.length} : null;
  return `<div class="cf-duo-p" id="cf-pie-card" data-ex="cashflow.ring"><div class="lc-head"><b class="lc-title">${title}${hq('cf_ausgaben_kuchen')}</b>${cfMv('duo')}${cfArtSeg()}</div>`
    + (items.length ? `<div class="cf-plot" id="cf-pie"></div>` : `<div class="cf-empty muted small">${t('cf_keine_zahlungen')}</div>`) + `</div>`;
}
function cfDrawPie() {
  // the ring as large as the card allows beside the names; the names close to it, per side spread evenly from top to bottom.
  // The small slices (the most names) sit around nine o'clock, where there is the most room up and down.
  // A click on a slice (or its name) keeps it open: its categories are named around it instead of the positions, the middle
  // shows the position; a click on it again, beside it or Escape goes back.
  const el = $('#cf-pie'), P0 = CF.pie; if (!el || !P0) return;
  const {items, all, tc, up} = P0, sel = items.length === 1 ? 0 : items.findIndex(e => e.label === CF.pieSel), total = items.reduce((a, e) => a + e.v, 0), NCAT = 3, n = items.length;
  const W = Math.max(280, el.clientWidth), CW = 6.6, LH = 34;
  // room for the names: the positions' and their categories' (kept open), so the ring keeps its size either way
  const names = items.flatMap(e => [e.label, ...e.parts.slice().sort((x, y) => y.v - x.v).slice(0, NCAT).map(d => '● ' + d.label)]);
  const labW = Math.min(150, W * 0.22, Math.max(64, Math.max(...names.map(n => n.length), ...items.map(e => F0(e.v).length + 8)) * CW));     // longer names shortened (… the tooltip has them)
  const R2 = Math.max(58, Math.min(124, (W - 2 * (labW + 26)) / 2)), R1 = R2 - 13, R0 = Math.max(R1 - Math.max(24, R2 * 0.3), 40);
  const pt = (r, a, cx, cy) => `${(cx + r * Math.sin(a)).toFixed(2)},${(cy - r * Math.cos(a)).toFixed(2)}`;
  // where the slices go: by size clockwise, turned so that the smaller half of them (by count) is centred on nine o'clock
  const spans = items.map(e => e.v / total * Math.PI * 2), tail = Math.floor(n / 2);
  const before = spans.slice(0, tail).reduce((a, x) => a + x, 0), tailSpan = spans.slice(tail).reduce((a, x) => a + x, 0);
  const rot = 1.5 * Math.PI - (before + tailSpan / 2);
  let a = rot; const geo = items.map((e, i) => { const g0 = a; a += spans[i]; return {a0: g0, a1: a, mid: g0 + spans[i] / 2}; });
  const side = l => Math.sin(l.mid) >= 0;
  const perSide = [true, false].map(r => geo.filter(x => side(x) === r).length);
  const H = Math.max(2 * R2 + 40, Math.max(...perSide) * LH + 16), cx = W / 2, cy = H / 2, gap = 0.012;
  const arc = (a0, a1, ri, ro) => { const big = a1 - a0 > Math.PI ? 1 : 0;
    return `M${pt(ro, a0, cx, cy)}A${ro},${ro} 0 ${big} 1 ${pt(ro, a1, cx, cy)}L${pt(ri, a1, cx, cy)}A${ri},${ri} 0 ${big} 0 ${pt(ri, a0, cx, cy)}Z`; };
  const kv = (k, v, cls) => `<span>${esc(k)}</span><b class="${cls || ''}">${v}</b>`;
  let g = '';
  const labels = [], geoTip = [];
  items.forEach((e, i) => {
    const {a0: s0, a1: s1, mid} = geo[i], a0 = s0 + gap / 2, a1 = Math.max(s1 - gap / 2, a0 + 0.002);
    const shade = e.rest ? '' : `style="--k:${Math.round(100 - i * (55 / Math.max(1, n - 1)))}%"`;
    const ps = e.parts.slice().sort((x, y) => y.v - x.v), shown = ps.slice(0, NCAT), rest = ps.slice(NCAT), other = rest.reduce((s2, d) => s2 + d.v, 0);
    const segs = shown.map((d, k) => ({...d, key: 'cat' + (k + 1)})).concat(other >= 0.5 ? [{label: t('cf_uebrige', rest.length), v: other, key: 'cat0', p: cfRestP(rest, P0.prev)}] : []);
    let sub = '', b = a0; const sum = segs.reduce((s2, d) => s2 + d.v, 0) || 1;
    for (const d of segs) { const w = (a1 - a0) * d.v / sum, b1 = b + w; d.mid = (b + b1) / 2;
      if (segs.length > 1) sub += `<path class="cf-pie-sub ${d.key}" d="${arc(b + 0.004, Math.max(b + 0.006, b1 - 0.004), R1 + 3, R2)}"/>`; b = b1; }
    const ch = cfChange(e.v, e.p, up);
    const tip = cfTip(`<div class="cf-tip-h">${esc(e.label)}</div><div class="cf-tip-kv">${kv(t('betrag'), cfEur(e.v))}${kv(t('anteil'), cfPct(e.v, total) + ' %', 'pl')}`
      + (P0.prev ? `${kv(t('cf_vorperiode'), e.p != null ? cfEur(e.p) : '–', 'pl')}${kv(t('cf_veraenderung'), ch ? ch.txt : '–', 'pl ' + (ch ? ch.cls : ''))}` : '') + `</div>`
      + (segs.length > 1 ? segs.map(d => cfTipRow(d.key, d.label, cfEur(d.v), cfChange(d.v, d.p, up) || {cls: '', txt: ''})).join('') : ''));
    const st = sel < 0 ? '' : i === sel ? ' on' : ' off';
    // its share, small, inside the slice where the box fits between the ring's edges and the slice's sides
    const pc = cfPct(e.v, total) + ' %', pw = pc.length * 5.6 + 4, ph = 10, rm = (R0 + R1) / 2, sn = Math.abs(Math.sin(mid)), cs = Math.abs(Math.cos(mid));
    const share = pw * sn + ph * cs <= R1 - R0 - 3 && pw * cs + ph * sn <= (a1 - a0) * rm - 4
      ? `<text class="cf-pie-p" x="${(cx + rm * Math.sin(mid)).toFixed(1)}" y="${(cy - rm * Math.cos(mid) + 3.5).toFixed(1)}" text-anchor="middle">${pc}</text>` : '';
    geoTip[i] = tip;
    g += `<g class="cf-pie-sl${st}" data-cftip="${tip}" data-pie="${i}" tabindex="0" aria-pressed="${i === sel}" aria-label="${esc(e.label + ': ' + cfEur(e.v))}"><path class="cf-pie-a${e.rest ? ' rest' : ''}" ${shade} d="${arc(a0, a1, R0, R1)}"/>${share}${sub}</g>`;
    if (sel < 0) labels.push({e, i, mid, ch, tip, r: R1, main: true});          // the positions: close to the ring (its outer ring of categories only shows on hover)
    else if (i === sel) {
      const one = segs.length === 1 && e.parts.length ? [{...segs[0], mid}] : segs;
      if (!one.length) labels.push({e, i, mid, ch, tip, r: R2});
      const restKats = rest.flatMap(d => d.kat ? [d.kat] : d.kats || []);
      // each category (or "Übrige") its own hover box: its amount, its share of the position, the comparison period, the change
      const ctip = d => { const c = cfChange(d.v, d.p, up); return cfTip(`<div class="cf-tip-h">${esc(d.label.startsWith(e.label + ' › ') ? d.label : e.label + ' › ' + d.label)}</div><div class="cf-tip-kv">${kv(t('betrag'), cfEur(d.v))}${kv(t('cf_anteil_an', e.label), cfPct(d.v, e.v) + ' %', 'pl')}`
        + (P0.prev ? `${kv(t('cf_vorperiode'), d.p != null ? cfEur(d.p) : '–', 'pl')}${kv(t('cf_veraenderung'), c ? c.txt : '–', 'pl ' + (c ? c.cls : ''))}` : '') + `</div>`); };
      for (const d of one) labels.push({e: d, i, mid: d.mid, ch: cfChange(d.v, d.p, up), tip: ctip(d), r: R2, key: segs.length > 1 ? d.key : '',
        kats: d.key === 'cat0' ? restKats : d.kat ? [d.kat] : d.kats || [], est: d.key === 'cat0' ? rest.some(x => !x.kat && !x.kats) : !d.kat && !d.kats});
    }
  });
  for (const l of labels) { l.right = Math.sin(l.mid) >= 0; l.y = cy - (l.r + 14) * Math.cos(l.mid); }
  // the small slices sit around nine o'clock, so most names are on the left: the large ones near twelve or six o'clock
  // may take the right side instead, largest first, until both sides are about even
  // (only slices whose middle is close to twelve or six o'clock; the line then starts at their part on the right)
  if (sel < 0) { const n = r => labels.filter(l => l.right === r).length, TAU = Math.PI * 2;
    for (const l of labels.filter(x => !x.right && Math.abs(Math.sin(x.mid)) < 0.26).sort((p, q) => q.e.v - p.e.v)) {
      if (n(false) - n(true) <= 1) break;
      const g = geo[l.i], top = Math.ceil(g.a0 / TAU) * TAU, bottom = Math.floor(g.a1 / TAU) * TAU + Math.PI;
      const at = top < g.a1 ? top + Math.min((g.a1 - top) / 2, 0.35) : bottom > g.a0 && bottom < g.a1 ? bottom - Math.min((bottom - g.a0) / 2, 0.35) : null;
      if (at == null) continue;
      l.right = true; l.mid = at; l.y = cy - (l.r + 14) * Math.cos(at); } }
  // per side from top to bottom, at least a label apart, inside the card; a short line from the slice to its name
  for (const right of [true, false]) {
    const ls = labels.filter(l => l.right === right).sort((p, q) => p.y - q.y);
    let yPrev = -Infinity; for (const l of ls) { l.ly = Math.max(l.y, yPrev + LH, 18); yPrev = l.ly; }
    let over = (ls.length ? ls[ls.length - 1].ly : 0) - (H - 16); for (let k = ls.length - 1; k >= 0 && over > 0; k--) { ls[k].ly -= over; over = k ? Math.max(0, ls[k - 1].ly - (ls[k].ly - LH)) : 0; }
  }
  const maxCh = Math.max(4, Math.floor(labW / CW)), CWM = 7.1;          // the positions a little larger than their categories
  // a label answers a click over its whole area, also between its two lines (an invisible box behind them)
  const hw = (l, name) => Math.min(labW + 22, Math.max(name.length + (l.key ? 2 : 0), (F0(l.e.v) + (l.ch ? ' ' + l.ch.txt : '')).length) * (l.main ? CWM : CW) + 8);
  for (const l of labels) {
    const tx = l.right ? cx + l.r + 22 : cx - l.r - 22, anchor = l.right ? 'start' : 'end';
    const ex = cx + (l.r + 3) * Math.sin(l.mid), ey = cy - (l.r + 3) * Math.cos(l.mid), kx = l.right ? tx - 5 : tx + 5;
    const mc = l.main ? Math.floor((labW + R2 - R1) / CWM) : maxCh, name = l.e.label.length > mc ? l.e.label.slice(0, mc - 1) + '…' : l.e.label;
    g += `<path class="cf-pie-lead" d="M${ex.toFixed(1)},${ey.toFixed(1)}L${kx.toFixed(1)},${(l.ly - 4).toFixed(1)}"/>`
      + `<g class="cf-pie-lab${l.main ? ' main' : ''}" data-cftip="${l.tip}" data-pie="${l.i}"${l.kats && l.kats.length ? ` data-kats="${esc(JSON.stringify(l.kats))}" data-name="${esc(l.e.label)}"${l.est ? ' data-est="1"' : ''}` : ''}><rect class="cf-pie-hit" x="${(l.right ? tx - 4 : tx - hw(l, name) + 4).toFixed(1)}" y="${(l.ly - 19).toFixed(1)}" width="${hw(l, name).toFixed(1)}" height="32"/><text x="${tx.toFixed(1)}" y="${(l.ly - 6).toFixed(1)}" text-anchor="${anchor}" class="cf-pie-n">${l.key ? `<tspan class="cf-pie-k ${l.key}">● </tspan>` : ''}${esc(name)}</text>`
      + `<text x="${tx.toFixed(1)}" y="${(l.ly + 9).toFixed(1)}" text-anchor="${anchor}" class="cf-pie-m">${esc(F0(l.e.v))}${l.ch ? `<tspan class="${l.ch.cls}"> ${esc(l.ch.txt)}</tspan>` : ''}</text></g>`;
  }
  // the middle: the total and its change (hovering it names both periods and the amounts) -- or the position kept open
  const diff = P0.before != null ? all - P0.before : null;
  if (sel >= 0) {
    const e = items[sel], ch = cfChange(e.v, e.p, up), room = Math.max(4, Math.floor(2 * (R0 - 8) / 6.4));
    const nm = e.label.length > room ? e.label.slice(0, room - 1) + '…' : e.label;
    g += `<g class="cf-pie-c" data-reftip="${geoTip[sel]}" data-pie="${items.length === 1 ? 0 : -1}" tabindex="0" aria-label="${esc(items.length === 1 ? e.label : t('cf_pie_zurueck'))}">${items.length === 1 ? '' : `<title>${esc(t('cf_pie_zurueck'))}</title>`}<circle cx="${cx}" cy="${cy}" r="${(R0 - 2).toFixed(1)}"/>`
      + `<text class="cf-pie-cn" x="${cx}" y="${cy - 16}" text-anchor="middle">${esc(nm)}</text><text class="cf-pie-v" x="${cx}" y="${cy + 4}" text-anchor="middle">${esc(F0(e.v))} €</text>`
      + (ch ? `<text class="cf-pie-d ${ch.cls}" x="${cx}" y="${cy + 22}" text-anchor="middle">${esc(ch.txt)}</text>` : '') + `</g>`;
    el.innerHTML = `<svg class="cf-svg pinned${up ? ' ein' : ''}" data-ex="cashflow.ring.pinned" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(e.label)}">${g}</svg>`;
    return;
  }
  const ctip = cfTip(`<div class="cf-tip-h">${esc(t(up ? 'einnahmen' : 'ausgaben'))}</div><div class="cf-tip-kv">${kv(P0.span, cfEur(all))}`
    + (P0.neg <= -0.5 ? kv(t('cf_gegenposten'), cfEur(P0.neg), 'pl') : '')
    + (P0.before != null ? `${kv(P0.spanPrev, cfEur(P0.before), 'pl')}${kv(t('cf_veraenderung'), (diff > 0.5 ? '+' : diff < -0.5 ? '−' : '±') + cfEur(Math.abs(diff)) + (tc ? ' (' + tc.txt + ')' : ''), 'pl ' + (tc ? tc.cls : ''))}` : '') + `</div>`);
  g += `<g class="cf-pie-c" data-cftip="${ctip}" tabindex="0" aria-label="${esc(t(up ? 'einnahmen' : 'ausgaben') + ': ' + cfEur(all))}"><circle cx="${cx}" cy="${cy}" r="${(R0 - 2).toFixed(1)}"/>`
    + `<text class="cf-pie-len" x="${cx}" y="${cy + (tc ? -19 : -14)}" text-anchor="middle">${esc(spanText(P0.n))}</text>`          // how long the period is, quietly above the total
    + `<text class="cf-pie-v" x="${cx}" y="${cy + (tc ? 1 : 6)}" text-anchor="middle">${esc(F0(all))} €</text>` + (tc ? `<text class="cf-pie-d ${tc.cls}" x="${cx}" y="${cy + 21}" text-anchor="middle">${esc(tc.txt)}</text>` : '') + `</g>`;
  el.innerHTML = `<svg class="cf-svg${up ? ' ein' : ''}" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(P0.title)}">${g}</svg>`;
}
// ---- further charts, to choose from: trends without one-offs, savings rate, seasonality, how long the cash lasts, the year so far
const cfEur = v => F0(v) + ' €';
// 9. Expenses (or income, as the ring beside it) by month and position: the darker, the more that month -- one scale for every
// cell, so a large position stands out against a small one; the amount in the tooltip
const cfHeatQ = () => { const D = B(); return !!D && cfMonths(D, S.cfZeit)[0].length > 24; };
// expenses or income: one switch for the ring and the heat map beside it (at the right of their card)
const cfArtSeg = () => { const up = S.cfPieArt === 'ein'; return `<div class="seg small" id="cf-pie-art" role="group">${[['aus', 'ausgaben'], ['ein', 'einnahmen']].map(([k, l]) => `<button data-a="${k}" class="${(up ? 'ein' : 'aus') === k ? 'on' : ''}" aria-pressed="${(up ? 'ein' : 'aus') === k}">${t(l)}</button>`).join('')}</div>`; };
// the switch and the arrows at the top right of the card: in the ring's head (above when stacked), in the heat map's without a ring
// amounts or the change against the year before (the same month a year earlier): amounts at first, a switch at the top right
const cfHeatChg = () => S.cfHeatMode === 'chg';
const cfHeatSeg = () => `<div class="seg small" id="cf-heat-mode" role="group" aria-label="${esc(t('cf_heat_modus'))}">${[['abs', 'cf_heat_betraege', 'cf_heat_betraege_tip'], ['chg', 'cf_heat_vj', 'cf_heat_vj_tip']].map(([k, l, tip]) => `<button data-hmode="${k}" class="${(cfHeatChg() ? 'chg' : 'abs') === k ? 'on' : ''}" aria-pressed="${(cfHeatChg() ? 'chg' : 'abs') === k}" title="${esc(t(tip))}">${t(l)}</button>`).join('')}</div>`;
const cfHeatCard = (own = false) => `<div class="cf-duo-h" id="cf-heat-card" data-ex="cashflow.heatmap"><div class="lc-head"><b class="lc-title">${t(S.cfPieArt === 'ein' ? (cfHeatQ() ? 'cf_heatmap_ein_q' : 'cf_heatmap_ein') : (cfHeatQ() ? 'cf_heatmap_q' : 'cf_heatmap'))}${hq('cf_heatmap')}</b>${own ? cfMv('duo') + cfArtSeg() : ''}${cfHeatSeg()}</div><div id="cf-heat"></div></div>`;
// a change in a small cell: whole percent, from 1000 % on in thousands ("+1,5T%", "+12T%") -- the percent sign always there
const pctCell = d => { const a = Math.abs(d), s = d > 0 ? '+' : d < 0 ? '−' : '±';
  return s + (a >= 999.5 ? (a / 1000).toLocaleString(LOCALE, {maximumFractionDigits: a >= 9950 ? 0 : 1}) + t('tsd_kurz') : Math.round(a).toLocaleString(LOCALE)) + '%'; };
function cfDrawHeat() {
  // per row the position's average month at the right; hovering a cell shows what made up that month (categories, largest first)
  const D = B(), el = $('#cf-heat'); if (!D || !el) return;
  const up = S.cfPieArt === 'ein', sec = up ? 'income' : 'expenses', sg = up ? 1 : -1;
  const all = cfMonths(D, S.cfZeit)[0], q = all.length > 24, bk = m => q ? m.slice(0, 4) + '-Q' + Math.ceil(+m.slice(5) / 3) : m;
  const cnt = {}; all.forEach(m => { cnt[bk(m)] = (cnt[bk(m)] || 0) + 1; });
  const ms = [...new Set(all.map(bk))], sek = D.cashflow.sections.find(s => s.name === sec) || {rows: []}, by = new Map();
  const ahead = new Set(all.filter(m => cfIsOpen(D, m)).map(bk));          // the running month and plan months: hatched
  const lab = (k, full) => q ? k.slice(5) + ' ' + k.slice(2, 4) : full ? ML(k) : MONATE_LANG[+k.slice(5) - 1].slice(0, 3);
  const catName = cfDetName;
  for (const z of sek.rows) {
    const k = zLabel(z), r = by.get(k) || {label: k, v: {}, cats: new Map(), paths: new Set(), est: false, none: !!(z.lbl && z.lbl[0] === 'cf_ohne_kategorie'), zs: []}; r.zs.push(z);
    for (const d of z.details || []) { if (d.category) r.paths.add(d.category); else r.est = true; }
    ms.forEach(m => { r.v[m] = r.v[m] || 0; }); all.forEach(m => { r.v[bk(m)] += sg * (cfVals(z)[m] || 0); });
    for (const d of cfDet(z)) { const n = catName(d), c = r.cats.get(n) || {}; all.forEach(m => { c[bk(m)] = (c[bk(m)] || 0) + sg * (cfVals(d)[m] || 0); }); r.cats.set(n, c); }          // (plan months: the category's plan)
    by.set(k, r);
  }
  const all2 = [...by.values()].map(r => ({...r, sum: ms.reduce((a, m) => a + r.v[m], 0)})).filter(r => r.sum >= 0.5).sort((a, b) => b.sum - a.sum);
  const none = all2.filter(r => r.none), rows = all2.filter(r => !r.none).slice(0, 10 - none.length).concat(none);
  if (!rows.length || !ms.length) { el.innerHTML = `<div class="cf-empty muted small">${t('cf_keine_zahlungen')}</div>`; return; }
  // all positions together, as a row of its own below the others, on its own scale (the sum is always far larger)
  const tot = {label: t(up ? 'cf_heat_summe_ein' : 'cf_heat_summe_aus'), v: {}, cats: new Map(), paths: new Set(), est: false, total: true, zs: sek.rows};
  // the same month (quarter) a year before -- only where all its months are in the data
  const first = (D.months || [])[0], prevY = (r, m) => { const pm = all.filter(x => bk(x) === m).map(x => mShift(x, -12));
    return first && pm.length && pm.every(x => x >= first) ? pm.reduce((a, x) => a + r.zs.reduce((b, z) => b + sg * (cfVals(z)[x] || 0), 0), 0) : null; };
  ms.forEach(m => { tot.v[m] = 0; }); for (const z of sek.rows) all.forEach(m => { tot.v[bk(m)] += sg * (cfVals(z)[m] || 0); });
  for (const r of by.values()) { r.paths.forEach(x => tot.paths.add(x)); tot.est = tot.est || r.est; ms.forEach(m => { if (Math.abs(r.v[m]) >= 0.5) { const c = tot.cats.get(r.label) || {}; c[m] = r.v[m]; tot.cats.set(r.label, c); } }); }
  tot.sum = ms.reduce((a, m) => a + tot.v[m], 0);
  CF.heat = {rows: rows.concat([tot]), months: m => all.filter(x => bk(x) === m), lab: m => q ? lab(m) : ML(m)};          // a click on a cell: its transactions
  // colour by amount, robust against a few huge months: the scale follows the regular cells (up to three times the upper
  // quartile) -- the highest of them in the strongest colour; cells above it the strongest colour too, framed and marked
  const scale = (lines, most = Infinity) => {          // most: the regular scale's end at the latest (a change: 100 %)
    const regular = lines.map(vals => { const xs = vals.filter(v => v > 0.5).sort((p, r) => p - r); if (!xs.length) return 0;
      const q3 = xs[Math.floor((xs.length - 1) * 0.75)]; return xs.length >= 4 ? Math.max(...xs.filter(v => v <= 3 * q3)) : xs[xs.length - 1]; });
    const top = Math.max(0, ...lines.flat()), cap = Math.min(Math.max(...regular, 0.5), most);
    return {cap, top, k: v => v <= 0.5 ? 0 : v <= cap ? 0.1 + 0.9 * v / cap : 1}; };
  // the change against the year before: per cell new (nothing then, something now -- the strongest colour and ✦), unknown (the year
  // before is not in the data: grey, as no amount) or the percentage; one robust scale on its size, as for the amounts
  const chgMode = cfHeatChg();
  const chg = (r, m) => { const v = r.v[m], p = prevY(r, m); if (p == null) return null; if (Math.abs(p) < 0.5) return Math.abs(v) < 0.5 ? {d: 0} : {d: v > 0 ? Infinity : -Infinity, neu: true};
    return {d: (v - p) / Math.abs(p) * 100}; };
  if (chgMode) for (const r of rows.concat([tot])) { r.c = {}; ms.forEach(m => { r.c[m] = ahead.has(m) ? null : chg(r, m); }); }          // a month begun or planned: no comparison
  const finite = r => ms.map(m => r.c[m] && isFinite(r.c[m].d) ? Math.abs(r.c[m].d) : 0);
  const sc = chgMode ? scale(rows.map(finite), 100) : scale(rows.map(r => ms.map(m => r.v[m]))), scT = chgMode ? scale([finite(tot)], 100) : scale([ms.map(m => tot.v[m])]);
  const avgMax = Math.max(1, ...rows.map(r => Math.abs(r.sum / all.length)));          // the averages' unit follows the largest of them
  // the change over the whole period (only the months whose year before is known): the column at the right
  const heatAll = r => { const ks = ms.filter(m => r.c[m] != null); if (!ks.length) return '–'; const v = ks.reduce((a, m) => a + r.v[m], 0), p = ks.reduce((a, m) => a + prevY(r, m), 0);
    return Math.abs(p) < 0.5 ? (Math.abs(v) < 0.5 ? '±0%' : '✦') : pctCell((v - p) / Math.abs(p) * 100); };          // new: its mark, as in the cells
  const every = Math.max(1, Math.ceil(ms.length * 34 / Math.max(1, el.clientWidth * 0.66)));          // names that fit
  const kv = (k, v) => `<span>${esc(k)}</span><b>${v}</b>`;
  let h = `<div class="cf-heat${up ? ' ein' : ''}${chgMode ? ' chg' : ''}"${chgMode ? ' data-ex="cashflow.heatmap.change"' : ''} style="--ch:${Math.round(Math.max(18, Math.min(32, 240 / rows.length)))}px;grid-template-columns:minmax(90px, 24%) repeat(${ms.length}, minmax(0, 1fr)) auto"><span></span>${ms.map((m, i) => { const on = (ms.length - 1 - i) % every === 0, first = ms.findIndex((x, j) => (ms.length - 1 - j) % every === 0) === i; return `<span class="cf-heat-m">${on ? esc(lab(m, (first || m.endsWith('-01')) && every * el.clientWidth * 0.66 / ms.length >= 46)) : ''}</span>`; }).join('')}<span class="cf-heat-m cf-heat-avg" title="${esc(t(chgMode ? 'cf_heat_vj_ges' : 'cf_schnitt_monat'))}">${chgMode ? '±' : 'Ø'}</span>`;
  CF.heat.rows.forEach((r, ri) => {
    const open = r.none || r.paths.size, S2 = r.total ? scT : sc;
    if (r.total) h += `<span class="cf-heat-sep"></span>`;
    const ex = r.total ? ' data-ex="cashflow.heatmap.total"' : '';          // the row of all positions together (docs/ui)
    // the name: the bookings of the whole period (as a cell does for its month)
    h += `<span class="cf-heat-n${r.total ? ' tot' : ''}${open ? ' open' : ''}"${ex} title="${esc(r.label)}"${open ? ` data-hr="${ri}" data-hm="*" tabindex="0"` : ''}>${esc(r.label)}</span>` + ms.map(m => { const v = r.v[m], c = chgMode ? r.c[m] : null;
      // new (nothing a year before): the strongest colour and a mark, no frame (no outlier)
      const k = chgMode ? (!c ? 0 : c.neu ? 1 : S2.k(Math.abs(c.d))) : S2.k(v), big = chgMode ? !!c && !c.neu && Math.abs(c.d) > S2.cap : v > S2.cap, neu = chgMode && !!c && !!c.neu;
      const good = k && c && c.d ? (c.d > 0) === up : null, mark = chgMode ? (!c ? '' : pctCell(c.d)) : Fs(v, 0);
      const cs = [...r.cats].map(([n, c]) => [n, c[m] || 0]).filter(([, x]) => Math.abs(x) >= 0.5).sort((p, q) => q[1] - p[1]);
      const shown = cs.length > 7 ? cs.slice(0, 6) : cs, rest = cs.slice(shown.length);
      const p = prevY(r, m), pch = cfChange(v, p, up);          // the year before and the change, in one line
      const before = p != null ? `<div><i></i><span>${esc(t('cf_vorjahr'))}</span><b class="cf-tip-pv">${cfEur(p)}<em class="${pch ? pch.cls : ''}">${pch ? pch.txt : '–'}</em></b></div>` : '';          // value and change side by side, at the right
      const parts = shown.length > 1 || (shown.length === 1 && shown[0][0] !== r.label) ? `<div class="cf-tip-kv cf-tip-parts">${shown.map(([n, x]) => kv(n, cfEur(x))).join('')}${rest.length ? kv(t('cf_uebrige', rest.length), cfEur(rest.reduce((a, [, x]) => a + x, 0))) : ''}</div>` : '';
      const tip = cfTip(`<div class="cf-tip-h">${esc(r.label)} <span class="muted">· ${esc(q ? lab(m) : ML(m))}</span></div>${cfTipRow(up ? 'sw in' : 'sw out', t(up ? 'einnahmen' : 'ausgaben'), cfEur(v))}${before}${parts}${q && cnt[m] < 3 ? `<div class="cf-tip-note">${esc(t('cf_teilquartal', cnt[m]))}</div>` : ''}${open && Math.abs(v) >= 0.5 ? `<div class="cf-tip-hint">${esc(t('cf_klick_umsaetze'))}</div>` : ''}`);
      return `<span class="cf-heat-c${k ? '' : ' none'}${chgMode && !c ? ' na' : ''}${good === true ? ' good' : good === false ? ' bad' : ''}${q && cnt[m] < 3 ? ' part' : ''}${open && Math.abs(v) >= 0.5 ? ' open' : ''}${big ? ' big' : ''}${neu ? ' neu' : ''}${ahead.has(m) ? ' ahead' : ''}"${ex} style="${k ? `--k:${Math.round(k * 100)}%` : ''}" data-cftip="${tip}" tabindex="0"${open && Math.abs(v) >= 0.5 ? ` data-hr="${ri}" data-hm="${m}"` : ''}>${big ? `<b class="cf-heat-x" data-up="${!c || c.d > 0 ? 1 : 0}" data-lvl="${(x => x > 10 ? 3 : x > 3 ? 2 : 1)((chgMode ? Math.abs(c.d) : v) / S2.cap)}">${esc(mark)}</b>` : neu ? `<b class="cf-heat-x neu" aria-label="${esc(t('cf_heat_neu'))}">✦</b>` : ''}</span>`; }).join('')          // an outlier: its amount (its change) in the cell
      + `<span class="cf-heat-v${r.total ? ' tot' : ''}"${ex}>${esc(chgMode ? heatAll(r) : Fk(r.sum / all.length, false, r.total ? Math.abs(r.sum / all.length) : avgMax))}</span>`;
  });
  el.innerHTML = h + '</div>';
  // too narrow for the amount (the change): a mark -- one, two or three by how far beyond the regular scale (3 and 10 times)
  for (const b of $$('.cf-heat-x:not(.neu)', el)) if (b.scrollWidth > b.parentNode.clientWidth - 4) { b.textContent = (b.dataset.up === '0' ? '▼' : '▲').repeat(+b.dataset.lvl || 1); b.classList.add('mark'); }
}
// 3. Where the money came from and where it went: everything that came in (income, loans taken up, sales, less cash) and
// everything it was used for (expenses, investments, repayment, interest, more cash) -- both sides add up to the same sum
function cfSourcesUses(D, months, prev = []) {
  const {src, use} = cfFlowItems(D, months);
  // the period before (hover): each item and part by its name on the same side -- not there then: nothing flowed that way
  const has = prev.length > 0, was = has ? cfFlowItems(D, prev) : null;
  const withP = (list, before) => list.forEach(e => { const m = has ? (before || []).find(x => x.label === e.label) : null;
    e.p = has ? (m ? m.v : 0) : null; if (e.kids) withP(e.kids, m && m.all); });
  withP(src, was && was.src); withP(use, was && was.use);
  const total = src.reduce((a, e) => a + e.v, 0);
  if (total < 0.5) { CF.flow = null; return ''; }
  // small flows (under 3 % of everything) together as "the others" -- so that every name stays readable; a click opens them
  const group = (list, side) => { list.sort((p, q) => q.v - p.v); const small = list.filter(e => e.v < total * 0.03);
    if (small.length < 2) return list;
    return list.filter(e => e.v >= total * 0.03).concat([{label: t('cf_uebrige_n', small.length), v: small.reduce((a, e) => a + e.v, 0), p: cfRestP(small, has), act: 'mix', kids: small, key: side + '|~'}]); };
  CF.flow = {src: group(src, 's'), use: group(use, 'u'), total, has, span: months.length > 1 ? ML(months[0]) + ' – ' + ML(months[months.length - 1]) : ML(months[0]), n: months.length};
  return `<div class="card bch cf-card __CLS__" data-cfid="flow" data-ex="cashflow.flow"><div class="lc-head"><b class="lc-title">${t('cf_herkunft_verwendung')}${hq('cf_herkunft_verwendung')}</b>${cfMv('flow')}</div>`
    + `<div class="cf-plot" id="cf-flow"></div></div>`;
}
function cfFlowItems(D, months) {
  // every item with its parts (a position: its categories; a kind of investing or financing: its rows) -- a click opens them
  const src = [], use = [];
  const put = (label, v, act, kids) => { const k = (kids || []).map(x => ({...x, v: v >= 0 ? x.v : -x.v})).filter(x => x.v >= 0.5);
    if (v >= 0.5) src.push({label, v, act, kids: k.length > 1 ? k : null, all: k}); else if (v <= -0.5) use.push({label, v: -v, act, kids: k.length > 1 ? k : null, all: k}); };
  const cats = zs => { const m = new Map(); for (const z of zs) for (const d of cfDet(z)) { const k = cfDetName(d); m.set(k, (m.get(k) || 0) + cfRowSum(d, months)); }
    return [...m.entries()].map(([label, v]) => ({label, v})).sort((a, b) => Math.abs(b.v) - Math.abs(a.v)); };
  for (const [sec, act] of [['income', 'ein'], ['expenses', 'aus']]) {
    const sek = D.cashflow.sections.find(s => s.name === sec) || {rows: []}, by = new Map();
    for (const z of sek.rows) { const k = zLabel(z), r = by.get(k) || {v: 0, zs: []}; r.v += cfRowSum(z, months); r.zs.push(z); by.set(k, r); }
    for (const [l, r] of by) if (Math.abs(r.v) >= 0.5) put(l, r.v, act, cats(r.zs));
  }
  for (const [sec, act] of [['investing', 'inv'], ['financing', 'fin']]) for (const g of cfGroups(D, sec, months)) {
    const by = new Map(); for (const z of g.rows) by.set(zLabel(z), (by.get(zLabel(z)) || 0) + cfRowSum(z, months));
    put(g.label, g.v, act, [...by.entries()].map(([label, v]) => ({label, v})));
  }
  put(t('cf_unklar'), cfSum(D, 'unclear', months), 'unk');
  let change = cfSum(D, 'cash_change', months);
  const sums = D.cashflow.sums || {}, allM = D.months || [], before = allM[allM.indexOf(months[0]) - 1], last = months[months.length - 1];
  if (before && sums[before]?.bank != null && sums[last]?.bank != null) {
    const real = sums[last].bank - sums[before].bank;
    put(t('cf_abgleich'), real - change, 'unk'); change = real;
  }
  if (change <= -0.5) src.push({label: t('cf_bank_weniger'), v: -change, act: 'tot'}); else if (change >= 0.5) use.push({label: t('cf_bank_mehr'), v: change, act: 'tot'});
  return {src, use};
}
// The money flow as a Sankey diagram: everything that came in on the left, everything it went to on the right; the bands run
// into one another in the middle with a soft change of colour -- money has no label, so no source is tied to a use. Each band
// as wide as its amount; the larger ones carry their share. A click on a name with ▸ opens its parts (▾ closes them).
function cfDrawFlow() {
  const el = $('#cf-flow'), F = CF.flow; if (!el || !F) return; CF.flHov = null;
  const open = CF.flowOpen || (CF.flowOpen = {});
  const keyOf = (e, side, parent) => e.key || side + '|' + (parent ? parent + '›' : '') + e.label;
  // the nodes of a side: an open item gives way to its parts, their heights in proportion within it
  const flat = (list, side) => { const out = [];
    const walk = (e, h0, depth, parent, act, pLabel) => { const key = keyOf(e, side, parent), kids = e.kids && e.kids.length > 1 ? e.kids : null;
      if (kids && open[key]) { const sum = kids.reduce((a, k) => a + k.v, 0) || 1; kids.forEach(k => walk(k, h0 * k.v / sum, depth + 1, key, e.act === 'mix' ? k.act : act, e.act === 'mix' ? t('cf_uebrige_kurz') : e.label)); }
      else out.push({...e, act: e.act === 'mix' ? 'unk' : act, key, depth, parentKey: parent, parentLabel: pLabel, hv: h0, more: !!kids}); };
    list.forEach(e => walk(e, e.v, 0, null, e.act, null));
    return out; };
  const L0 = flat(F.src, 's'), R0 = flat(F.use, 'u');
  // every item with parts, at every level: a click beside the bands opens them all (and closes them again)
  const allKeys = []; { const walk = (e, side, parent) => { const key = keyOf(e, side, parent); if (e.kids && e.kids.length > 1) { allKeys.push(key); e.kids.forEach(k => walk(k, side, key)); } };
    F.src.forEach(e => walk(e, 's', null)); F.use.forEach(e => walk(e, 'u', null)); }
  CF.flowAll = allKeys;          // a click beside the bands: all open -- or, when any is, all closed (a normal pointer there)
  // amounts short (17,4T): the names take less room, the bands more
  // half width: the amount small below the name, both as short as they can be -- the bands keep the middle
  const amt = v => Fs(v);
  // the names take a fixed share of the width -- opening an item never narrows the bands (longer names shortened, whole on hover)
  const W = Math.max(300, el.clientWidth), narrow = W < 760;
  const LW = narrow ? Math.max(90, W * 0.27) : Math.min(220, W * 0.24), RW = LW, nodeW = 8, gap = 5, tiny = W < 480, LH = tiny ? 28 : 18, HEAD = 13;          // iPhone: the amount below the name          // a name and its amount on one line; an opened group: a row above
  // beside another chart in the same row: as tall as that one's content (its plot -- not the card, which the row stretches)
  el.innerHTML = ''; const card = el.closest('.cf-card'), ct = card ? card.getBoundingClientRect().top : 0;
  const sib = card && card.classList.contains('cf-half') ? [card.previousElementSibling, card.nextElementSibling].find(x => x && x.classList.contains('cf-half') && Math.abs(x.getBoundingClientRect().top - ct) < 2) : null;
  const sp = sib && $('.cf-plot', sib), room = sp ? Math.min(640, sp.getBoundingClientRect().bottom - el.getBoundingClientRect().top) : 0;
  const heads = list => list.filter((e, i) => e.parentKey && (i === 0 || list[i - 1].parentKey !== e.parentKey)).length;
  const n = Math.max(L0.length * (LH + 3) + heads(L0) * HEAD, R0.length * (LH + 3) + heads(R0) * HEAD), H = Math.max(200, n + 22 + (tiny ? 12 : 0), room), top = 16, bot = H - 6 - (tiny ? 12 : 0);       // beside a taller card: its height
  const avail = side => (bot - top) - gap * (side.length - 1);
  let k = Math.min(avail(L0), avail(R0)) / F.total;
  for (let i = 0; i < 6; i++) { const over = Math.max(...[L0, R0].map(sd => sd.reduce((a, e) => a + Math.max(1.5, e.hv * k), 0) - avail(sd))); if (over <= 0.5) break; k *= Math.max(0.1, 1 - over / (bot - top)); }
  const xL = LW, xM = W / 2, xR = W - RW - nodeW;
  const lay = list => { const sh = list.reduce((a, e) => a + Math.max(1.5, e.hv * k), 0) + gap * (list.length - 1); let y = top + ((bot - top) - sh) / 2;
    return list.map(e => { const h = Math.max(1.5, e.hv * k), o = {...e, y, h}; y += h + gap; return o; }); };
  // the waist: the bands meet a little narrower in the middle than at the sides -- just enough for the period and the total above it
  const WAIST = Math.max(0.6, Math.min(0.88, ((bot - top) - 2 * ((narrow ? 44 : 38) - top)) / (F.total * k))), L = lay(L0), R = lay(R0), mH = F.total * k * WAIST, mTop = top + ((bot - top) - mH) / 2;
  // the colours as values (the bands mix them): each band runs from its own colour to the colour of everything that came in
  // (the sources mixed by amount) where all bands meet in the middle -- one colour flows into the next, nothing turns transparent
  const css = getComputedStyle(document.documentElement), rgb = v => { const h = css.getPropertyValue(v).trim().replace('#', ''); const f = h.length === 3 ? h.split('').map(c => c + c).join('') : h;
    return /^[0-9a-f]{6}$/i.test(f) ? [0, 2, 4].map(i => parseInt(f.slice(i, i + 2), 16)) : [142, 142, 147]; };
  const COLV = {ein: rgb('--pos'), aus: rgb('--neg'), inv: rgb('--cf-inv'), fin: rgb('--cf-fin'), unk: rgb('--cf-unk'), tot: rgb('--cf-unk')};
  const hex = c => '#' + c.map(x => x.toString(16).padStart(2, '0')).join(''), COL = Object.fromEntries(Object.entries(COLV).map(([k, v]) => [k, hex(v)]));
  const band = (x0, y0a, y0b, x1, y1a, y1b) => { const c = (x0 + x1) / 2;
    return `M${x0.toFixed(1)},${y0a.toFixed(1)}C${c.toFixed(1)},${y0a.toFixed(1)} ${c.toFixed(1)},${y1a.toFixed(1)} ${x1.toFixed(1)},${y1a.toFixed(1)}L${x1.toFixed(1)},${y1b.toFixed(1)}C${c.toFixed(1)},${y1b.toFixed(1)} ${c.toFixed(1)},${y0b.toFixed(1)} ${x0.toFixed(1)},${y0b.toFixed(1)}Z`; };
  // narrow: the bands rise steeply -- they run flat for a short stretch in the middle, where the period and the total stand
  const full = F.span + ' · ' + spanText(F.n), spanTxt = full.length * 5.8 <= (xR - xL - nodeW) * 0.66 ? full : spanText(F.n);          // the period and its length (no room: the length -- the period stands above the charts)
  const NECK = narrow ? Math.min((xM - xL - nodeW) * 0.4, Math.max(spanTxt.length, 9) * 2.9 + 4) : 0;
  const neck = (xa, xb, ya, yb) => NECK ? `M${xa.toFixed(1)},${ya.toFixed(1)}L${xb.toFixed(1)},${ya.toFixed(1)}L${xb.toFixed(1)},${yb.toFixed(1)}L${xa.toFixed(1)},${yb.toFixed(1)}Z` : '';
  let defs = '', g = '', mY = mTop, shares = '';          // the shares drawn last: no later band covers them
  // the bands opaque, their colours softened towards the background: where they meet there is no seam
  const BG = rgb('--head'), soft = c => { const v = /^#([0-9a-f]{6})$/i.test(c) ? [0, 2, 4].map(i => parseInt(c.slice(1 + i, 3 + i), 16)) : [142, 142, 147]; return hex(v.map((x, i) => Math.round(x * 0.62 + BG[i] * 0.38))); };
  const sc = e => soft(COL[e.act] || COL.unk);
  // where all bands meet they fade out (the mix of all, mostly background -- opaque, so layers never show as lines): each band keeps
  // its own colour for most of the way and fades only close to the middle; the same colour for all there, so no seam
  const rgbOf = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
  const midC = (() => { const w = L.reduce((a, e) => a + e.v, 0) || 1, m = [0, 1, 2].map(c => L.reduce((a, e) => a + rgbOf(sc(e))[c] * e.v, 0) / w), gr = BG;
    return hex(m.map((x, c) => Math.round(x * 0.4 + gr[c] * 0.6))); })();
  let gi = 0;
  const grad = (e, left) => { const id = 'cffl' + (gi++), own = sc(e);
    defs += `<linearGradient id="${id}" x1="0" x2="1" y1="0" y2="0">${left ? `<stop offset="0.7" stop-color="${own}"/><stop offset="1" stop-color="${midC}"/>` : `<stop offset="0" stop-color="${midC}"/><stop offset="0.3" stop-color="${own}"/>`}</linearGradient>`; return id; };
  const share = (e, x, y, anchor) => e.h >= 15 && e.v / F.total >= 0.05 ? `<text class="cf-fl-p" x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="${anchor}">${cfPct(e.v, F.total)} %</text>` : '';
  // a click: an item with parts opens them; a part that has none closes its group again (on the band or its name)
  const tgt = e => e.more ? ` data-fl="${esc(e.key)}" tabindex="0" role="button" aria-expanded="false"` : e.parentKey ? ` data-fl="${esc(e.parentKey)}" tabindex="0" role="button" aria-expanded="true"` : '';
  const tcls = e => e.more ? ' more' : e.parentKey ? ' back' : '';
  // on hover (band or name): the exact amount, its share, the period before and the change, then its parts -- as in the ring
  const upG = act => act === 'ein' ? true : act === 'aus' ? false : null;          // income up: good, expenses up: bad, the rest neutral
  const chg = (v, p, g) => { const c = F.has ? cfChange(v, p, g !== false) : null; return c && g === null ? {...c, cls: ''} : c; };
  const kv = (a, b, cls) => `<span>${esc(a)}</span><b class="${cls || ''}">${b}</b>`;
  const tips = new Map(), tipOf = e => { if (tips.has(e.key)) return tips.get(e.key);
    const mix = e.key.endsWith('|~'), ch = chg(e.v, e.p, upG(e.act)), ks = (e.kids || []).slice().sort((a, b) => b.v - a.v);
    const shown = ks.length > 8 ? ks.slice(0, 7) : ks, rest = ks.slice(shown.length);
    const row = (label, v, p, act) => cfTipRow('none', label, cfEur(v), chg(v, p, upG(act)) || {cls: '', txt: ''});
    const i = cfTip(`<div class="cf-tip-h">${esc(e.label)}</div><div class="cf-tip-kv">${kv(t('betrag'), cfEur(e.v))}${kv(t('anteil'), cfPct(e.v, F.total) + ' %', 'pl')}`
      + (F.has ? kv(t('cf_vorperiode'), e.p != null ? cfEur(e.p) : '–', 'pl') + kv(t('cf_veraenderung'), ch ? ch.txt : '–', 'pl ' + (ch ? ch.cls : '')) : '') + `</div>`
      + (ks.length > 1 ? shown.map(k => row(k.label, k.v, k.p, mix ? k.act : e.act)).join('')
        + (rest.length ? row(t('cf_uebrige', rest.length), rest.reduce((a, k) => a + k.v, 0), cfRestP(rest, F.has), mix ? null : e.act) : '') : ''));
    tips.set(e.key, i); return i; };
  for (const e of L) { const h = e.hv * k, d = band(xL + nodeW, e.y, e.y + h, xM + 0.8 - NECK, mY, mY + h * WAIST + 0.7) + neck(xM - NECK, xM + 0.8, mY, mY + h * WAIST + 0.7);          // +0.7: under the next band, no hairline between them
    g += `<g class="cf-fl-g${tcls(e)}"${tgt(e)} data-cftip="${tipOf(e)}" aria-label="${esc(e.label + ': ' + cfEur(e.v))}"><path class="cf-fl-b" fill="url(#${grad(e, true)})" d="${d}"/><rect class="cf-fl-n ${e.act}" x="${xL}" y="${e.y.toFixed(1)}" width="${nodeW}" height="${e.h.toFixed(1)}" rx="2"/></g>`; shares += share(e, xL + nodeW + 6, e.y + e.h / 2, 'start'); mY += h * WAIST; }
  mY = mTop;
  for (const e of R) { const h = e.hv * k, d = neck(xM - 0.8, xM + NECK, mY, mY + h * WAIST + 0.7) + band(xM - 0.8 + NECK, mY, mY + h * WAIST + 0.7, xR, e.y, e.y + h);
    g += `<g class="cf-fl-g${tcls(e)}"${tgt(e)} data-cftip="${tipOf(e)}" aria-label="${esc(e.label + ': ' + cfEur(e.v))}"><path class="cf-fl-b" fill="url(#${grad(e, false)})" d="${d}"/><rect class="cf-fl-n ${e.act}" x="${xR}" y="${e.y.toFixed(1)}" width="${nodeW}" height="${e.h.toFixed(1)}" rx="2"/></g>`; shares += share(e, xR - 6, e.y + e.h / 2, 'end'); mY += h * WAIST; }
  g += shares;
  // the amount that ran through the period, quietly above the middle
  g += `<text class="cf-fl-mid" x="${xM.toFixed(1)}" y="${(mTop - 7).toFixed(1)}" text-anchor="middle">${esc(F0(F.total))} €</text>`
    + `<text class="cf-fl-mid cf-fl-span" x="${xM.toFixed(1)}" y="${(mTop - 21).toFixed(1)}" text-anchor="middle">${esc(spanTxt)}</text>`;          // the period, small above the total
  // names beside the bars: at their middle, pushed apart where bars are thin (a short line leads to the bar); opened parts carry
  // their item's name, and a row to close them again
  const labels = (list, left) => { let yPrev = -Infinity;
    const out = list.map((e, i) => { const head = !!e.parentKey && (i === 0 || list[i - 1].parentKey !== e.parentKey), gapY = LH + (head ? HEAD : 0);
      const y = Math.max(e.y + e.h / 2, yPrev + gapY, top + 6 + (head ? HEAD : 0)); yPrev = y; return {e, y, head, gapY}; });
    let over = out.length ? out[out.length - 1].y - (bot - 4) : 0; for (let i = out.length - 1; i >= 0 && over > 0; i--) { out[i].y -= over; over = i ? Math.max(0, out[i - 1].y - (out[i].y - out[i].gapY)) : 0; }
    const room = Math.floor((LW - 14) / 6.3);          // characters for the name and its amount (iPhone: the name alone)
    return out.map(({e, y, head}) => { const x = left ? xL - 6 : xR + nodeW + 6, disc = e.more ? '▸ ' : '', mid = e.y + e.h / 2;
      const a = amt(e.v), fit = tiny ? room : Math.max(4, room - a.length - 1), lab = disc + e.label, nm = lab.length > fit ? lab.slice(0, Math.max(3, fit - 1)) + '…' : lab;
      const close = head ? `<text class="cf-fl-up" data-fl="${esc(e.parentKey)}" x="${x.toFixed(1)}" y="${(y - (tiny ? 15 : 12)).toFixed(1)}" text-anchor="${left ? 'end' : 'start'}">▾ ${esc(e.parentLabel || '')}</text>` : '';
      return close + (Math.abs(y - mid) > 2 ? `<path class="cf-fl-lead" d="M${(left ? xL - 1 : xR + nodeW + 1).toFixed(1)},${mid.toFixed(1)}L${(left ? xL - 5 : xR + nodeW + 5).toFixed(1)},${y.toFixed(1)}"/>` : '')
        + `<g class="cf-fl-l${tcls(e)}"${e.more || e.parentKey ? ` data-fl="${esc(e.more ? e.key : e.parentKey)}"` : ''} data-cftip="${tipOf(e)}">`
        + (tiny ? `<text class="cf-fl-t" x="${x.toFixed(1)}" y="${(y - 2).toFixed(1)}" text-anchor="${left ? 'end' : 'start'}">${esc(nm)}</text><text class="cf-fl-t cf-fl-v cf-fl-v2" x="${x.toFixed(1)}" y="${(y + 10).toFixed(1)}" text-anchor="${left ? 'end' : 'start'}">${esc(a)}</text>`
          : `<text class="cf-fl-t" x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="${left ? 'end' : 'start'}">${esc(nm)} <tspan class="cf-fl-v">${esc(a)}</tspan></text>`) + `</g>`; }).join(''); };
  g += labels(L, true) + labels(R, false);
  el.innerHTML = `<svg class="cf-svg cf-fl" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(t('cf_herkunft_verwendung'))}"><defs>${defs}</defs>${g}</svg>`;
}

// the tooltip with colour keys: beside the row or column it belongs to, also on keyboard focus (on the iPhone: a tap)
function cfShowTip(el) {
  const box = $('#cf-tip'); if (!box || el.dataset.cftip == null) return;
  box.innerHTML = CF.tips[+el.dataset.cftip] || ''; box.classList.remove('hidden'); CF.tipFor = el;
  const host = box.parentElement.getBoundingClientRect(), r = el.getBoundingClientRect(), bw = box.offsetWidth, bh = box.offsetHeight;
  let left = r.left - host.left + r.width / 2 - bw / 2; left = Math.max(0, Math.min(left, host.width - bw));
  let top = r.top - host.top - bh - 8; if (top < 0) top = r.bottom - host.top + 8;
  // sources and uses: beside the chart (it can be taller than the window), at the height of the pointer and always in view --
  // where there is no room beside it, over its other half; a narrow screen: as everywhere (above or below the item)
  const fl = el.closest('#cf-flow svg');
  if (fl && host.width >= 600) { const a = fl.getBoundingClientRect(), recent = CF.pt && Date.now() - CF.pt.t < 400;
    const cy = recent ? CF.pt.y : r.top + r.height / 2, vt = Math.max(8, Math.min(innerHeight - bh - 8, cy - bh / 2));
    top = vt - host.top;
    if (host.right - a.right >= bw + 8) left = a.right - host.left + 8;
    else if (a.left - host.left >= bw + 8) left = a.left - host.left - bw - 8;
    else left = (r.left + r.width / 2 > a.left + a.width / 2) ? a.left - host.left + 4 : a.right - host.left - bw - 4; }
  const br = el.closest('#cf-bridge svg, #cf-wbridge svg');          // the bridges: right of the row's figures, beside the chart (where there is room)
  if (br) { const a = br.getBoundingClientRect(), x = a.right - host.left + 8;
    if (x + bw <= host.width) { left = x; top = Math.max(0, r.top - host.top + r.height / 2 - bh / 2); } }
  box.style.left = left + 'px'; box.style.top = top + 'px';
}
const monthEnd = m => `${m}-${String(new Date(+m.slice(0, 4), +m.slice(5), 0).getDate()).padStart(2, '0')}`;
// the transactions behind a cell of the heat map or a category of the ring, under „Umsätze & Belege“ (filter shown there)
// the transactions behind a figure, whatever it is (a category, unclear ones): in a side panel -- the cash flow stays; from there the page
function cfOpenTx(o, page = false) {
  const f = {entity: S.area || '', year: '', account: '', q: '', ohne_beleg: false, direction: o.direction || '', uncategorized_flag: !!o.none,
    kats: o.none ? null : o.kats, date_from: o.months[0] + '-01', date_to: monthEnd(o.months[o.months.length - 1]), title: o.title, est: !!o.est, ext: true,
    mitOhne: !!o.mitOhne, katsLabel: (o.kats || []).length > 1 ? o.katsLabel || '' : '', rChart: !!o.rChart, ids: o.ids || null,
    cfRows: o.cfRows || null, cfArea: o.cfRows ? S.area : null, cfMonths: o.cfRows ? o.months : null};
  if (page) { Object.assign(S.uf, f); S.sel.clear(); go('#transactions'); return; }
  const d = $('#drawer'), q = umsQuery(f); q.set('limit', '500');
  const key = 'cftx|' + (o.title || '') + '|' + q.toString();          // the same figure clicked again closes the panel
  if (drawerAgain(key)) return;
  // what it shows (docs/ui/drawer.md): the check against the balance sheet with its reasons, or the bookings behind a figure
  const head = `<button class="close icon">✕</button><h2>${esc(o.title || '')}</h2>`, ex = o.kopf ? 'data-ex="drawer.check"' : 'data-ex="drawer.tx"';
  const body = inner => `<div ${ex}>${o.kopf || ''}${inner}</div>`;
  d.innerHTML = head + body(o.cfRows && !o.cfRows.length ? '' : `<div class="muted small">${t('wird_geladen')}</div>`);
  d.classList.add('open'); $('.close', d).onclick = closeDrawer;
  if (o.cfRows && !o.cfRows.length) return;                 // nothing to fetch (a difference without single bookings behind it)
  api('/api/transactions?' + q.toString()).then(r => { if (DRW.key !== key) return;
    // a category's figure: its sum (all matches); bookings behind other rows can differ from the figure (a transfer, interest on a loan account): their number only
    d.innerHTML = head + body(`
      <div class="note">${o.kats ? tn('cf_tx_n', r.hits, F(r.sum)) : tn('cf_tx_anzahl', r.hits)}${f.est ? ' · ' + t('uf_ohne_geschaetzte') : ''} · <a href="#" id="cftx-page">${t('cf_tx_seite')}</a></div>
      <div class="wrap auto dr-wrap"><table class="plain small dr-tx"><colgroup><col class="c-d"><col><col class="c-a"></colgroup><tbody>`
      + r.transactions.map(u => `<tr><td>${FD(u.date)}</td><td>${esc(u.name)}<div class="muted">${esc(u.purpose)}</div></td><td class="num">${F(u.amount)}</td></tr>`).join('')
      + `</tbody></table></div>`);
    $('.close', d).onclick = closeDrawer;
    $('#cftx-page', d).onclick = e => { e.preventDefault(); closeDrawer(); cfOpenTx(o, true); };
  }).catch(e => { if (DRW.key === key) toast(e.message); });
}
// the bookings of a filter in the side panel (positions, recipients): their number and sum, a link to „Umsätze & Belege“
function txPanel(title, f) {
  const d = $('#drawer'), q = umsQuery(f); q.set('limit', '500');
  const key = 'tx|' + title + '|' + q.toString(); if (drawerAgain(key)) return;
  const head = `<button class="close icon">✕</button><h2>${esc(title)}</h2>`;
  d.innerHTML = head + `<div class="muted small">${t('wird_geladen')}</div>`; d.classList.add('open'); $('.close', d).onclick = closeDrawer;
  api('/api/transactions?' + q.toString()).then(r => { if (DRW.key !== key) return;
    d.innerHTML = head + `<div data-ex="drawer.tx"><div class="note">${tn('cf_tx_n', r.hits, F(r.sum))} · <a href="#" id="tx-page">${t('cf_tx_seite')}</a></div>`
      + `<div class="wrap auto dr-wrap"><table class="plain small dr-tx"><colgroup><col class="c-d"><col><col class="c-a"></colgroup><tbody>`
      + r.transactions.map(u => `<tr><td>${FD(u.date)}</td><td>${esc(u.name)}<div class="muted">${esc(u.purpose)}</div></td><td class="num">${F(u.amount)}</td></tr>`).join('') + `</tbody></table></div></div>`;
    $('.close', d).onclick = closeDrawer;
    $('#tx-page', d).onclick = e => { e.preventDefault(); closeDrawer(); Object.assign(S.uf, {entity: '', year: '', account: '', q: '', ohne_beleg: false, direction: '', uncategorized_flag: false,
      kats: null, date_from: '', date_to: '', ids: null, cfRows: null}, f, {ext: true, title}); S.sel.clear(); go('#transactions'); };
  }).catch(e => { if (DRW.key === key) toast(e.message); });
}
// the first day of the last twelve months, as the service counts them (on 29 February: from 1 March a year before)
const yearAgo = () => { const n = new Date(), d = new Date(n.getFullYear() - 1, n.getMonth(), (n.getMonth() === 1 && n.getDate() === 29 ? 28 : n.getDate()) + 1); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
function bindCfCharts(main) {
  if (CF.ro) { CF.ro.disconnect(); CF.ro = null; }
  const wrap = $('.cf-charts', main); if (!wrap) return;
  const draw = () => { cfDrawBridge('liq'); cfDrawBridge('nw'); cfDrawMonths(); cfDrawPie(); cfDrawHeat(); cfDrawFlow(); };
  draw();
  if (CF.focusAfter) { const f = $('#' + CF.focusAfter, main); CF.focusAfter = null; if (f) f.focus({preventScroll: true}); }          // after choosing a month: back on its button
  const hide = () => { const b = $('#cf-tip'); if (b) b.classList.add('hidden'); };
  for (const [ev, fn] of [['pointerover', e => { CF.pt = {x: e.clientX, y: e.clientY, t: Date.now()}; const el = e.target.closest('[data-cftip]'); if (el) cfShowTip(el); }], ['focusin', e => { const el = e.target.closest('[data-cftip]'); if (el) cfShowTip(el); }],
    ['pointerout', e => { const el = e.target.closest('[data-cftip]'); if (el && !(e.relatedTarget && el.contains(e.relatedTarget))) hide(); }], ['focusout', hide]]) wrap.addEventListener(ev, fn);
  // the month under the pointer in the monthly chart: its column heading in the table lights up softly (the chosen end month keeps its mark)
  const colMark = k => { $$('.cf-tbl thead th.cf-hov', main).forEach(th => th.classList.remove('cf-hov')); if (k) $$(`.cf-tbl:not(.cf-names) thead th[data-key="${CSS.escape(k)}"]`, main).forEach(th => th.classList.add('cf-hov')); };
  for (const ev of ['pointerover', 'focusin']) wrap.addEventListener(ev, e => { const h = e.target.closest('#cf-months .cf-hit[data-k]'); colMark(h ? h.dataset.k : null); });
  wrap.addEventListener('pointerout', e => { if (!(e.relatedTarget && wrap.contains(e.relatedTarget))) colMark(null); });
  wrap.addEventListener('focusout', () => colMark(null));
  const pin = el => { const i = el ? +el.dataset.pie : -1, e = CF.pie && CF.pie.items[i];
    CF.pieSel = e && CF.pieSel !== e.label ? e.label : null; hide(); cfDrawPie();
    if (e && CF.pieSel) { const f = $(`#cf-pie .cf-pie-sl[data-pie="${i}"]`); if (f) f.focus({preventScroll: true}); } };
  const setRange = (v, b) => cfSetRange(v, b);
  // a month of the period: a small calendar of the year (‹ › other years), the months that have figures; plan months hatched
  const mpClose = () => { const p = $('#cf-mpick'); if (p) p.remove(); document.removeEventListener('pointerdown', CF.mpOut, true); CF.mpOut = null; };
  const mpOpen = (btn, year) => {
    mpClose();
    const D = B(), pick = cfPick(D), which = btn.id, v = $('#cf-von').dataset.m, b = $('#cf-bis').dataset.m, y = year || +btn.dataset.m.slice(0, 4);
    const y0 = +pick[0].slice(0, 4), y1 = +pick[pick.length - 1].slice(0, 4);
    const cell = k => { const m = `${y}-${String(k + 1).padStart(2, '0')}`, ok = pick.includes(m), on = m === btn.dataset.m, inR = m >= v && m <= b;
      return `<button data-pm="${m}" class="${on ? 'on' : inR ? 'in' : ''}${ok && cfIsOpen(D, m) ? ' open' : ''}"${ok ? '' : ' disabled'} aria-pressed="${on}" aria-label="${esc(MLL(m))}">${esc(MONATE[k])}</button>`; };
    const box = document.createElement('div'); box.id = 'cf-mpick'; box.className = 'cf-mpick'; box.setAttribute('role', 'dialog'); box.dataset.for = which;
    box.innerHTML = `<div class="cf-mp-h"><button class="icon" data-py="${y - 1}" ${y <= y0 ? 'disabled' : ''} aria-label="${esc(String(y - 1))}">‹</button><b>${y}</b><button class="icon" data-py="${y + 1}" ${y >= y1 ? 'disabled' : ''} aria-label="${esc(String(y + 1))}">›</button></div>`
      + `<div class="cf-mp-g">${[...Array(12).keys()].map(cell).join('')}</div>`;
    wrap.appendChild(box);
    const host = wrap.getBoundingClientRect(), r = btn.getBoundingClientRect();
    box.style.left = Math.max(0, Math.min(r.left - host.left, host.width - box.offsetWidth)) + 'px'; box.style.top = (r.bottom - host.top + 6) + 'px';
    const f = $('button.on', box) || $('button[data-pm]:not([disabled])', box); if (f) f.focus({preventScroll: true});
    CF.mpOut = e => { if (!e.target.closest('#cf-mpick, .cf-mbtn')) mpClose(); }; document.addEventListener('pointerdown', CF.mpOut, true);
  };
  wrap.addEventListener('click', e => {
    const mbn = e.target.closest('.cf-mbtn'); if (mbn) { e.stopPropagation(); const p = $('#cf-mpick'); if (p && p.dataset.for === mbn.id) mpClose(); else mpOpen(mbn); return; }
    const py = e.target.closest('#cf-mpick [data-py]'); if (py) { e.stopPropagation(); mpOpen($('#' + $('#cf-mpick').dataset.for), +py.dataset.py); return; }
    const pm = e.target.closest('#cf-mpick [data-pm]'); if (pm) { e.stopPropagation(); const which = $('#cf-mpick').dataset.for, m = pm.dataset.pm;
      let v = $('#cf-von').dataset.m, b = $('#cf-bis').dataset.m; if (which === 'cf-von') { v = m; if (v > b) b = v; } else { b = m; if (b < v) v = b; }
      mpClose(); CF.focusAfter = which; setRange(v, b); }
  }, true);
  wrap.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#cf-mpick')) { const f = $('#' + $('#cf-mpick').dataset.for); mpClose(); if (f) f.focus(); } });
  // the monthly chart: two fingers sideways move the period a month at a time (all charts, and the table follows)
  const mEl = $('#cf-months', main);
  const cfStep = d => { const D = B(), ms = cfPick(D), [cur] = cfMonths(D, S.cfZeit), i0 = ms.indexOf(cur[0]) + d, i1 = ms.indexOf(cur[cur.length - 1]) + d;
    if (i0 < 0 || i1 >= ms.length) return false;
    CF.wheelBusy = true; hide(); Promise.resolve(cfSetRange(ms[i0], ms[i1])).then(() => setTimeout(() => { CF.wheelBusy = false; }, 80)); return true; };
  const zSet = (p, f) => { const Z = S.cfMoZ || (S.cfMoZ = {}); if (f == null || Math.abs(f - 1) < 0.02) delete Z[p]; else Z[p] = Math.max(0.05, Math.min(4, f)); hide(); cfDrawMonths(); };
  if (mEl) mEl.addEventListener('pointerdown', e => {          // a scale: drag down = wider range, up = closer; a click: automatic again
    const ax = e.target.closest('.cf-yax'); if (!ax || e.button !== 0) return;
    e.preventDefault(); const p = ax.dataset.p, f0 = (S.cfMoZ || {})[p] || 1, y0 = e.clientY; let moved = false;
    const move = ev => { const dy = ev.clientY - y0; if (Math.abs(dy) > 3) moved = true; if (moved) zSet(p, f0 * Math.exp(dy * 0.01)); };
    const up = () => { document.removeEventListener('pointermove', move); document.removeEventListener('pointerup', up); document.body.classList.remove('cf-ydrag'); if (!moved) zSet(p, null); };
    document.addEventListener('pointermove', move); document.addEventListener('pointerup', up); document.body.classList.add('cf-ydrag');
  });
  if (mEl) mEl.addEventListener('wheel', e => {
    const ya = e.target.closest('.cf-yax'); if (ya) { e.preventDefault(); const p = ya.dataset.p; zSet(p, ((S.cfMoZ || {})[p] || 1) * Math.exp(e.deltaY * 0.004)); return; }
    // over the axis also up and down (a mouse wheel); elsewhere up and down scrolls the page
    let dx = e.deltaX; if (Math.abs(dx) <= Math.abs(e.deltaY)) { if (!e.target.closest('.cf-xaxis')) return; dx = e.deltaY; }
    e.preventDefault(); if (CF.wheelBusy) return;
    CF.wheelAcc = (CF.wheelAcc || 0) + dx; if (Math.abs(CF.wheelAcc) < 40) return;
    const d = CF.wheelAcc > 0 ? 1 : -1; CF.wheelAcc = 0; cfStep(d);
  }, {passive: false});
  // the total: only a band under the pointer brings the others back -- a veil over the rest (no layers, so no seam), the band lifted above it
  const flEl = $('#cf-flow', main);
  if (flEl) {
    const off = () => { const h = CF.flHov; if (!h) return; CF.flHov = null; h.veil.remove(); if (h.next && h.next.parentNode === h.g.parentNode) h.g.parentNode.insertBefore(h.g, h.next); };
    flEl.addEventListener('pointerover', e => { const g = e.target.closest('.cf-fl-g'); if (!g || (CF.flHov && CF.flHov.g === g)) return; off();
      const gs = flEl.querySelectorAll('.cf-fl-g'), veil = document.createElementNS('http://www.w3.org/2000/svg', 'rect'), next = g.nextSibling;
      veil.setAttribute('class', 'cf-fl-veil'); veil.setAttribute('width', '100%'); veil.setAttribute('height', '100%');
      gs[gs.length - 1].after(veil); veil.after(g); CF.flHov = {g, next, veil}; });
    flEl.addEventListener('pointerout', e => { if (CF.flHov && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('.cf-fl-g') === CF.flHov.g)) off(); });
  }
  // drag the axis: a month per column moved (pulled to the left: later months)
  if (mEl) mEl.addEventListener('pointerdown', e => {
    const ax = e.target.closest('.cf-xaxis'); if (!ax || e.button !== 0) return;
    e.preventDefault(); const slot = Math.max(8, +ax.dataset.slot || 30), x0 = e.clientX; let done = 0;
    const move = ev => { const want = Math.trunc((x0 - ev.clientX) / slot); if (want === done || CF.wheelBusy) return; const d = want > done ? 1 : -1; if (cfStep(d)) done += d; else done = want; };
    const up = () => { document.removeEventListener('pointermove', move); document.removeEventListener('pointerup', up); document.body.classList.remove('cf-dragging'); };
    document.addEventListener('pointermove', move); document.addEventListener('pointerup', up); document.body.classList.add('cf-dragging');
  });
  // the bridges: drag across one to zoom into that range of amounts; the button above or a click on the axis shows it whole again
  for (const [which, P] of Object.entries(BRIDGES)) {
    const brEl = $('#' + P.el, main); if (!brEl) continue;
    let dr = null;
    const G = () => CF['br_' + which], redraw = () => cfDrawBridge(which);
    const xIn = e => { const r = brEl.getBoundingClientRect(); return Math.max(G().L, Math.min(G().R, e.clientX - r.left)); };
    brEl.addEventListener('pointerdown', e => { if (e.button > 0 || !G()) return; const r = brEl.getBoundingClientRect(), x = e.clientX - r.left;
      if (x < G().L || x > G().R) return; if (e.pointerType === 'mouse') e.preventDefault();          // no text selected while dragging
      dr = {x0: x, x1: x, id: e.pointerId, moved: false}; });
    brEl.addEventListener('pointermove', e => { if (!dr) return; dr.x1 = xIn(e);
      if (!dr.moved && Math.abs(dr.x1 - dr.x0) > 6) { dr.moved = true; try { brEl.setPointerCapture(dr.id); } catch (x) {} hide(); }
      if (dr.moved) { const svg = $('svg', brEl); if (!svg) return; let sel = $('.cf-br-sel', svg);
        if (!sel) { sel = document.createElementNS('http://www.w3.org/2000/svg', 'rect'); sel.setAttribute('class', 'cf-br-sel'); svg.appendChild(sel); }
        sel.setAttribute('x', Math.min(dr.x0, dr.x1)); sel.setAttribute('width', Math.abs(dr.x1 - dr.x0)); sel.setAttribute('y', G().top); sel.setAttribute('height', G().rowsH); } });
    const end = () => { if (!dr) return; const d = dr; dr = null;
      if (d.moved && Math.abs(d.x1 - d.x0) > 12) { const v = x => G().lo + (x - G().L) / (G().R - G().L) * (G().hi - G().lo);
        S[P.zoom] = [v(Math.min(d.x0, d.x1)), v(Math.max(d.x0, d.x1))]; CF.brDragged = true; setTimeout(() => { CF.brDragged = false; }, 0); redraw(); }
      else if (d.moved) redraw(); };
    brEl.addEventListener('pointerup', end); brEl.addEventListener('pointercancel', () => { dr = null; redraw(); });
  }
  // touch: the first tap on a month or a cell shows its numbers, the second acts
  wrap.addEventListener('pointerdown', e => { CF.touch = e.pointerType === 'touch'; }, true);
  const act = (el, key) => { if (CF.touch && CF.armed !== key) { CF.armed = key; return false; } CF.armed = null; return true; };
  wrap.addEventListener('click', e => {
    if (e.target.closest('#cf-order-reset')) { try { LS.del(CF_ORDER_KEY); } catch (x) {} hide(); route(); toast(t('ansicht_zurueckgesetzt')); return; }
    const mvb = e.target.closest('[data-cfmv]');
    if (mvb) { const o = cfOrder(), id = mvb.dataset.cfmv, k = o.indexOf(id), n = k + +mvb.dataset.d; if (k < 0 || n < 0 || n >= o.length) return;
      [o[k], o[n]] = [o[n], o[k]]; try { LS.set(CF_ORDER_KEY, JSON.stringify(o)); } catch (x) {}
      hide(); Promise.resolve(route()).then(() => { const c = $(`.cf-card[data-cfid="${id}"]`); if (c) c.scrollIntoView({block: 'nearest', behavior: 'smooth'}); }); return; }
    const bl = e.target.closest('[data-bal]'); if (bl && !CF.brDragged) { cfToBalance(bl.dataset.bal); return; }
    const fl = e.target.closest('#cf-flow [data-fl]');
    if (fl) { const o = CF.flowOpen || (CF.flowOpen = {}); o[fl.dataset.fl] = !o[fl.dataset.fl]; cfDrawFlow(); return; }
    // anywhere beside the bands and names (the total, the period, the empty card): everything open -- or, when anything is, all closed
    if (e.target.closest('.cf-card[data-cfid="flow"]') && !e.target.closest('button, a, input, .hq, .cf-fl-g, .cf-fl-l, .cf-fl-up')) {
      const o = CF.flowOpen || {}, all = CF.flowAll || []; if (!all.length) return;
      CF.flowOpen = all.some(x => o[x]) ? {} : Object.fromEntries(all.map(x => [x, true])); hide(); cfDrawFlow(); return; }
    const brW = Object.keys(BRIDGES).find(k => e.target.closest(`#${BRIDGES[k].reset}, #${BRIDGES[k].el} .cf-br-axis`));
    if (brW) { S[BRIDGES[brW].zoom] = null; CF.brDragged = false; hide(); cfDrawBridge(brW); return; }
    if (CF.brDragged) { CF.brDragged = false; return; }                     // the end of a drag is no click
    const br = e.target.closest('#cf-bridge .cf-br-row[data-br], #cf-wbridge .cf-br-row[data-br]');
    if (br) { const which = br.closest('#cf-wbridge') ? 'nw' : 'liq', P = BRIDGES[which], id = br.dataset.br, o = P.open(); o[id] = !o[id]; hide(); cfDrawBridge(which); cfDrawFlow();          // beside it the total follows its height
      const f = $(`#${P.el} .cf-br-row[data-br="${CSS.escape(id)}"]`); if (f && e.detail === 0) f.focus({preventScroll: true}); return; }
    const sh = e.target.closest('.cf-shift');
    if (sh) { const D = B(), ms = cfPick(D), [cur] = cfMonths(D, S.cfZeit), d = +sh.dataset.shift, i0 = ms.indexOf(cur[0]) + d, i1 = ms.indexOf(cur[cur.length - 1]) + d;
      if (i0 >= 0 && i1 < ms.length) setRange(ms[i0], ms[i1]); return; }
    const hc = e.target.closest('#cf-heat .cf-heat-c[data-hr], #cf-heat .cf-heat-n[data-hr]');
    if (hc && hc.dataset.hm === '*') { const r = CF.heat && CF.heat.rows[+hc.dataset.hr], [cur] = cfMonths(B(), S.cfZeit); if (!r) return; hide();
      cfOpenTx(r.total ? {kats: [...r.paths], rChart: true, mitOhne: r.est || CF.heat.rows.some(x => x.none), direction: S.cfPieArt === 'ein' ? 'ein' : 'aus', katsLabel: r.label, months: cur, title: r.label + ' · ' + cfSpanLabel(cur)}
        : {kats: [...r.paths], est: r.est, none: r.none, months: cur, title: r.label + ' · ' + cfSpanLabel(cur)}); return; }
    if (hc) { const r = CF.heat && CF.heat.rows[+hc.dataset.hr]; if (r && act(hc, 'h' + hc.dataset.hr + hc.dataset.hm)) { hide();
      // the total: all categories of the section together (one chip) and the transactions without a category, in its direction
      cfOpenTx(r.total ? {kats: [...r.paths], rChart: true, mitOhne: r.est || CF.heat.rows.some(x => x.none), direction: S.cfPieArt === 'ein' ? 'ein' : 'aus', katsLabel: r.label, months: CF.heat.months(hc.dataset.hm), title: r.label + ' · ' + CF.heat.lab(hc.dataset.hm)}
        : {kats: [...r.paths], est: r.est, none: r.none, months: CF.heat.months(hc.dataset.hm), title: r.label + ' · ' + CF.heat.lab(hc.dataset.hm)}); } return; }
    const pl = e.target.closest('#cf-pie .cf-pie-lab[data-kats]');
    if (pl && CF.pie) { hide(); const [cur] = cfMonths(B(), S.cfZeit); cfOpenTx({kats: JSON.parse(pl.dataset.kats), est: pl.dataset.est === '1', months: cur, title: pl.dataset.name + ' · ' + CF.pie.span}); return; }
    const hmb = e.target.closest('#cf-heat-mode button');
    if (hmb) { if ((cfHeatChg() ? 'chg' : 'abs') === hmb.dataset.hmode) return; S.cfHeatMode = hmb.dataset.hmode; hide();
      keepPlace(hmb, () => `#cf-heat-mode button[data-hmode="${hmb.dataset.hmode}"]`, () => { const hcard = $('#cf-heat-card'); if (hcard) { hcard.outerHTML = cfHeatCard(!$('#cf-pie-card')); cfDrawHeat(); } }); return; }
    const sw = e.target.closest('#cf-pie-art button');
    if (sw) { if (sw.dataset.a === S.cfPieArt) return; S.cfPieArt = sw.dataset.a; CF.pieSel = null; hide();
      // the switch stays where it is: the cards are drawn anew (for a moment shorter), then the page is moved back by what it moved
      // the card keeps at least its height: at the end of the page a shorter one would pull the page (and the switch) up
      const duo = sw.closest('.cf-duo'), h0 = duo ? duo.offsetHeight : 0;
      keepPlace(sw, () => `#cf-pie-art button[data-a="${sw.dataset.a}"]`, () => {
        const D = B(), [cur, prev] = cfMonths(D, S.cfZeit), old = $('#cf-pie-card'); if (old) { old.outerHTML = cfPie(D, cur, prev); cfDrawPie(); }
        const hc = $('#cf-heat-card'); if (hc) { hc.outerHTML = cfHeatCard(!$('#cf-pie-card')); cfDrawHeat(); }
        if (duo && duo.offsetHeight < h0) duo.style.minHeight = h0 + 'px'; }); return; }
    if (!e.target.closest('#cf-pie')) return; pin(e.target.closest('#cf-pie [data-pie]')); });
  wrap.addEventListener('keydown', e => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.closest('#cf-heat .cf-heat-c[data-hr], #cf-heat .cf-heat-n[data-hr], #cf-pie .cf-pie-lab[data-kats], #cf-bridge .cf-br-row[data-br], #cf-wbridge .cf-br-row[data-br], #cf-flow [data-fl], [data-bal]')) { e.preventDefault(); CF.touch = false; e.target.dispatchEvent(new MouseEvent('click', {bubbles: true})); return; }
    if (!e.target.closest('#cf-pie')) return;
    if (e.key === 'Escape' && CF.pieSel) { e.preventDefault(); CF.pieSel = null; hide(); cfDrawPie(); }
    else if ((e.key === 'Enter' || e.key === ' ') && e.target.closest('[data-pie]')) { e.preventDefault(); pin(e.target.closest('[data-pie]')); } });
  let last = wrap.clientWidth;
  CF.ro = new ResizeObserver(onResizeFrame(() => { if (PRINT.on) return; const w = $('.cf-charts'); if (w && Math.abs(w.clientWidth - last) > 2) { last = w.clientWidth; draw(); } }));
  CF.ro.observe(wrap);
}

// ---------------------------------------------------------------- Synchronisierung
async function vSync() {
  const st = S.STATUS, m = st.moneymoney || {}, z = st.service || {}, l = st.last_run, r = await api('/api/sync');
  const stale = r.accounts.filter(k => k.kind === 'online' && k.back);          // only what needs a look: accounts MoneyMoney has not refreshed for a while
  const tage = t => r.newest && t ? Math.floor((new Date(r.newest.replace(' ', 'T')) - new Date(t.replace(' ', 'T'))) / 864e5) : null;
  const card = (t, v, d) => `<div class="card"><div class="l">${t}</div><div class="v s">${v}</div><div class="d">${d}</div></div>`;
  let h = `<div class="cards">
    ${card('MoneyMoney', `<span class="dot ${mmState(st).cls}"></span>${mmState(st).text}`, m.running ? (m.locked ? t('zum_lesen_in_moneymoney_entsperren') : t('kontor_kann_lesen')) : t('kontor_rechnet_mit_dem_zuletzt'))}
    ${card(t('banken_moneymoney'), r.newest ? esc(fmtZeit(r.newest)) : '–', t('neuester_bankabruf_in_moneymoney_den'))}
    ${card(t('moneymoney_kontor'), r.read_at ? esc(fmtZeit(r.read_at)) : '–', (z.automatic ? t('automatisch_alle') + z.interval_minutes + t('minuten_wenn_moneymoney_laeuft_und') : t('automatischer_abgleich_ist_aus')) + '.')}
    ${hasRules() ? card(t('regeln_zuletzt_angewendet'), l ? esc(fmtZeit(l.time)) : '–', `${t('nur_wenn_sich_in_moneymoney')} <a href="#bookings">${t('nav_auto_buchungen')}</a>`) : ''}
  </div>
  <div class="toolbar"><button id="sync-now" ${OFFLINE.mode ? 'disabled' : ''}>${t('jetzt_synchronisieren')}</button><button id="sync-full" class="secondary" ${OFFLINE.mode ? 'disabled' : ''}>${t('alles_neu_lesen')}</button>${hq('sync_knoepfe')}<span class="sp"></span><a class="small" href="#log">${t('protokoll')}</a></div>
  <div class="small muted sync-full-info">${t('voll_lesen_info', r.full_read && r.full_read.last ? esc(fmtZeit(r.full_read.last)) : '–', (r.full_read || {}).days || 30)}</div>`;
  if (stale.length) h += `<div class="banner">${t('0_mehr_als_einen_tag', stale.length === 1 ? t('1_konto_liegt') : stale.length + t('konten_liegen'), esc(stale.map(k => { const d = tage(k.time); return d ? `${k.name} (${d} ${d === 1 ? t('tag') : t('tage')})` : k.name; }).join(', ')))}</div>`;
  if (m.problem_text) h += `<div class="banner err">${t('moneymoney_lief_am_0_kontor', esc(fmtZeit(m.problem_text.time)), esc(m.problem_text.text))}</div>`;
  return h;
}

// ---------------------------------------------------------------- Buchungen (Laeufe)
// approval: your changes and the bookings left out, until the next check; calc = the list recalculated for them (a booking
// left out or changed moves every later balance, so the next value adjustment of that account takes up the difference)
const BOOK = {time: null, edits: {}, off: new Set(), runs: null, calc: null, waits: new Set(), extra: {}, editing: new Set(), seq: 0};
// the rows shown: the waiting list, new ones from the recalculation, each with the amount it books now
function bkRows(l) {
  const base = l.proposals || [], inBase = new Set(base.map(v => v.key)), calc = BOOK.calc ? new Map(BOOK.calc.map(r => [r.key, r])) : null;
  return base.concat(Object.values(BOOK.extra).filter(x => !inBase.has(x.key))).map(v => {
    const k = v.key || '', off = BOOK.off.has(k), e = BOOK.edits[k] || {}, cur = calc && !off ? calc.get(k) : null;
    const gone = !!(calc && k && !off && !cur), b = e.amount ?? (cur ? cur.amount : v.amount);
    return {v, k, off, e, gone, waits: gone && BOOK.waits.has(k), b, new: !inBase.has(k), adjusted: !!(cur && e.amount == null && inBase.has(k) && Math.abs(cur.amount - v.amount) >= 0.005)};
  });
}
// folded sections that stay open while the page is drawn again (e.g. "Not booked" while booking several again)
const KEEP_OPEN = new Set();
const keepOpen = k => KEEP_OPEN.has(k) ? ' open' : '';
document.addEventListener('toggle', e => { const d = e.target; if (d.matches && d.matches('details[data-keep]')) { if (d.open) KEEP_OPEN.add(d.dataset.keep); else KEEP_OPEN.delete(d.dataset.keep); } }, true);
// draw the page again with `sel` where it was on the screen (rows added above it do not push it away)
async function routeKeeping(sel) {
  const el = sel && $(sel, $('#main')), top = el ? el.getBoundingClientRect().top : null;
  await route();
  const main = $('#main');
  const fade = $('.fade', main); if (fade) fade.classList.remove('fade');          // in place: no fade-in (it moves the page)
  const now = sel && $(sel, main);
  if (!now || top == null) return;
  pageBy(now.getBoundingClientRect().top - top);
  const miss = now.getBoundingClientRect().top - top;          // the page ends below: room there, so it stays in place
  if (miss > 1) { main.style.paddingBottom = Math.ceil(miss) + 'px'; pageBy(miss); }
}
// "Book again" with approval: the list waiting planned again (only the accounts of the rules read), one after the other
const NB = {busy: false, again: false};
async function nbRefresh() {
  if (NB.busy) { NB.again = true; return; }
  NB.busy = true;
  try {
    let tries = 0;
    do {
      NB.again = false;
      try { await api('/api/bookings/refresh', {}); }
      catch (e) { if (tries++ > 60) { toast(e.message, 5000); break; } await new Promise(r => setTimeout(r, 1500)); NB.again = true; }    // a check is running: after it
    } while (NB.again);
    S.STATUS = await api('/api/status'); statusMini();
  } catch (e) { toast(e.message, 5000); }
  finally { NB.busy = false; routeKeeping('#nb-list'); }
}
// rules saved: the list under Auto bookings follows at once -- with approval planned again (only the accounts of the rules are
// read), booking fully automatically a sync books what is new
async function rulesFollowUp(after) {
  if (OFFLINE.mode) return;
  if (S.CFG.dry_run === false) { await syncNow(); if (after && S.tab === 'accounts' && S.sub === 'rules') after(); return; }
  try {
    const r = await api('/api/bookings/refresh', {});
    S.STATUS = await api('/api/status'); statusMini();
    if (after && S.tab === 'accounts' && S.sub === 'rules') after();
    if (r.status === 'ok' && r.wartend) toast(r.wartend === 1 ? t('aktualisiert_1') : t('aktualisiert_n', r.wartend), 4500);
  } catch (e) { /* the next sync plans it */ }
}
async function bkRecalc() {
  const l = (BOOK.runs || {}).last_run || {}, my = ++BOOK.seq;
  if (!l.dry_run) return;
  const edits = {}; Object.entries(BOOK.edits).forEach(([k, e]) => { if (e.amount != null || e.date) edits[k] = {amount: e.amount, date: e.date}; });
  if (!BOOK.off.size && !Object.keys(edits).length) { BOOK.calc = null; BOOK.extra = {}; return route(); }
  // everything left out: nothing is booked, nothing to work out (holding all would only bring recalculated ones, chosen by default)
  const keys = (l.proposals || []).map(v => v.key).concat(Object.keys(BOOK.extra)).filter(Boolean);
  if (keys.length && keys.every(k => BOOK.off.has(k))) { BOOK.calc = null; BOOK.extra = {}; return route(); }
  try {
    const r = await api('/api/bookings/plan', {hold: [...BOOK.off], changes: edits});
    if (my !== BOOK.seq) return;                    // a newer change is on its way
    const inBase = new Set((l.proposals || []).map(v => v.key));
    BOOK.calc = r.proposals || null; BOOK.waits = new Set(r.waiting || []);
    BOOK.extra = Object.fromEntries(Object.entries(BOOK.extra).filter(([k]) => BOOK.off.has(k)));
    (BOOK.calc || []).forEach(x => { if (!inBase.has(x.key)) BOOK.extra[x.key] = x; });
    route();
  } catch (e) { toast(e.message, 5000); }
}
// an account in the lists of bookings with its area below it, small and grey (account names repeat across areas)
const areaOfAcct = id => { const k = (S.KONTEN || []).find(x => x.uuid === id), a = k && ((S.CFG || {}).areas || []).find(b => String(b.id) === String(k.area_id)); return a ? a.name : ''; };
const acctCell = (name, id) => { const a = areaOfAcct(id); return esc(name) + (a ? `<div class="small muted">${esc(a)}</div>` : ''); };
function vBuchungen(runs) {
  BOOK.runs = runs;
  // Auto-Buchungen: what the auto rules would book (waiting for approval) and have booked; the rules themselves under Auto-Regeln
  const st = S.STATUS, l = runs.last_run, ask = S.CFG.dry_run !== false, local = !!st.local;
  const pending = l && l.dry_run && (l.proposals || []).length ? l.proposals.length : 0;
  const artL = {repayment: t('art_tilgung'), interest: t('art_zins'), value: t('art_wert'), mirror: t('art_spiegel')};
  let h = `<div class="toolbar">
    ${pending ? `<button id="run-live" class="ico" ${local ? '' : t('disabled_title_nur_am_mac')}>${ICON.check}<span>${t('jetzt_buchen')} (<span id="sel-n">${pending}</span>)</span></button>` : ''}
    ${ask ? `<button id="bk-refresh" class="secondary ico" title="${esc(t('freigabe_aktualisieren_tip'))}" ${OFFLINE.mode ? 'disabled' : ''}>${ICON.refresh}<span>${t('aktualisieren')}</span></button>` : ''}
    <span class="sp"></span><a class="small" href="#accounts/rules">${t('zu_den_regeln')}</a>
    <a class="mode-chip${ask ? '' : ' auto'}" href="#accounts/rules" title="${t(ask ? 'auto_buchen_aus' : 'auto_buchen_an')}">${ask ? ICON.hand : ICON.bolt}${t(ask ? 'modus_freigabe' : 'modus_automatisch')}</a>
  </div>`;
  if (l) {
    const head = pending ? `${t('wartet_freigabe')} <span class="x">${pending}</span>` : `${t('zuletzt_geprueft')} <span class="x">${esc(fmtZeit(l.time))} · ${l.written} ${t('gebucht')}</span>`;
    h += `<h2>${head}${l.error ? ' <span class="pill err">' + esc(l.error) + '</span>' : ''}</h2>`;
    if ((l.proposals || []).length) {
      const pick = pending && local, ed = pending;          // choose and change only while waiting; booking only at the Mac
      // a new list: what carries a note (a possible counterpart entered by hand) starts not chosen -- you tick it yourself
      // a new check with bookings still listed (the next sync): what you held back or changed stays as you left it
      // -- but one with a note it did not have before (now new, or another: "already booked by hand") starts not chosen again
      if (BOOK.time !== l.time) { const keys = new Set((l.proposals || []).map(v => v.key).filter(Boolean)), was = BOOK.notes || {};
        const notes = Object.fromEntries((l.proposals || []).filter(v => v.key).map(v => [v.key, v.note || '']));
        const noted = Object.keys(notes).filter(k => notes[k] && notes[k] !== was[k]);
        const off = new Set([...BOOK.off].filter(k => keys.has(k)).concat(noted)), edits = Object.fromEntries(Object.entries(BOOK.edits).filter(([k]) => keys.has(k)));
        Object.assign(BOOK, {time: l.time, notes, edits, off, calc: null, extra: {}, editing: new Set(), needCalc: off.size > 0 || Object.keys(edits).length > 0}); }
      const plain = txt => String(txt || '').replace(/\s*·?\s*#kontor-[a-z]+-[A-Za-z0-9-]+/g, '').trim();
      h += `<div class="wrap auto" data-ex="bookings.list"><table class="plain bk-table"><thead><tr>${pick ? `<th class="c"><input type="checkbox" id="bk-all" ${BOOK.off.size || bkRows(l).some(r => r.gone) ? '' : 'checked'} aria-label="${esc(t('alle'))}"></th>` : ''}<th>${t('datum')}</th><th>${t('konto_2')}</th><th>${t('art')}</th><th class="num">${t('betrag')}</th><th>${t('text')}</th>${ed ? '<th></th>' : ''}</tr></thead><tbody>`
        + bkRows(l).map(({v, k, off, e, gone, waits, b, new: neu, adjusted}) => {
          const d = e.date ?? v.date, z = e.purpose ?? plain(v.text), changed = Object.keys(e).length > 0, loan = v.kind === 'repayment' || v.kind === 'interest';
          const pills = (changed ? ` <span class="pill info">${t('geaendert')}</span>` : '') + (adjusted ? ` <span class="pill info" title="${esc(t('angepasst_tip'))}">${t('angepasst')}</span>` : '')
            + (neu ? ` <span class="pill info" title="${esc(t('neu_dazu_tip'))}">${t('neu_dazu')}</span>` : '')
            + (!ask && v.retroactive ? ` <span class="pill neutral" title="${esc(t('aelter_tip'))}">${t('aelter')}</span>` : '') + (v.note ? ` <span class="pill warn">${t('bk_pruefen')}</span>` : '') + (gone ? ` <span class="pill neutral" title="${esc(t(waits ? 'bk_wartet_tip' : 'entfaellt_tip'))}">${t(waits ? 'bk_wartet' : 'entfaellt')}</span>` : '');
          return `<tr data-key="${esc(k)}" class="${off || gone ? 'off' : ''}${gone ? ' gone' : ''}${BOOK.editing.has(k) ? ' editing' : ''}">${pick ? `<td class="c">${k ? `<input type="checkbox" class="bk-on" title="${esc(t('bk_on_tip'))}" ${off || gone ? '' : 'checked'}${gone ? ' disabled' : ''}>` : ''}</td>` : ''}`
            + `<td style="white-space:nowrap"><span class="${loan ? 'v' : ''}">${FD(d)}</span>${loan ? `<input type="date" class="bk-d e" value="${esc(d)}">` : ''}</td><td>${acctCell(v.account_name || v.account, v.account_id)}</td><td>${esc(artL[v.kind] || v.kind)}</td>`
            + `<td class="num ${b < 0 ? 'neg' : 'pos'}"><span class="${loan ? 'v' : ''}">${F(b)}</span>${loan ? `<input type="number" step="0.01" class="bk-b e" value="${b}">` : ''}</td>`
            + `<td data-ex="bookings.list.text"><span class="v">${esc(z)}</span><input type="text" class="bk-z e" value="${esc(z)}">${pills}<div class="small muted">${esc(v.rule || '')}${v.category ? ' · ' + esc(v.category) : ''}</div>${v.note ? `<div class="small bk-note">${esc(v.note)}</div>` : ''}</td>`
            + (ed ? `<td class="nowrap">${k ? (local ? `<button class="icon bk-edit" title="${esc(t('bearbeiten'))}" aria-label="${esc(t('bearbeiten'))}">${ICON.pencil}</button>` : '') + `<button class="icon bk-rej" title="${esc(t('verwerfen'))}" aria-label="${esc(t('verwerfen'))}">✕</button>` : ''}</td>` : '') + `</tr>`;
        }).join('') + '</tbody></table></div>';
      if (l.dry_run && l.proposals.some(v => !v.key)) h += `<div class="note">${t('einmal_sync_fuer_auswahl')}</div>`;
    } else h += `<div class="note" data-ex="bookings.list">${t('keine_buchungen_noetig')}</div>`;
    if (l.warnings && l.warnings.length) h += `<h3>${t('hinweise')}</h3><div data-ex="bookings.notes">` + l.warnings.map(x => `<div class="banner">${esc(x)}</div>`).join('') + '</div>';
    if (l.hints && l.hints.length) h += `<details class="calc" data-keep="bk-calc" data-ex="bookings.calc"${keepOpen('bk-calc')}><summary>${t('rechenwege')} (${l.hints.length})</summary>` + l.hints.map(x => `<div class="small muted">${esc(x)}</div>`).join('') + '</details>';
  }
  // not booked: the proposals you chose not to book (kept in the settings) -- "Propose again" takes one off the list
  const rej = runs.not_book || [];
  if (rej.length) h += `<details class="calc" id="nb-list" data-keep="bk-nb" data-ex="bookings.rejected"${keepOpen('bk-nb')}><summary>${t('nicht_gebucht_titel')} (${rej.length})</summary><div class="wrap auto"><table class="plain"><tbody>`
    + rej.map(v => `<tr><td style="white-space:nowrap">${FD(v.date)}</td><td>${acctCell(v.account || '', String(v.key || '').split('|')[0])}</td><td>${esc(artL[v.kind] || v.kind || '')}</td><td class="num">${v.amount != null ? F(v.amount) : ''}</td>`
      + `<td class="small">${esc(v.text || '')}<div class="small muted">${esc(v.rule || '')}</div></td>`
      + `<td><button class="secondary small re-book" data-key="${esc(v.key)}" title="${esc(t('wieder_vorschlagen_tip'))}">${t('wieder_vorschlagen')}</button></td></tr>`).join('') + '</tbody></table></div></details>';
  // what Kontor made in MoneyMoney: the bookings carrying its mark
  const ang = runs.created_at || [];
  h += `<h2>${t('angelegt_titel')} <span class="x">${ang.length}</span></h2>`
    + (ang.length ? `<div class="wrap auto" style="max-height:420px" data-ex="bookings.created"><table class="plain"><thead><tr><th>${t('datum')}</th><th>${t('konto_2')}</th><th>${t('art')}</th><th class="num">${t('betrag')}</th><th>${t('text')}</th><th>${t('markierung')}</th></tr></thead><tbody>`
      + ang.slice(0, 300).map(v => `<tr><td style="white-space:nowrap">${FD(v.date)}</td><td>${acctCell(v.account, v.account_id)}</td><td>${esc(artL[v.kind] || v.kind)}</td><td class="num ${v.amount < 0 ? 'neg' : 'pos'}">${F(v.amount)}</td><td class="small">${esc(v.purpose || v.counterparty)}</td><td class="small muted" style="white-space:nowrap">${esc(v.mark)}</td></tr>`).join('')
      + `</tbody></table></div>` : `<div class="muted small" data-ex="bookings.created">${t('keine_angelegt')}</div>`);
  // history: only the checks (when, how many proposed and booked, errors) -- the bookings themselves are listed above
  h += `<details class="calc" data-keep="bk-hist" data-ex="bookings.history"${keepOpen('bk-hist')}><summary>${t('verlauf_2')} (${(runs.history_source || []).length})</summary><div class="wrap auto"><table class="plain"><thead><tr><th>${t('zeit')}</th><th class="num">${t('vorschlaege')}</th><th class="num">${t('gebucht_2')}</th><th>${t('fehler_2')}</th></tr></thead><tbody>`
    + (runs.history_source || []).map(v => `<tr><td style="white-space:nowrap">${esc(fmtZeit(v.time))}</td><td class="num">${v.proposals ?? ''}</td><td class="num">${v.written}</td><td>${esc(v.error || '')}</td></tr>`).join('') + '</tbody></table></div></details>';
  return h;
}

// ---------------------------------------------------------------- Steuer
function vSteuer() {
  if (!S.DATA || !S.DATA.tax) return noData;
  const T = S.DATA.tax, years = T.years, ents = T.entities;
  if (!years.length || !ents.length) return `<div class="note">${t('keine_steuerdaten_keine_kategorisierte')}</div>`;
  if (!S.steuerJahr) S.steuerJahr = String(years[years.length - 1]);
  if (!S.steuerEnt || !ents.some(e => e.uuid === S.steuerEnt)) S.steuerEnt = (ents.find(e => e.uuid === S.area) || ents[0]).uuid;
  const ent = ents.find(e => e.uuid === S.steuerEnt) || ents[0];
  let h = `<div class="toolbar"><label>${t('jahr_2')} <select id="st-jahr">${years.map(y => `<option ${String(y) === S.steuerJahr ? 'selected' : ''}>${y}</option>`).join('')}</select></label>
    <label>${t('entitaet')} <select id="st-ent">${ents.map(e => `<option value="${esc(e.uuid)}" ${e.uuid === ent.uuid ? 'selected' : ''}>${esc(e.name)} (${e.kind === 'private' ? t('privat') : e.kind === 'company' ? t('gesellschaft') : esc(({gbr: 'GbR', gmbh: 'GmbH'})[e.kind] || String(e.kind || ''))}${e.share ? t('anteil_2') + FN(e.share * 100, 0) + ' %' : ''})</option>`).join('')}</select></label>
    <span class="sp"></span><button id="st-belege" class="secondary small">${t('belege_0_exportieren', esc(S.steuerJahr))}</button>${xlsxBtn('tax')}</div>`;
  const J = ent.years[S.steuerJahr]; if (!J) return h + `<div class="note">${t('keine_daten_fuer_dieses_jahr')}</div>`;
  const objs = Object.keys(J.properties_list);
  h += `<div class="cards" data-ex="tax.cards"><div class="card"><div class="l">${t('einnahmen_kategorisiert')}</div><div class="v">${F0(J.sum_income)} €</div></div><div class="card"><div class="l">${t('ausgaben_kategorisiert')}</div><div class="v">${F0(J.sum_expenses)} €</div></div><div class="card"><div class="l">${t('schuldzinsen')}</div><div class="v">${F0(Object.values(J.debt_interest).reduce((a, b) => a + b, 0))} €</div></div><div class="card"><div class="l">${t('ohne_kategorie')}</div><div class="v">${J.uncategorized_flag.count ? '<span class="pill warn">' + J.uncategorized_flag.count + ` ${t('buchungen')}</span>` : `<span class="pill ok">${t('keine')}</span>`}</div><div class="d">${F(J.uncategorized_flag.amount)} € – <a href="#transactions?uncategorized=1&year=${S.steuerJahr}&entity=${encodeURIComponent(ent.uuid)}">${t('kategorisieren')}</a></div></div></div>`;
  if (objs.length) {
    h += `<h2>${t('vermietung_je_objekt')} <span class="x">${t('kategorien_0_objekt_art', esc(T.rental_category))}</span></h2><div class="wrap auto" data-ex="tax.rental"><table class="plain"><thead><tr><th>${t('position')}</th>${objs.map(o => `<th class="num">${esc(o)}</th>`).join('')}</tr></thead><tbody>`;
    const arten = [...new Set(objs.flatMap(o => Object.keys(J.properties_list[o].kinds)))];
    for (const a of arten) h += `<tr><td class="ind1">${esc(a)}</td>${objs.map(o => `<td class="num">${F(J.properties_list[o].kinds[a] ?? 0)}</td>`).join('')}</tr>`;
    h += `<tr class="total"><td>${t('einnahmen')}</td>${objs.map(o => `<td class="num pos">${F(J.properties_list[o].income_sum)}</td>`).join('')}</tr>`;
    h += `<tr class="total"><td>${t('werbungskosten_ohne_zinsen_afa')}</td>${objs.map(o => `<td class="num neg">${F(J.properties_list[o].deductible_costs)}</td>`).join('')}</tr>`;
    const loans = [...new Set(objs.flatMap(o => Object.keys(J.properties_list[o].debt_interest)))];
    for (const l of loans) h += `<tr><td class="ind1">${t('schuldzinsen_0', esc(l))}</td>${objs.map(o => `<td class="num">${F(J.properties_list[o].debt_interest[l] ?? 0)}</td>`).join('')}</tr>`;
    h += `<tr><td class="ind1">${t('afa_manuell')}</td>${objs.map(o => `<td class="num"><input type="number" step="0.01" class="depreciation" data-obj="${esc(o)}" value="${J.properties_list[o].depreciation_source === 'manual' ? J.properties_list[o].depreciation : ''}" placeholder="${J.properties_list[o].depreciation_source === 'calc' ? esc(F(J.properties_list[o].depreciation)) : ''}" style="width:110px"></td>`).join('')}</tr>`;
    h += `<tr class="total"><td>${t('ergebnis_ueberschuss_verlust')}</td>${objs.map(o => `<td class="num ${J.properties_list[o].result < 0 ? 'neg' : 'pos'}">${F(J.properties_list[o].result)}</td>`).join('')}</tr>`;
    if (ent.share) h += `<tr class="total"><td>${t('davon_anteil_0', (ent.share * 100).toFixed(0))}</td>${objs.map(o => `<td class="num">${F(J.properties_list[o].share_result)}</td>`).join('')}</tr>`;
    h += `</tbody></table></div><div class="actions"><button id="afa-save" class="small">${t('afa_speichern')}</button></div>`;
  } else h += `<div class="note">${t('keine_vermietungskategorien_fuer_diese', esc(T.rental_category))}</div>`;
  h += `<h2>${ent.kind === 'private' ? t('steuerpositionen') : t('oberkategorien')}</h2><div class="wrap auto" data-ex="tax.positions"><table class="plain"><thead><tr><th>${t('position')}</th><th>${t('kategorie')}</th><th class="num">${t('betrag')}</th><th class="num">${t('buchungen')}</th></tr></thead><tbody>`;
  for (const [pos, p] of Object.entries(J.positions)) {
    h += `<tr class="sub"><td colspan="2">${esc(pos)}</td><td class="num ${p.amount < 0 ? 'neg' : 'pos'}">${F(p.amount)}</td><td></td></tr>` + p.categories.map(k => `<tr><td></td><td>${esc(CP(k.path))}</td><td class="num">${F(k.amount)}</td><td class="num">${k.count}</td></tr>`).join('');
  }
  h += `</tbody></table></div><div class="note">${t('zusammenstellung_der_kategorisierten_b')}</div>`;
  return h;
}

// ---------------------------------------------------------------- Immobilien
const IM = {edit: null, res: null, tab: 'calc', kalk: null, timer: null};
const immoOf = id => (S.CFG.real_estate || []).find(x => String(x.id) === String(id));
const immoData = id => ((S.DATA && S.DATA.real_estate) || []).find(x => String(x.id) === String(id));
function vImmobilien(id) {
  if (id) return vImmobilie(id);
  const list = S.CFG.real_estate || [];
  let h = `<div class="toolbar"><span class="muted small">${t('kalkulationen_je_objekt_mehrere_szenar')}</span><span class="sp"></span><button id="im-new" class="small">${t('neues_objekt')}</button></div>`;
  if (!list.length) return h + `<div class="card" data-ex="properties.list"><div class="v s">${t('noch_keine_immobilie')}</div><div class="d">${t('lege_ein_objekt_an_und')}</div></div>`;
  h += '<div class="cards k3" data-ex="properties.list">' + list.map(im => { const d = immoData(im.id) || {}; const K = d.figures || {}; const j1 = (d.years || []).find(j => j.months === 12) || (d.years || [])[0];
    return `<div class="card clickable" data-im="${esc(im.id)}" style="cursor:pointer"><div class="l">${esc(BN(im.area) || im.area || '–')}${im.in_planning ? `<span class="tag">${t('in_planung')}</span>` : ''}</div><div class="v s">${esc(im.name)}</div>
      <div class="d">${K.purchase_price != null ? t('kaufpreis') + F0(K.purchase_price) + t('faktor') + FN(K.price_factor) + t('bruttorendite') + (K.gross_rental_yield != null ? FN(K.gross_rental_yield * 100) + ' %' : '–') : t('keine_kalkulation')}</div>
      <div class="d">${j1 ? t('cashflow') + j1.year + ': <b class="' + (j1.cashflow < 0 ? 'neg' : 'pos') + '">' + F0(j1.cashflow) + ` €</b> ${t('ek_rendite')} ` + (j1.return_on_equity != null ? FN(j1.return_on_equity * 100, 1) + ' %' : '–') + t('irr') + (K.irr != null ? FN(K.irr * 100, 1) + ' %' : '–') : ''}</div>
      ${(d.hints || []).length ? `<div class="d"><span class="pill warn">${tn('0_hinweise', d.hints.length)}</span></div>` : ''}</div>`; }).join('') + '</div>';
  return h;
}
function vImmobilie(id) {
  const im = immoOf(id); if (!im) return `<div class="banner err">${t('immobilie_nicht_gefunden')}</div>`;
  const d = immoData(id) || {};
  const kalks = im.calcs || [];
  if (!IM.kalk || !kalks.some(k => k.id === IM.kalk)) IM.kalk = (kalks.find(k => k.active) || kalks[0] || {}).id || null;
  const k = kalks.find(x => x.id === IM.kalk);
  if (!IM.edit || IM.editFor !== id + '|' + IM.kalk) { IM.edit = JSON.parse(JSON.stringify((k && k.inputs) || null)); IM.editFor = id + '|' + IM.kalk; IM.res = null; }
  const konten = S.KONTEN.filter(x => !x.group);
  const kats = S.KATS.filter(x => x.depth <= 1);
  let h = `<div class="toolbar"><a href="#properties" class="small">${t('alle_objekte')}</a><h2 style="margin:0">${esc(im.name)}</h2><span class="sp"></span>${xlsxBtn('property', `data-immo="${esc(im.id)}" data-kalk="${esc(IM.kalk || '')}"`)}<button id="im-del" class="danger small">${t('objekt_loeschen')}</button></div>
  <div class="card" style="margin-bottom:12px" data-ex="properties.object"><div class="immo-form">
    <label>${t('name')}</label><input type="text" id="im-name" value="${esc(im.name)}">
    <label>${t('bereich_0', hq('area'))}</label><select id="im-bereich">${Object.entries((S.DATA && S.DATA.area_names) || {}).map(([bid, n]) => `<option value="${esc(bid)}" ${im.area === bid ? 'selected' : ''}>${esc(n)}</option>`).join('') || (S.CFG.areas || []).map(b => `<option value="${esc(b.id)}" ${im.area === b.id ? 'selected' : ''}>${esc(b.name)}</option>`).join('')}</select>
    <label>${t('vermietungskategorie_0', hq('immo_kategorie'))}</label><input type="text" id="im-kat" list="im-kats" value="${esc(im.category || '')}" placeholder="${t('vermietung_objekt')}"><datalist id="im-kats">${kats.map(c => `<option value="${esc(c.raw)}">`).join('')}</datalist>
    <label>${t('objektkonto_wert_0', hq('immo_objektkonto'))}</label><select id="im-konto">${acctOptions(im.property_account, x => !x.group)}</select>
    <label>${t('in_planung_uebernehmen_0', hq('immo_planung'))}</label><label class="switch"><input type="checkbox" id="im-plan" ${im.in_planning ? 'checked' : ''}><i></i>${im.in_planning ? t('aktiv') : t('aus')}</label>
    <label>${t('notizen')}</label><input type="text" id="im-notiz" value="${esc(im.notes || '')}">
  </div><div class="actions"><button id="im-save-meta" class="small">${t('objekt_speichern')}</button></div></div>
  <div class="tabs">${[['calc', t('kalkulation')], ['years', t('jahrestabelle')], ['sollist', t('soll_ist')], ['documents', t('dokumente') + (im.documents || []).length + ')']].map(([t, l]) => `<button data-t="${t}" class="${IM.tab === t ? 'on' : ''}">${l}</button>`).join('')}</div>`;
  if (IM.tab === 'calc') h += vImmoKalk(im, k, konten);
  else if (IM.tab === 'years') h += vImmoJahre(d);
  else if (IM.tab === 'sollist') h += vImmoSollIst(d);
  else h += vImmoDokumente(im);
  return h;
}
function vImmoKalk(im, k, konten) {
  const kalks = im.calcs || [];
  let h = `<div class="row tight"><label>${t('szenario')} <select id="im-kalk">${kalks.map(x => `<option value="${esc(x.id)}" ${x.id === IM.kalk ? 'selected' : ''}>${esc(x.name)}${x.active ? ` (${t('aktiv')})` : ''}</option>`).join('')}${!kalks.length ? `<option value="">${t('keine_2')}</option>` : ''}</select></label>
    <button id="im-kalk-new" class="small secondary">${kalks.length ? t('als_neues_szenario_kopieren') : t('kalkulation_anlegen')}</button>${k && !k.active ? `<button id="im-kalk-aktiv" class="small secondary">${t('als_aktiv_setzen')}</button>` : ''}${k ? `<button id="im-kalk-del" class="small danger">${t('szenario_loeschen')}</button>` : ''}
    <span class="small muted">${t('das_aktive_szenario_gilt_fuer')}</span></div>`;
  if (!IM.edit) return h + `<div class="note">${t('noch_keine_kalkulation_kalkulation_anl')}</div>`;
  const e = IM.edit;
  const inp = (path, label, type = 'number', opts = {}) => { let v = get(e, path); if (type === 'month' && v) v = String(v).slice(0, 7); const attrs = Object.entries(opts).filter(([a]) => a !== 'hq').map(([a, b]) => `${a}="${b}"`).join(' '); return `<label>${label}${opts.hq ? hq(opts.hq) : ''}</label><input type="${type}" data-p="${path}" value="${v == null ? '' : esc(v)}" ${attrs}>`; };
  const sel = (path, label, options, hqk) => `<label>${label}${hqk ? hq(hqk) : ''}</label><select data-p="${path}">${options.map(([v, l]) => `<option value="${v}" ${String(get(e, path) ?? '') === String(v) ? 'selected' : ''}>${l}</option>`).join('')}</select>`;
  h += `<div class="immo-grid" data-ex="properties.calc"><div class="card" data-ex="properties.calc.inputs"><h3>${t('eingaben')} <span class="muted" style="text-transform:none;letter-spacing:0">${t('szenario_0', esc(k ? k.name : t('neu')))}</span></h3><div class="immo-form">
    <h4>${t('objekt')}</h4>
    ${inp('name', t('bezeichnung'), 'text')}${sel('kind', t('art'), [['commercial', t('gewerbe')], ['housing', t('wohnen')]])}${inp('area_sqm', t('flaeche_m2'), 'number', {step: '0.1'})}${inp('units', t('einheiten'), 'number', {step: '1'})}
    ${inp('purchase_price', t('kaufpreis_2'), 'number', {step: '1000'})}${inp('transfer_date', t('uebergang_nutzen_lasten'), 'month', {hq: 'immo_uebergang'})}${inp('horizon_years', t('horizont_jahre'), 'number', {step: '1', min: '1', max: '60'})}
    <h4>${t('nebenkosten_0', hq('immo_nk'))}</h4>
    ${inp('closing_costs.transfer_tax_percent', t('grunderwerbsteuer'), 'number', {step: '0.1'})}${inp('closing_costs.notary', t('notar_kaufvertrag'), 'number', {step: '1'})}${inp('closing_costs.land_register', t('grundbuch'), 'number', {step: '1'})}${inp('closing_costs.broker_fee', t('makler'), 'number', {step: '1'})}${inp('closing_costs.other_depreciation', t('sonstige_afa_basis'), 'number', {step: '1'})}${inp('closing_costs.immediately_deductible', t('sofort_abziehbar'), 'number', {step: '1'})}
    <h4>${t('abschreibung')}</h4>
    ${inp('building_share_percent', t('gebaeudeanteil'), 'number', {step: '0.01', hq: 'immo_geb'})}${inp('depreciation_percent', 'AfA % p.a.', 'number', {step: '0.01', hq: 'immo_afa'})}${inp('remaining_life_years', t('oder_restnutzungsdauer_jahre'), 'number', {step: '1'})}
    <h4>${t('miete')}</h4>
    ${inp('rent.net_rent_month', t('nettokaltmiete_monat'), 'number', {step: '1'})}${inp('rent.utilities_month', t('umlage_nk_vorauszahlung_monat'), 'number', {step: '1'})}${inp('rent.vacancy_percent', t('leerstand_mietausfall'), 'number', {step: '0.5'})}
    ${sel('rent.index.kind', t('anpassung'), [['cpi', t('indexmiete_vpi')], ['percent', t('feste_steigerung_p_a')], ['none', t('keine')]], 'immo_index')}
    ${inp('rent.index.cpi_base', t('vpi_bei_letzter_anpassung'), 'number', {step: '0.1'})}${inp('rent.index.cpi_current', t('vpi_aktuell'), 'number', {step: '0.1'})}${inp('rent.index.cpi_increase_percent', t('vpi_annahme_p_a'), 'number', {step: '0.1'})}${inp('rent.index.factor', t('weitergabe_faktor_01'), 'number', {step: '0.05'})}${inp('rent.index.threshold_percent', t('schwelle'), 'number', {step: '0.5'})}${inp('rent.index.increase_percent', t('feste_steigerung_p_a'), 'number', {step: '0.1'})}
    <h4>${t('kosten')}</h4>
    ${inp('costs.non_recoverable_pa', t('nicht_umlagefaehig_p_a'), 'number', {step: '10', hq: 'immo_kosten'})}${inp('costs.reserve_pa', t('ruecklage_p_a'), 'number', {step: '10', hq: 'immo_ruecklage'})}${sel('costs.increase', t('steigerung'), [['cpi', t('mit_vpi')], ['percent', t('fester_satz')], ['none', t('keine')]])}${inp('costs.increase_percent', t('fester_satz_p_a'), 'number', {step: '0.1'})}
    <h4>${t('gesellschafter_0', hq('immo_ges'))}</h4></div><div id="im-ges">${(e.partners || []).map((g, i) => `<div class="row tight" data-g="${i}"><input type="text" data-p="partners.${i}.name" value="${esc(g.name || '')}" placeholder="${t('name')}" style="width:140px"><input type="number" step="0.01" data-p="partners.${i}.share_percent" value="${g.share_percent ?? ''}" placeholder="${t('anteil_3')}" style="width:90px"><input type="number" step="0.001" data-p="partners.${i}.tax_rate_percent" value="${g.tax_rate_percent ?? ''}" placeholder="${t('steuersatz')}" style="width:110px"><button class="ghost small im-ges-del" data-i="${i}">✕</button></div>`).join('')}</div><div class="row tight"><button id="im-ges-add" class="small secondary">${t('gesellschafter_hinzufuegen')}</button></div>
    <div class="immo-form">${inp('distribution_percent', t('ausschuettung_des_ergebnisses'), 'number', {step: '1', hq: 'immo_aussch'})}${sel('tax_refund_in_cashflow', t('steuererstattung_im_cashflow'), [['true', t('ja')], ['false', t('nein')]])}
    <h4>${t('wert_verkauf')}</h4>${inp('appreciation_percent', t('wertentwicklung_p_a'), 'number', {step: '0.1', hq: 'immo_wert'})}${inp('sale.year', t('verkaufsjahr_optional'), 'number', {step: '1', hq: 'immo_verkauf'})}${inp('sale.costs_percent', t('verkaufskosten'), 'number', {step: '0.1'})}</div>
    <h4 style="margin:12px 0 2px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)">${t('finanzierung')}</h4><div id="im-loans">${(e.loans || []).map((l, i) => loanBox(l, i, im, konten)).join('')}</div><div class="row tight"><button id="im-loan-add" class="small secondary">${t('darlehen_hinzufuegen')}</button></div>
    <div class="actions"><button id="im-calc" class="small secondary">${t('neu_berechnen')}</button><label class="chk small">${t('szenario_name')} <input type="text" id="im-kalk-name" value="${esc(k ? k.name : t('kalkulation'))}" style="width:160px"></label><button id="im-kalk-save" class="small">${t('speichern')}</button></div><div id="im-err" class="findings"></div></div>
    <div id="im-result">${IM.res ? immoResultHtml(IM.res) : `<div class="card"><div class="muted">${t('berechnung_laeuft')}</div></div>`}</div></div>`;
  return h;
}
function loanBox(l, i, im, konten) {
  const p = k => `loans.${i}.${k}`;
  const v = k => l[k] == null ? '' : esc(l[k]);
  const ref = (im.loan_accounts || {})[l.name] || '';
  const st = (l.special_repayments || []).map(x => `${x.date ? String(x.date).slice(0, 7) : ''}: ${x.amount}`).join('; ');
  return `<div class="loan-box" data-loan="${i}"><div class="immo-form">
    <label>${t('bezeichnung')}</label><input type="text" data-p="${p('name')}" value="${v('name')}">
    <label>${t('betrag_2')}</label><input type="number" step="1000" data-p="${p('amount')}" value="${v('amount')}">
    <label>${t('zins_p_a')}</label><input type="number" step="0.01" data-p="${p('interest_percent')}" value="${v('interest_percent')}">
    <label>${t('art_0', hq('immo_darlehen_art'))}</label><select data-p="${p('kind')}">${[['annuity', t('annuitaet')], ['repayment', t('tilgungsdarlehen')], ['bullet', t('endfaellig')]].map(([a, b]) => `<option value="${a}" ${l.kind === a ? 'selected' : ''}>${b}</option>`).join('')}</select>
    <label>${t('annuitaet_monat')}</label><input type="number" step="0.01" data-p="${p('annuity_month')}" value="${v('annuity_month')}" placeholder="${t('oder_anfangstilgung')}">
    <label>${t('anfangstilgung_p_a')}</label><input type="number" step="0.01" data-p="${p('initial_repayment_percent')}" value="${v('initial_repayment_percent')}">
    <label>${t('tilgung_monat_tilgungsdarlehen')}</label><input type="number" step="1" data-p="${p('repayment_month')}" value="${v('repayment_month')}">
    <label>${t('sondertilgung_monat_0', hq('immo_sonder'))}</label><input type="number" step="1" data-p="${p('special_repayment_month')}" value="${v('special_repayment_month')}">
    <label>${t('ab_monat')}</label><input type="month" data-p="${p('special_repayment_from')}" value="${l.special_repayment_from ? String(l.special_repayment_from).slice(0, 7) : ''}">
    <label>${t('einzelne_sondertilgungen')}</label><input type="text" data-p="${p('special_repayments')}" data-kind="st" value="${esc(st)}" placeholder="2027-06: 50000; 2028-06: 50000">
    <label>${t('zinsbindung_bis_0', hq('immo_zinsbindung'))}</label><input type="month" data-p="${p('fixed_rate_until')}" value="${l.fixed_rate_until ? String(l.fixed_rate_until).slice(0, 7) : ''}">
    <label>${t('anschlusszins_p_a')}</label><input type="number" step="0.01" data-p="${p('followup_rate_percent')}" value="${v('followup_rate_percent')}">
    <label>${t('faelligkeit_0', hq('immo_faellig'))}</label><input type="month" data-p="${p('maturity')}" value="${l.maturity ? String(l.maturity).slice(0, 7) : ''}">
    <label>${t('bei_faelligkeit')}</label><select data-p="${p('maturity_kind')}">${[['open', t('offen_hinweis')], ['payback', t('rueckzahlung_aus_liquiditaet')]].map(([a, b]) => `<option value="${a}" ${(l.maturity_kind || 'open') === a ? 'selected' : ''}>${b}</option>`).join('')}</select>
    <label>${t('beginn_auszahlung')}</label><input type="month" data-p="${p('begin')}" value="${l.begin ? String(l.begin).slice(0, 7) : ''}" placeholder="${t('uebergang')}">
    <label>${t('abrechnung_0', hq('immo_abrechnung'))}</label><select data-p="${p('settlement')}">${[['monthly', t('monatlich_bank')], ['yearly', t('jaehrlich_stand_1_1')]].map(([a, b]) => `<option value="${a}" ${(l.settlement || 'monthly') === a ? 'selected' : ''}>${b}</option>`).join('')}</select>
    <label>${t('zinsen_abziehbar_0', hq('immo_abziehbar'))}</label><select data-p="${p('deductible')}"><option value="true" ${l.deductible !== false ? 'selected' : ''}>${t('ja')}</option><option value="false" ${l.deductible === false ? 'selected' : ''}>${t('nein')}</option></select>
    <label>${t('darlehenskonto_in_moneymoney_0', hq('immo_darlehen_konten'))}</label><select class="im-loan-konto" data-loan-name="${esc(l.name || '')}">${acctOptions(ref, x => !x.group)}</select>
  </div><div class="row tight"><button class="ghost small im-loan-del" data-i="${i}">${t('darlehen_entfernen')}</button></div></div>`;
}
function get(o, path) { return path.split('.').reduce((a, k) => (a == null ? undefined : a[k]), o); }
function setp(o, path, v) { const ks = path.split('.'); let a = o; for (let i = 0; i < ks.length - 1; i++) { const k = ks[i]; if (a[k] == null) a[k] = /^\d+$/.test(ks[i + 1]) ? [] : {}; a = a[k]; } a[ks[ks.length - 1]] = v; }
function immoResultHtml(r) {
  const K = r.figures, J = r.years;
  const pct = x => x == null ? '–' : FN(x * 100) + ' %';
  const kp = (l, v) => `<div class="k"><div class="l">${l}</div><div class="v">${v}</div></div>`;
  let h = `<div class="card" data-ex="properties.calc.kpis"><h3>${t('kennzahlen')}</h3><div class="kpis">${kp(t('gesamtinvestition'), F0(K.total_investment) + ' €')}${kp(t('eigenkapital_inkl_nk'), F0(K.equity_incl_costs) + ' €')}${kp(t('fremdkapital_ltv'), F0(K.loans) + ' € (' + pct(K.ltv) + ')')}${kp(t('kaufpreisfaktor'), FN(K.price_factor))}${kp(t('bruttomietrendite'), pct(K.gross_rental_yield))}${kp(t('nettomietrendite'), pct(K.net_rental_yield))}${kp(t('cashflow_jahr_1'), F0(K.cashflow_year1) + ' €')}${kp('Cash-on-Cash', pct(K.cash_on_cash))}${kp(t('dscr_jahr_1'), FN(K.dscr_year1))}${kp('AfA p.a.', F0(K.depreciation_year) + ' € (' + FN(K.depreciation_rate || 0) + t('auf') + F0(K.depreciation_base) + ')')}${kp(t('kapitaldienst_monat'), F0(K.debt_service_month) + ' €')}${kp(t('irr_bis') + (K.exit_year || '–'), pct(K.irr))}${K.price_sqm ? kp(t('preis_m2'), F0(K.price_sqm) + ' €') : ''}${K.rent_sqm ? kp(t('miete_m2'), F(K.rent_sqm) + ' €') : ''}</div>
    ${(r.hints || []).map(x => `<div class="banner" style="margin:4px 0">${esc(x)}</div>`).join('')}
    ${(K.rent_adjustments || []).length ? `<div class="small muted">${t('mietanpassungen')} ` + K.rent_adjustments.slice(0, 6).map(a => a.year + ': +' + FN(a.raise_percent) + ' % → ' + F0(a.net_rent_new) + ' €').join(' · ') + (K.rent_adjustments.length > 6 ? ' …' : '') + '</div>' : ''}
    <div class="im-chart" data-ex="properties.calc.chart">${immoChart(J)}</div></div>
    <div class="card" style="margin-top:12px" data-ex="properties.calc.years"><h3>${t('erste_jahre')}</h3><div class="wrap auto"><table class="plain"><thead><tr><th>${t('jahr_2')}</th><th class="num">${t('miete')}</th><th class="num">${t('kosten')}</th><th class="num">${t('zinsen')}</th><th class="num">${t('tilgung')}</th><th class="num">${t('afa')}</th><th class="num">${t('ergebnis')}</th><th class="num">${t('steuer')}</th><th class="num">${t('cashflow_2')}</th><th class="num">${t('vermoegensaufbau')}</th><th class="num">${t('ek_rendite_2')}</th><th class="num">${t('restschuld')}</th></tr></thead><tbody>`
    + J.slice(0, 12).map(j => `<tr><td>${j.year}${j.months < 12 ? ' <span class="muted small">(' + j.months + ` ${t('mon_2')}</span>` : ''}</td><td class="num">${F0(j.rent)}</td><td class="num">${F0(j.costs + j.reserve)}</td><td class="num">${F0(j.interest)}</td><td class="num">${F0(j.repayment + j.special_repayment)}</td><td class="num">${F0(j.depreciation)}</td><td class="num ${j.result < 0 ? 'neg' : 'pos'}">${F0(j.result)}</td><td class="num">${F0(j.tax)}</td><td class="num ${j.cashflow < 0 ? 'neg' : 'pos'}">${F0(j.cashflow)}</td><td class="num">${F0(j.wealth_build)}</td><td class="num">${j.return_on_equity == null ? '–' : FN(j.return_on_equity * 100, 1) + ' %'}</td><td class="num">${F0(j.remaining_debt)}</td></tr>`).join('') + '</tbody></table></div></div>';
  return h;
}
function immoChart(J) {
  if (!J.length) return '';
  const W = 560, H = 200, P = {l: 56, r: 56, t: 10, b: 24}, n = J.length, bw = (W - P.l - P.r) / n;
  const cfs = J.map(j => j.cashflow), rs = J.map(j => j.remaining_debt), ws = J.map(j => j.value);
  const cmax = Math.max(...cfs, 1) * 1.1, cmin = Math.min(...cfs, 0) * 1.1, rmax = Math.max(...rs, ...ws, 1) * 1.05;
  const yc = v => P.t + (cmax - v) * (H - P.t - P.b) / ((cmax - cmin) || 1), yr = v => P.t + (rmax - v) * (H - P.t - P.b) / rmax, x = i => P.l + i * bw;
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}">`;
  for (const [t, ref] of axisTicks(cmin, cmax, 4)) s += `<line x1="${P.l}" x2="${W - P.r}" y1="${yc(t)}" y2="${yc(t)}" stroke="var(--line)"/><text x="${P.l - 6}" y="${yc(t) + 4}" text-anchor="end">${Fk(t, false, ref)}</text>`;
  cfs.forEach((v, i) => { s += `<rect x="${(x(i) + bw * 0.15).toFixed(1)}" y="${Math.min(yc(v), yc(0)).toFixed(1)}" width="${(bw * 0.7).toFixed(1)}" height="${Math.abs(yc(v) - yc(0)).toFixed(1)}" fill="${v < 0 ? 'var(--c-aus)' : 'var(--c-ein)'}" rx="2"/>`; if (i % Math.ceil(n / 8) === 0) s += `<text x="${(x(i) + bw / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle">${J[i].year}</text>`; });
  s += `<path d="${rs.map((v, i) => (i ? 'L' : 'M') + (x(i) + bw / 2).toFixed(1) + ' ' + yr(v).toFixed(1)).join(' ')}" fill="none" stroke="var(--c-verb)" stroke-width="2"/>`;
  s += `<path d="${ws.map((v, i) => (i ? 'L' : 'M') + (x(i) + bw / 2).toFixed(1) + ' ' + yr(v).toFixed(1)).join(' ')}" fill="none" stroke="var(--c-immo)" stroke-width="2" stroke-dasharray="4 3"/>`;
  for (const [t, ref] of axisTicks(0, rmax, 4)) s += `<text x="${W - P.r + 6}" y="${yr(t) + 4}">${Fk(t, false, ref)}</text>`;
  return s + `</svg><div class="chart-legend"><span><i style="background:var(--c-ein)"></i>${t('cashflow_je_jahr_links')}</span><span><i style="background:var(--c-verb)"></i>${t('restschuld_rechts')}</span><span><i style="background:var(--c-immo)"></i>${t('objektwert_rechts')}</span></div>`;
}
function vImmoJahre(d) {
  const J = d.years || []; if (!J.length) return `<div class="note">${t('keine_kalkulation_vorhanden_oder_beric')}</div>`;
  const names = d.loan_names || [];
  let h = `<div class="toolbar"><span class="muted small">${t('aktive_kalkulation_0_alle_jahre', esc(d.name || ''))}</span><span class="sp"></span>${xlsxBtn('property', `data-immo="${esc(d.id)}"`)}</div><div class="wrap" data-ex="properties.years"><table><thead><tr><th>${t('jahr_2')}</th>${[t('miete'), t('umlage'), t('kosten'), t('ruecklage'), t('zinsen'), t('tilgung'), t('sondertilgung'), 'AfA', t('ergebnis'), t('steuer'), t('ergebnis_n_st'), t('ausschuettung'), t('cashflow_2'), t('cashflow_kum'), t('vermoegensaufbau'), t('ek_rendite_2'), t('restschuld'), t('objektwert'), t('ek_im_objekt'), 'DSCR', t('re_nkm_monat')].map(x => `<th>${x}</th>`).join('')}${names.map(n => `<th>${t('0_zins', esc(n))}</th><th>${t('0_tilgung', esc(n))}</th><th>${t('0_saldo', esc(n))}</th>`).join('')}</tr></thead><tbody>`;
  const c = v => `<td class="${v == null ? 'zero' : v < 0 ? 'neg' : 'pos'}">${v == null ? '–' : F(v)}</td>`;
  for (const j of J) h += `<tr><td>${j.year}${j.months < 12 ? ' (' + j.months + ' ' + t('mon_2') : ''}</td>${[j.rent, j.recoverable_costs, j.costs, j.reserve, j.interest, j.repayment, j.special_repayment, j.depreciation, j.result, j.tax, j.result_after_tax, j.distribution, j.cashflow, j.cashflow_cumulative, j.wealth_build].map(c).join('')}<td>${j.return_on_equity == null ? '–' : FN(j.return_on_equity * 100) + ' %'}</td>${[j.remaining_debt, j.value, j.equity_property].map(c).join('')}<td>${FN(j.dscr)}</td>${c(j.net_rent_monthly)}${names.map(n => c(j.loans[n].interest) + c(j.loans[n].repayment) + c(j.loans[n].balance_amount)).join('')}</tr>`;
  h += '</tbody></table></div>';
  return h;
}
function vImmoSollIst(d) {
  const rows = d.target_actual || [];
  if (!rows.length) return `<div class="note">${t('fuer_soll_ist_braucht_das')}</div>`;
  const c = (v, cls2 = '') => `<td class="num ${cls2}">${v == null ? '–' : F0(v)}</td>`;
  // Δ = actual − target; green where it is better than planned: more rent, less cost and interest (both below zero), less debt
  const dv = (soll, ist, more = 1) => ist == null || soll == null ? '<td></td>' : `<td class="num ${Math.abs(ist - soll) < 0.5 ? '' : (ist - soll) * more > 0 ? 'pos' : 'neg'}">${F0(ist - soll)}</td>`;
  return `<div class="wrap auto" data-ex="properties.target"><table class="plain"><thead><tr><th>${t('jahr_2')}</th><th class="num">${t('miete_soll')}</th><th class="num">${t('miete_ist')}</th><th class="num">Δ</th><th class="num">${t('kosten_soll')}</th><th class="num">${t('kosten_ist')}</th><th class="num">Δ</th><th class="num">${t('zinsen_soll')}</th><th class="num">${t('zinsen_ist')}</th><th class="num">Δ</th><th class="num">${t('restschuld_soll')}</th><th class="num">${t('restschuld_ist')}</th><th class="num">Δ</th></tr></thead><tbody>`
    + rows.map(r => `<tr><td>${r.year}</td>${c(r.rent_target)}${c(r.rent_actual)}${dv(r.rent_target, r.rent_actual)}${c(r.costs_target)}${c(r.costs_actual)}${dv(r.costs_target, r.costs_actual)}${c(r.interest_target)}${c(r.interest_actual)}${dv(r.interest_target, r.interest_actual)}${c(r.remaining_debt_target)}${c(r.remaining_debt_actual)}${dv(r.remaining_debt_target, r.remaining_debt_actual, -1)}</tr>`).join('')
    + `</tbody></table></div><div class="note">${t('ist_kategorisierte_umsaetze_der_vermie')}</div>`;
}
function vImmoDokumente(im) {
  const docs = im.documents || [];
  let h = `<div class="note">${H.documents}</div><div class="card" data-ex="properties.documents">${docs.map(d => `<div class="doc" data-id="${esc(d.id)}"><div class="n"><b>${esc(d.title)}</b>${d.kind ? ' <span class="tag">' + esc(d.kind) + '</span>' : ''}<div class="p" title="${esc(d.path)}">${esc(d.path)}</div></div><span class="small muted">${esc(d.added || '')}</span>${S.STATUS.local ? `<button class="ghost small doc-open">${t('oeffnen')}</button><button class="ghost small doc-show">${t('finder')}</button>` : ''}<button class="ghost small doc-del">✕</button></div>`).join('') || `<div class="muted small">${t('noch_keine_dokumente_verknuepft')}</div>`}
    <div class="row tight" style="margin-top:10px"><input type="text" id="doc-titel" placeholder="${t('titel_z_b_kaufvertrag')}" style="width:200px"><input type="text" id="doc-art" placeholder="${t('art_vertrag_gutachten')}" style="width:160px"><input type="text" id="doc-pfad" placeholder="${t('pfad_auf_dem_mac')}" style="min-width:260px;flex:1">${S.STATUS.local ? `<button id="doc-pick" class="small secondary">${t('datei_waehlen_2')}</button>` : ''}<button id="doc-add" class="small">${t('verknuepfen')}</button></div></div>`;
  return h;
}
async function immoCalc() {
  if (!IM.edit) return;
  try { IM.res = await api('/api/properties/calculate', {inputs: IM.edit, without_months: true}); const el = $('#im-result'); if (el) el.innerHTML = immoResultHtml(IM.res); const er = $('#im-err'); if (er) er.innerHTML = ''; }
  catch (e) { const el = $('#im-err'); if (el) el.innerHTML = `<div class="error">${esc(e.message)}</div>`; }
}
function bindImmo(main) {
  $$('.card[data-im]', main).forEach(c => c.addEventListener('click', () => { go('#properties/' + c.dataset.im); }));
  const nw = $('#im-new', main); if (nw) nw.addEventListener('click', async () => { const name = prompt(t('name_des_objekts')); if (!name) return; const b = S.area || ((S.CFG.areas || [])[0] || {}).id || ''; try { const r = await api('/api/properties', {action: 'create', name, area: b}); S.CFG = await api('/api/config'); go('#properties/' + r.property.id); } catch (e) { toast(e.message, 5000); } });
  const id = (location.hash.split('/')[1] || '').split('?')[0]; if (!id) return;
  const im = immoOf(id); if (!im) return;
  $$('.tabs button[data-t]', main).forEach(b => b.addEventListener('click', () => { IM.tab = b.dataset.t; route(); }));
  const del = $('#im-del', main); if (del) del.addEventListener('click', async () => { if (!confirm(t('objekt_2') + im.name + t('mit_allen_kalkulationen_loeschen'))) return; await api('/api/properties', {action: 'delete', id}); S.CFG = await api('/api/config'); go('#properties'); });
  const sm = $('#im-save-meta', main); if (sm) sm.addEventListener('click', async () => { try { await api('/api/properties', {action: 'update', id, name: $('#im-name').value, area: $('#im-bereich').value, category: $('#im-kat').value, property_account: $('#im-konto').value, in_planning: $('#im-plan').checked, notes: $('#im-notiz').value}); toast(t('gespeichert')); await loadAll(); route(); } catch (e) { toast(e.message, 5000); } });
  const ks = $('#im-kalk', main); if (ks) ks.addEventListener('change', e => { IM.kalk = e.target.value; IM.edit = null; route(); });
  const kn = $('#im-kalk-new', main); if (kn) kn.addEventListener('click', async () => {
    let eing = IM.edit ? JSON.parse(JSON.stringify(IM.edit)) : (await api('/api/properties/template')).inputs;
    if (!IM.edit) { eing.name = im.name; if (S.DATA && S.DATA.area_info && S.DATA.area_info[im.area] && S.DATA.area_info[im.area].kind === 'private') eing.partners = [{name: t('eigentuemer'), share_percent: 100, tax_rate_percent: 42}]; }
    const name = prompt(t('name_des_szenarios'), IM.edit ? t('variante') : t('basis')); if (!name) return;
    try { const r = await api('/api/properties', {action: 'calc_save', id, calc: {name, inputs: eing}}); S.CFG = await api('/api/config'); IM.kalk = r.property.calcs[r.property.calcs.length - 1].id; IM.edit = null; await loadAll(); route(); } catch (e) { toast(e.message, 6000); } });
  const ka = $('#im-kalk-aktiv', main); if (ka) ka.addEventListener('click', async () => { await api('/api/properties', {action: 'calc_activate', id, calc_id: IM.kalk}); await loadAll(); route(); });
  const kd = $('#im-kalk-del', main); if (kd) kd.addEventListener('click', async () => { if (!confirm(t('szenario_loeschen_2'))) return; await api('/api/properties', {action: 'calc_delete', id, calc_id: IM.kalk}); IM.kalk = null; IM.edit = null; await loadAll(); route(); });
  // Eingaben binden
  $$('[data-p]', main).forEach(inp => inp.addEventListener('input', () => {
    let v = inp.value;
    if (inp.dataset.kind === 'st') {          // "2027-06: 50.000; ...": an amount that is no number marks the field (and counts as nothing)
      let bad = false;
      v = v.split(';').map(x => x.trim()).filter(Boolean).map(x => { const [d, b] = x.split(':'), n = numIn(b); if (Number.isNaN(n)) bad = true; return {date: (d || '').trim(), amount: n || 0}; });
      inp.classList.toggle('invalid', bad);
    }
    else if (inp.type === 'number') v = v === '' ? null : parseFloat(v.replace(',', '.'));
    else if (v === 'true') v = true; else if (v === 'false') v = false;
    setp(IM.edit, inp.dataset.p, v);
    clearTimeout(IM.timer); IM.timer = setTimeout(immoCalc, 600);
  }));
  const la = $('#im-loan-add', main); if (la) la.addEventListener('click', () => { IM.edit.loans = IM.edit.loans || []; IM.edit.loans.push({name: t('darlehen_2') + (IM.edit.loans.length + 1), amount: 0, interest_percent: 3.5, kind: 'annuity', settlement: 'monthly', deductible: true}); route(); });
  $$('.im-loan-del', main).forEach(b => b.addEventListener('click', () => { IM.edit.loans.splice(+b.dataset.i, 1); route(); }));
  const ga = $('#im-ges-add', main); if (ga) ga.addEventListener('click', () => { IM.edit.partners = IM.edit.partners || []; IM.edit.partners.push({name: '', share_percent: 0, tax_rate_percent: 42}); route(); });
  $$('.im-ges-del', main).forEach(b => b.addEventListener('click', () => { IM.edit.partners.splice(+b.dataset.i, 1); route(); }));
  const cb = $('#im-calc', main); if (cb) cb.addEventListener('click', immoCalc);
  const sv = $('#im-kalk-save', main); if (sv) sv.addEventListener('click', async () => {
    const dk = {}; $$('.im-loan-konto', main).forEach(sel => { const name = sel.closest('.loan-box').querySelector('[data-p$=".name"]').value; if (sel.value) dk[name] = sel.value; });
    try { await api('/api/properties', {action: 'update', id, loan_accounts: dk}); await api('/api/properties', {action: 'calc_save', id, calc: {id: IM.kalk, name: $('#im-kalk-name').value, inputs: IM.edit}}); toast(t('kalkulation_gespeichert')); await loadAll(); route(); } catch (e) { $('#im-err').innerHTML = `<div class="error">${esc(e.message)}</div>`; } });
  if (IM.edit && !IM.res) immoCalc();
  // Dokumente
  const dp = $('#doc-pick', main); if (dp) dp.addEventListener('click', async () => { toast(t('dateiauswahl_am_mac_geoeffnet'), 4000); try { const r = await api('/api/file/choose', {kind: 'file', prompt: t('dokument_fuer') + im.name}); if (r.ok) { $('#doc-pfad').value = r.path; if (!$('#doc-titel').value) $('#doc-titel').value = r.name.replace(/\.[^.]+$/, ''); } else toast(r.text); } catch (e) { toast(e.message, 5000); } });
  const da = $('#doc-add', main); if (da) da.addEventListener('click', async () => { try { await api('/api/properties', {action: 'doc_add', id, title: $('#doc-titel').value, kind: $('#doc-art').value, path: $('#doc-pfad').value}); S.CFG = await api('/api/config'); route(); } catch (e) { toast(e.message, 5000); } });
  $$('.doc-del', main).forEach(b => b.addEventListener('click', async e => { const did = e.target.closest('.doc').dataset.id; await api('/api/properties', {action: 'doc_remove', id, document_id: did}); S.CFG = await api('/api/config'); route(); }));
  $$('.doc-open', main).forEach(b => b.addEventListener('click', async e => { const did = e.target.closest('.doc').dataset.id; const d = (im.documents || []).find(x => x.id === did); try { const r = await api('/api/file/open', {path: d.path}); if (r.status === 'icloud') toast(t('datei_liegt_in_icloud_und'), 5000); } catch (er) { toast(er.message, 5000); } }));
  $$('.doc-show', main).forEach(b => b.addEventListener('click', async e => { const did = e.target.closest('.doc').dataset.id; const d = (im.documents || []).find(x => x.id === did); try { await api('/api/file/reveal', {path: d.path}); } catch (er) { toast(er.message, 5000); } }));
}

// ---------------------------------------------------------------- Depots
// ---------------------------------------------------------------- Umsaetze & Belege
let UMS = {transactions: [], hits: 0, total: 0, years: []};
const QUELLE_TIP = {moneymoney: t('aus_moneymoney_2'), waiting: t('wartet_auf_moneymoney')};
// the filter of the page as a query -- the same for the list and its Excel export
function umsQuery(f = S.uf) {
  const q = new URLSearchParams();
  const P = {entity: 'entity', year: 'year', account: 'account', q: 'q'};
  for (const k in P) if (f[k]) q.set(P[k], f[k]);
  if (f.direction) q.set('direction', f.direction === 'aus' ? 'out' : 'in');
  if (f.ohne_beleg) q.set('without_receipt', '1'); if (f.uncategorized_flag) q.set('uncategorized', '1');
  if (f.ids && f.ids.length) q.set('ids', f.ids.join(','));          // bookings by their ids
  if (f.counted) q.set('counted', '1');          // as the categories' counts: booked, MoneyMoney's own category
  if (f.cfRows) { q.set('cf_rows', JSON.stringify(f.cfRows)); q.set('cf_area', f.cfArea || ''); q.set('cf_months', (f.cfMonths || []).join(',')); }      // behind a figure of the cash flow
  if (f.kats) q.set('categories', JSON.stringify(f.kats)); if (f.kats && f.mitOhne) q.set('with_uncategorized', '1'); if (f.date_from) q.set('from', f.date_from); if (f.date_to) q.set('to', f.date_to);      // opened from a chart
  return q;
}
async function loadUms() { const q = umsQuery(); q.set('limit', '400'); UMS = await api('/api/transactions?' + q.toString()); }
async function vUmsaetze() {
  if (!S.DATA) return noData;
  await loadUms();
  const f = S.uf, st = S.STATUS, konten = S.DATA.accounts.filter(k => !k.group && (!f.entity || k.path.startsWith(BN(f.entity))));
  // all filters always in view: what (area, year, account, search), which (direction, receipt, category state, dates), categories
  let h = `<div class="uf-filters" data-ex="transactions.filters"><div class="toolbar">
    <select id="uf-ent"><option value="">${t('alle_bereiche')}</option>${Object.keys(S.DATA.areas).map(k => `<option value="${esc(k)}" ${f.entity === k ? 'selected' : ''}>${esc(BN(k))}</option>`).join('')}</select>
    <select id="uf-jahr"><option value="">${t('alle_jahre')}</option>${UMS.years.map(y => `<option ${f.year === y ? 'selected' : ''}>${y}</option>`).join('')}</select>
    <select id="uf-konto"><option value="">${t('alle_konten')}</option>${konten.map(k => `<option value="${k.uuid}" ${f.account === k.uuid ? 'selected' : ''}>${esc(k.name)}</option>`).join('')}</select>
    <input type="search" id="uf-q" data-find placeholder="${t('suche_name_zweck_kategorie_betrag')}" value="${esc(f.q)}" style="min-width:220px">
  </div><div class="toolbar">
    <div class="seg"><button data-r="" class="${!f.direction ? 'on' : ''}">${t('alle_2')}</button><button data-r="aus" class="${f.direction === 'aus' ? 'on' : ''}">${t('ausgaben')}</button><button data-r="ein" class="${f.direction === 'ein' ? 'on' : ''}">${t('einnahmen')}</button></div>
    <label class="switch"><input type="checkbox" id="uf-ob" ${f.ohne_beleg ? 'checked' : ''}><i></i>${t('ohne_beleg_2')}</label>
    <label class="switch"><input type="checkbox" id="uf-ok" ${f.uncategorized_flag ? 'checked' : ''}><i></i>${t('ohne_kategorie_2')}</label>
    <label class="small">${t('cf_von')} <input type="date" id="uf-von" value="${esc(f.date_from)}"></label><label class="small">${t('cf_bis')} <input type="date" id="uf-bis" value="${esc(f.date_to)}"></label>
  </div>
  <div class="toolbar uf-ext">${f.ids || f.cfRows ? `<span class="chip">${esc(f.title || '')}<button class="icon ghost" data-ids-x="1" aria-label="${esc(t('entfernen'))}">✕</button></span>` : ''}
    <span class="small muted">${t('kategorien')}</span>${f.katsLabel && f.kats ? `<span class="chip">${esc(t('uf_alle_kats', f.katsLabel, f.kats.length))}${f.mitOhne ? ` · ${esc(t('ohne_kategorie_2'))}` : ''}<button class="icon ghost" data-kat-all="1" aria-label="${esc(t('entfernen'))}">✕</button></span>`
      : (f.kats || []).map((k, i) => `<span class="chip">${esc(CP(k))}<button class="icon ghost" data-kat-x="${i}" aria-label="${esc(t('entfernen'))}">✕</button></span>`).join('')}
    <input type="text" id="uf-kat-add" list="uf-kats" placeholder="${t('uf_kategorie_hinzu')}" style="min-width:230px"><datalist id="uf-kats">${(S.KATS || []).filter(k => !k.default).map(k => `<option value="${esc(CP(k.path))}">`).join('')}</datalist>
    ${f.est ? `<span class="small muted">${t('uf_ohne_geschaetzte')}</span>` : ''}
    ${f.date_from || f.date_to || f.kats || f.ids || f.cfRows ? `<button id="uf-chip-x" class="ghost small">${t('uf_filter_aufheben')}</button>` : ''}
  </div></div>
  <div class="toolbar"><span class="muted small ums-hits" data-ex="transactions.hits">${t('0_treffer_1_von_2', UMS.hits, UMS.hits > UMS.transactions.length ? ' (erste ' + UMS.transactions.length + t('angezeigt_filter_verfeinern') : '', UMS.total)}</span><span class="sp"></span>
    <button id="bl-folder" class="secondary small" ${st.local ? '' : t('disabled_title_nur_am_mac')}>${t('belegordner_oeffnen')}</button>
    <button id="bl-export" class="secondary small">${t('belege_exportieren_zip')}</button>
    ${xlsxBtn('transactions', `title="${esc(t('uf_excel_tip'))}"`)}</div>`;          // the transactions as filtered (all matches, not only those shown)
  if (S.sel.size) h += `<div class="banner info" data-ex="transactions.table" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">${t('0_ausgewaehlt_1', S.sel.size, `<input type="text" id="bulk-cat" list="bulk-kats" placeholder="${t('kategorie')}" style="min-width:240px">${katList('bulk-kats')}<button id="bulk-cat-btn" class="small">${t('kategorie_zuweisen')}</button>`)}<button id="bulk-clear" class="small secondary">${t('auswahl_aufheben')}</button></div>`;
  h += `<div class="wrap" data-ex="transactions.table"><table class="plain" id="ums-table"><thead><tr><th style="width:28px"><input type="checkbox" id="sel-all"></th><th>${t('datum')}</th><th>${t('konto_2')}</th><th>${t('name')}</th><th>${t('verwendungszweck')}</th><th class="num">${t('betrag')}</th><th>${t('kategorie')}</th><th class="num">${t('belege')}</th></tr></thead><tbody>`
    + UMS.transactions.map(u => `<tr class="clickable ${S.sel.has(u.id) ? 'sel' : ''}" data-id="${u.id}"><td><input type="checkbox" class="sel" ${S.sel.has(u.id) ? 'checked' : ''}></td><td class="small" style="white-space:nowrap">${FD(u.date)}</td><td class="small">${esc(u.account_name)}</td><td>${esc(u.name)}</td><td class="small muted" style="max-width:360px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(u.purpose)}</td><td class="num ${u.amount < 0 ? 'neg' : 'pos'}">${F(u.amount)}</td><td class="small" title="${QUELLE_TIP[u.source] || ''}">${u.category ? esc(CP(u.category)) + (u.source === 'waiting' ? ' <span class="muted">⏳</span>' : '') : u.needs === false || u.transfer ? '<span class="muted">–</span>' : `<span class="pill warn">${t('ohne')}</span>`}</td><td class="num">${u.receipts ? `<span class="pill ok">${u.receipts}</span>` : `<button class="ghost small add-beleg" title="${t('beleg_hinzufuegen')}">＋</button>`}</td></tr>`).join('')
    + '</tbody></table></div>';
  return h;
}
async function openDrawer(txId) {
  const u = UMS.transactions.find(x => x.id === txId); if (!u) return;
  const bl = await api('/api/receipts?files=1');
  const mine = bl.entry_list.filter(e => e.tx_id === txId), free = bl.files.filter(d => !d.linked);
  const st = S.STATUS;
  const d = $('#drawer');
  d.innerHTML = `<button class="close icon">✕</button><h2>${esc(u.name)}</h2><div data-ex="transactions.detail">
    <div class="kv"><div>${t('datum')}</div><div>${FD(u.date)}</div><div>${t('betrag')}</div><div class="${u.amount < 0 ? 'neg' : 'pos'}" style="font-weight:600;color:var(--${u.amount < 0 ? 'neg' : 'pos'})">${F(u.amount)} €</div><div>${t('konto_2')}</div><div>${esc(u.account_name)} · ${esc(BN(u.entity))}</div><div>${t('zweck')}</div><div>${esc(u.purpose) || '–'}</div><div>${t('kategorie')}</div><div>${u.category ? esc(CP(u.category)) : u.needs === false || u.transfer ? '–' : `<span class="pill warn">${t('ohne')}</span>`}${u.source ? ' <span class="small muted">· ' + (QUELLE_TIP[u.source] || '') + '</span>' : ''}</div><div>${t('status')}</div><div>${u.booked_count ? t('gebucht') : t('vorgemerkt')}${u.checkmark ? t('abgehakt') : ''}</div><div>${t('id')}</div><div class="mono small">${u.id}</div></div>
    ${u.needs !== false ? `<div class="row tight" style="margin-top:10px"><input type="text" id="dr-kat" list="dr-kats" value="${esc(CP(u.category))}" placeholder="${t('kategorie_aus_moneymoney')}" style="min-width:240px;flex:1">${katList('dr-kats')}<button id="dr-cat-btn" class="small">${t('in_moneymoney_eintragen')}</button></div>` : ''}
    <h3>${t('belege_n', mine.length)}</h3>
    ${mine.map(e => `<div class="beleg" data-id="${e.id}"><span class="n" title="${esc(e.path)}">${e.external ? `<span class="tag" title="${t('verknuepfung_zu_einer_datei_ausserhalb')}">${t('mac')}</span>` : ''}${esc(e.path.split('/').pop())}</span><span class="small muted">${e.external ? (e.status === 'icloud' ? `<span class="pill warn">${t('icloud_nicht_geladen')}</span>` : e.status === 'lacking' ? `<span class="pill err">${t('fehlt')}</span>` : '') : (e.size_bytes / 1024).toFixed(0) + ' KB'}</span><a href="/api/receipts/file?id=${e.id}" target="_blank" class="small">${t('ansehen')}</a>${st.local ? `<button class="ghost small bl-show" title="${t('im_finder_zeigen_2')}">${t('finder')}</button>` : ''}<button class="ghost small bl-note" title="${t('notiz')}">✎</button><button class="ghost small bl-del" title="${e.external ? t('verknuepfung_entfernen_datei_bleibt') : t('zuordnung_entfernen')}">✕</button></div>${e.note ? `<div class="small muted" style="padding:0 0 6px">${esc(e.note)}</div>` : ''}`).join('') || `<div class="muted small">${t('noch_kein_beleg')}</div>`}
    <div class="drop" id="dr-drop" style="margin-top:12px">${t('datei_hierher_ziehen')}<br><button id="dr-pick" class="small" style="margin-top:8px">${t('datei_waehlen')}</button> <button id="dr-cam" class="small secondary" style="margin-top:8px">${t('foto_aufnehmen')}</button><div class="small muted" style="margin-top:6px">${t('pdf_bilder_e_mails_office')}</div></div>
    ${free.length ? `<h3>${t('vorhandene_datei_aus_dem_belegordner')}</h3><div class="row tight"><select id="dr-free" style="max-width:300px">${free.map(x => `<option value="${esc(x.path)}">${esc(x.path)}</option>`).join('')}</select><button id="dr-link" class="small secondary">${t('zuordnen')}</button></div>` : ''}
    <h3>${t('datei_auf_dem_mac_verknuepfen', hq('documents'))}</h3><div class="row tight"><input type="text" id="dr-ext" placeholder="${t('pfad_z_b_library_mobile')}" style="flex:1;min-width:220px">${st.local ? `<button id="dr-ext-pick" class="small secondary">${t('datei_waehlen_2')}</button>` : ''}<button id="dr-ext-link" class="small secondary">${t('verknuepfen')}</button></div><div class="small muted">${t('die_datei_bleibt_wo_sie')}</div></div>`;
  d.classList.add('open');
  $('.close', d).onclick = closeDrawer;
  $('#dr-pick', d).onclick = () => pickFiles(txId, false);
  $('#dr-cam', d).onclick = () => pickFiles(txId, true);
  const dz = $('#dr-drop', d);
  dz.ondragover = e => { e.preventDefault(); dz.classList.add('over'); }; dz.ondragleave = () => dz.classList.remove('over');
  dz.ondrop = async e => { e.preventDefault(); dz.classList.remove('over'); await uploadFiles(txId, e.dataTransfer.files); };
  const lk = $('#dr-link', d); if (lk) lk.onclick = async () => { try { await api('/api/receipts/link', {tx_id: txId, path: $('#dr-free', d).value}); toast(t('zugeordnet')); await refreshUms(txId); } catch (e) { toast(e.message, 5000); } };
  $$('.bl-del', d).forEach(b => b.onclick = async e => { const id = e.target.closest('.beleg').dataset.id, ent = mine.find(x => x.id === id); const del = ent && ent.external ? false : confirm(t('zuordnung_entfernen_datei_auch_loesche')); try { await api('/api/receipts/remove', {id, delete_file: del}); await refreshUms(txId); } catch (er) { toast(er.message, 5000); } });
  const ep = $('#dr-ext-pick', d); if (ep) ep.onclick = async () => { toast(t('dateiauswahl_am_mac_geoeffnet'), 4000); try { const r = await api('/api/file/choose', {kind: 'file', prompt: t('beleg_fuer') + u.name}); if (r.ok) $('#dr-ext', d).value = r.path; else toast(r.text); } catch (er) { toast(er.message, 5000); } };
  const el = $('#dr-ext-link', d); if (el) el.onclick = async () => { const pfad = $('#dr-ext', d).value.trim(); if (!pfad) return toast(t('pfad_fehlt')); try { await api('/api/receipts/link', {tx_id: txId, path: pfad, external: true}); toast(t('verknuepft')); await refreshUms(txId); } catch (er) { toast(er.message, 6000); } };
  $$('.bl-note', d).forEach(b => b.onclick = async e => { const id = e.target.closest('.beleg').dataset.id, ent = mine.find(x => x.id === id); const n = prompt(t('notiz_zum_beleg'), ent.note || ''); if (n === null) return; await api('/api/receipts/update', {id, note: n}); await refreshUms(txId); });
  $$('.bl-show', d).forEach(b => b.onclick = async e => { const id = e.target.closest('.beleg').dataset.id, ent = mine.find(x => x.id === id); try { await api('/api/receipts/open', {path: ent.path}); } catch (er) { toast(er.message, 4000); } });
  const cb = $('#dr-cat-btn', d); if (cb) cb.onclick = async () => { const kat = $('#dr-kat', d).value.trim(); if (!kat) return toast(t('kategorie_fehlt')); try { const r = await assignCats([txId], kat); toast(assignMsg(r), 5000); await loadAll(); await refreshUms(txId); } catch (e) { toast(e.message, 5000); } };
}
function closeDrawer() { $('#drawer').classList.remove('open'); DRW.key = null; }
// which drawer is open; a click on the row that opened it closes it (the click outside closes it first -- it must not reopen)
const DRW = {key: null, closed: null, src: null, shown: null, key2: null};
// The side panel stands beside the page, like an inspector on the Mac: the page makes room for it whenever it is open (a window too
// narrow for both: it lies over the page -- CSS). The figure behind it is marked while it is open and stays in view.
document.addEventListener('click', e => {
  if (!e.target.closest || e.target.closest('#drawer')) return;
  DRW.src = e.target.closest('#main') ? (e.target.closest('td, th, .cf-hit, [data-cftip], .cf-br-row, .item, tr') || e.target) : null;
}, true);
function drawerReveal() {
  const d = $('#drawer'), open = !!(d && d.classList.contains('open'));
  document.body.classList.toggle('dock', open);
  if (!open) { $$('.dr-src').forEach(x => x.classList.remove('dr-src')); DRW.shown = null; return; }
  const src = DRW.src && document.contains(DRW.src) ? DRW.src : null;
  if (!src || src === DRW.shown) return;
  DRW.shown = src; DRW.key2 = srcKey(src);
  const mark = el => { $$('.dr-src').forEach(x => x.classList.remove('dr-src')); if (el && !(el instanceof SVGElement)) el.classList.add('dr-src'); };
  mark(src);
  // the narrower page (a chart drawn anew): the same figure, found again by its marks, in view
  setTimeout(() => { const el = document.contains(src) ? src : srcFind(DRW.key2); if (!el || !$('#drawer').classList.contains('open')) return;
    DRW.shown = el; mark(el); el.scrollIntoView({block: 'nearest', inline: 'nearest', behavior: 'smooth'}); }, 320);
}
// a figure by what marks it (the nearest element with an id, its tag and data marks) -- to find it again after a redraw
function srcKey(el) {
  const host = el.closest('[id]'), data = Object.entries(el.dataset || {}).filter(([k]) => k !== 'cftip').map(([k, v]) => `[data-${k.replace(/[A-Z]/g, c => '-' + c.toLowerCase())}="${CSS.escape(v)}"]`).join('');
  if (!host || !data) return null;
  const sel = el.tagName.toLowerCase() + data, all = [...host.querySelectorAll(sel)];
  return {host: host.id, sel, n: all.indexOf(el)};
}
function srcFind(k) { if (!k) return null; const h = document.getElementById(k.host); return h ? h.querySelectorAll(k.sel)[Math.max(0, k.n)] || null : null; }
// a click on the panel's empty background closes it (text, tables and controls stay as they are; the pointer stays an arrow)
document.addEventListener('click', e => { const d = e.target && e.target.id === 'drawer' ? e.target : null; if (!d || !d.classList.contains('open')) return;
  if (drawerDirty() && !confirm(t('ungespeicherte_aenderungen_verwerfen'))) return;          // unsaved entries: asked first, as beside it
  closeDrawer(); });
new MutationObserver(() => drawerReveal()).observe(document.getElementById('drawer') || document.body, {attributes: true, attributeFilter: ['class'], childList: true});
function drawerAgain(key) {
  const c = DRW.closed; DRW.closed = null;
  if (c && c.key === key && Date.now() - c.t < 800) return true;
  DRW.key = key; return false;
}
async function belegeApi(path, body) {
  // Erster Beleg: Ordner nur nach Rueckfrage anlegen (oder anderen Ordner in den Einstellungen waehlen)
  try { return await api(path, body); }
  catch (e) {
    if (!(e.data && e.data.confirm_folder)) throw e;
    if (!confirm(t('belege_werden_im_ordner', e.data.folder))) { go('#settings/receipts'); throw new Error(t('err_kein_belegordner')); }
    return api(path, Object.assign({}, body, {create_folder: true}));
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
    if (f.size > 60 * 1024 * 1024) { toast(f.name + t('zu_gross_max_60_mb'), 5000); continue; }
    toast(t('lade') + f.name + ' …', 60000);
    try {
      const b64 = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1] || ''); r.onerror = rej; r.readAsDataURL(f); });
      await belegeApi('/api/receipts/upload', {tx_id: txId, file_name: f.name, content: b64});
      toast(t('datei_abgelegt', f.name));
    } catch (e) { toast(t('fehler_3') + e.message, 6000); }
  }
  await refreshUms(txId);
}

// ---------------------------------------------------------------- Regeln
// The name of each account in a list; accounts of the same name (the "Kontokorrent" of each company) also name their area
// -- or, within one area, their group in MoneyMoney -- so the menu and the chosen entry tell them apart.
function acctLabels(list) {
  const count = (xs, f) => xs.reduce((m, k) => m.set(f(k), (m.get(f(k)) || 0) + 1), new Map());
  const parent = k => CP(k.path.split(' / ').slice(0, -1).join(' / '));
  const byName = count(list, k => k.name), where = k => (k.area || '').split(', ')[0] || k.path.split(' / ')[0];
  const first = new Map(list.map(k => [k.uuid, byName.get(k.name) > 1 && where(k) !== k.name ? k.name + ' · ' + where(k) : k.name]));
  const again = count(list, k => first.get(k.uuid));
  return new Map(list.map(k => [k.uuid, again.get(first.get(k.uuid)) > 1 && parent(k) ? k.name + ' · ' + parent(k) : first.get(k.uuid)]));
}
function acctOptions(selected, filter) {
  const sel = (selected || '').split('|')[0].trim(), list = S.KONTEN.filter(filter || (() => true)), lab = acctLabels(list);
  return `<option value="">${t('waehlen')}</option>` + list.map(k =>
    `<option value="${k.uuid} | ${esc(k.name)}" ${k.uuid === sel ? 'selected' : ''}>${' '.repeat(k.depth * 3)}${esc(lab.get(k.uuid))}${k.group ? t('gruppe_suffix') : (k.manual ? t('manuell_2') : '')}</option>`).join('')
    + (sel && !S.KONTEN.some(k => k.uuid === sel) ? `<option value="${esc(selected)}" selected>${t('0_nicht_gefunden', esc(selected))}</option>` : '');
}
const onlyManual = k => !k.group && k.manual, onlyLeaves = k => !k.group;
function vRegeln() {
  // Buchungsregeln: one switch (book automatically); loans as collapsible rows; one card per company (area of the kind
  // "Gesellschaft") with its participation and counter accounts; target, actual and difference live; one save bar for all
  const C = S.CFG;
  const lr = (S.STATUS || {}).last_run, pend = lr && lr.dry_run ? (lr.proposals || []).length : 0, auto = C.dry_run === false, loc = !!(S.STATUS || {}).local;
  let h = `<div class="rules-page" data-ex="accounts.rules"><p class="lead">${t('regeln_lead')} <a href="#bookings">${pend ? tn('0_buchungsvorschlaege', pend) : t('nav_auto_buchungen')} →</a></p>`
    + (S.KONTEN.length ? '' : `<div class="note"><b>${t('noch_keine_konten_geladen_unter')}</b></div>`);
  h += `<div class="group" data-ex="accounts.rules.auto"><div class="set-row"><div class="grow"><b>${t('auto_buchen')}</b><div class="small muted">${t(auto ? 'auto_buchen_an' : 'auto_buchen_aus')}${loc ? '' : ' ' + t('nur_am_mac_klammer')}</div></div>`
    + `<label class="switch${loc ? '' : ' off'}"><input type="checkbox" id="auto-book" ${auto ? 'checked' : ''} ${loc ? '' : 'disabled'}><i></i></label></div></div>`;
  h += `<section class="rule-sec" data-ex="accounts.rules.loans"><div class="sec-head"><h2>${t('regel_darlehen_titel')}${hq('regel_darlehen_h')}</h2><span class="sp"></span><button id="add-loan" class="secondary small add-rule">${t('darlehen_hinzufuegen')}</button></div>`
    + `<p class="sec-sub">${t('darlehen_sub')}</p><div class="list" id="loans">${(C.loans || []).map((l, i) => loanForm(l, i)).join('')}</div><div class="empty small muted">${t('leer_darlehen')}</div></section>`;
  const cos = companyAreas();
  h += `<section class="rule-sec" data-ex="accounts.rules.companies"><div class="sec-head"><h2>${t('regel_beteiligungen')}${hq('regel_gesellschaften_h')}</h2></div><p class="sec-sub">${t('gesellschaften_sub')}</p>`
    + `<div id="companies">${cos.map(b => companyCard(b, (C.companies || []).find(g => String(g.area) === String(b.id)) || {})).join('')}</div>`
    + (cos.length ? '' : `<div class="empty small muted">${t('leer_gesellschaften')} <a href="#accounts/areas">${t('mod_areas')} →</a></div>`) + `</section>`;
  h += `<section class="rule-sec" data-ex="accounts.rules.mirrors"><div class="sec-head"><h2>${t('co_gegenkonten')}${hq('h_co_gk')}</h2><span class="sp"></span><button id="add-mirror" class="secondary small add-rule">${t('gegenkonto_hinzufuegen')}</button></div>`
    + `<p class="sec-sub">${t('spiegel_sub')}</p><div id="mirrors">${(C.account_mirrors || []).map(mirrorRow).join('')}</div><div class="empty small muted">${t('leer_spiegel')}</div></section>`;
  h += `<div id="rules-warn" class="findings"></div><div id="findings" class="findings"></div>`
    + `<div class="savebar"><span class="small muted"><span id="rules-state">${t('regeln_gespeichert')}</span>${more('rules')}</span><span class="sp"></span>`
    + `<button id="save-rules" data-cmd-s disabled>${t('speichern_und_pruefen')}</button></div></div>`;
  return h;
}
// the companies: areas of the kind "Gesellschaft" (as set up; without own areas the top groups of MoneyMoney), in their order
function companyAreas() {
  const own = S.CFG.areas || [];
  const list = own.length ? own : S.KONTEN.filter(k => k.group && k.depth === 0).map(r => ({id: r.uuid, name: r.name}));
  return list.filter(b => b.active !== false && (b.kind || guessArt(b.name)) === 'company');
}
const pctText = v => (Math.round(parseFloat(v) * 10000) / 100).toLocaleString(LOCALE) + ' %';
function acctSel(cls, selected, filter, empty) {
  const sel = (selected || '').split('|')[0].trim(), list = S.KONTEN.filter(filter), lab = acctLabels(list);
  return `<select class="${cls}"><option value="">${empty}</option>` + list.map(k => `<option value="${k.uuid} | ${esc(k.name)}" ${k.uuid === sel ? 'selected' : ''}>${esc(lab.get(k.uuid))}</option>`).join('')
    + (sel && !list.some(k => k.uuid === sel) ? `<option value="${esc(selected)}" selected>${S.KONTEN.some(k => k.uuid === sel) ? t('0_nicht_waehlbar', esc(refName(selected))) : t('0_nicht_gefunden', esc(refName(selected) || selected))}</option>` : '') + `</select>`;
}
// an account in two steps, side by side: the area, then its accounts -- the account select keeps its class and value
// (one area only: one select)
const AP = new Map(); let apN = 0;
const apAreaName = id => id ? (((S.CFG.areas || []).find(b => String(b.id) === id) || {}).name || BN(id) || id) : t('ohne_bereich');
function acctPick(cls, selected, filter, empty) {
  const sel = (selected || '').split('|')[0].trim(), list = S.KONTEN.filter(filter), lab = acctLabels(list), areaOf = k => String(k.area_id || '');
  const order = (S.CFG.areas || []).map(b => String(b.id)), rank = id => id === '' ? 1e6 : (order.indexOf(id) + 1 || 1e5);
  const ids = [...new Set(list.map(areaOf))].sort((a, b) => rank(a) - rank(b));
  if (ids.length < 2) return acctSel(cls, selected, filter, empty);
  const cur = list.find(k => k.uuid === sel), area = cur ? areaOf(cur) : ids[0], n = String(++apN);
  const missing = sel && !cur ? `<option value="${esc(selected)}" selected>${S.KONTEN.some(k => k.uuid === sel) ? t('0_nicht_waehlbar', esc(refName(selected))) : t('0_nicht_gefunden', esc(refName(selected) || selected))}</option>` : '';
  AP.set(n, {opts: list.map(k => ({a: areaOf(k), v: `${k.uuid} | ${k.name}`, l: lab.get(k.uuid), on: k.uuid === sel})), empty, missing});
  return `<span class="acct-pick"><select class="ap-area" data-ap="${n}" aria-label="${esc(t('bereich'))}">${ids.map(id => `<option value="${esc(id)}" ${id === area ? 'selected' : ''}>${esc(apAreaName(id))}</option>`).join('')}</select>`
    + `<select class="${cls}" data-apk="${n}">${apOptions(n, area)}</select></span>`;
}
const apOptions = (n, area) => { const d = AP.get(n); return `<option value="">${d.empty}</option>` + d.opts.filter(o => o.a === area).map(o => `<option value="${esc(o.v)}" ${o.on ? 'selected' : ''}>${esc(o.l)}</option>`).join('') + d.missing; };
// another area: its accounts (nothing chosen) -- before the page's own change handler sees the event
document.addEventListener('change', e => {
  const a = e.target; if (!a.matches || !a.matches('select.ap-area')) return;
  const d = AP.get(a.dataset.ap), acc = a.parentElement.querySelector(`select[data-apk="${a.dataset.ap}"]`); if (!d || !acc) return;
  d.opts.forEach(o => { o.on = false; }); d.missing = '';
  acc.innerHTML = apOptions(a.dataset.ap, a.value);
}, true);
// counter account: a private manual account (outside the company) = counterpart of one account of the company
// an account mirror: any two accounts (your own, a company's, two companies'), booked from its own day on
function mirrorRow(m) {
  const pick = k => !k.group;
  return `<div class="gk-row" data-kat="${esc(m.category || '')}"${m.review ? ' data-review="1"' : ''}>${reviewMark(m)}${acctPick('g-a', m.a, pick, t('konto_waehlen'))}`
    + `<span class="gk-arrow" title="${esc(t('gk_spiegel'))}" aria-label="${esc(t('gk_spiegel'))}">⇄</span>${acctPick('g-b', m.b, pick, t('konto_waehlen'))}`
    + `<button class="ico gk-del" title="${esc(t('entfernen'))}" aria-label="${esc(t('entfernen'))}">×</button>`
    + `<div class="gk-ab"><span class="small muted">${t('co_rueck')}${hq('h_gk_rueck')}</span>${backField(m.from_date, 'rueck_alles_spiegel')}</div><div class="pv small"></div></div>`;
}
// "Buchen ab": from a day (new: today) or everything since the company exists
const isoToday = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); };
function backField(v, allKey = 'rueck_alles') {
  v = String(v || ''); const day = /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : isoToday();
  const all = v === 'all';
  return `<div class="row tight"><select class="c-rmode"><option value="date" ${all ? '' : 'selected'}>${t('rueck_datum')}</option><option value="all" ${all ? 'selected' : ''}>${t(allKey)}</option></select>`
    + `<input type="date" class="c-ab${all ? ' hidden' : ''}" value="${esc(day)}" max="${isoToday()}"></div>`;
}
const backValue = c => $('.c-rmode', c).value === 'all' ? 'all' : ($('.c-ab', c).value || isoToday());
const betCandidate = (bid) => k => !k.group && k.manual && k.role === 'participations' && k.area_id !== String(bid);
// rhythm: daily fits booking fully automatically, monthly fits approval (else a booking waits every day) -- a hint only when it does not fit
const taktTip = takt => { const auto = S.CFG.dry_run === false, monthly = takt === 'monthly'; return auto && monthly ? t('takt_tipp_taeglich') : !auto && !monthly ? t('takt_tipp_monatlich') : ''; };
function companyCard(b, g) {
  // all settings of a company in one card, nothing folded away; no account chosen in advance (choosing one starts the bookings)
  const has = b.share != null && b.share !== '', bid = String(b.id);
  const row = (label, help, field) => `<div class="co-row"><div class="co-l">${label}${hq(help)}</div><div class="co-f">${field}</div></div>`;
  return `<div class="co-card" data-b="${esc(bid)}"${g.review ? ' data-review="1"' : ''}><div class="co-head"><h3>${esc(b.name)}</h3>${reviewMark(g)}`
    + (has ? `<a class="pill neutral" href="#accounts/areas">${t('anteil_0', pctText(b.share))}</a>` : `<a class="pill warn" href="#accounts/areas">${t('anteil_fehlt')}</a>`) + hq('h_co_anteil') + `</div>`
    + row(t('co_beteiligung'), 'h_co_bet', `${acctSel('c-bet', g.participation, betCandidate(bid), t('keine_2'))}<div class="pv small" data-pv="b" data-ex="accounts.rules.companies.preview"></div>`)
    + row(t('co_takt'), 'h_co_takt', `<select class="c-takt"><option value="daily" ${g.cycle !== 'monthly' ? 'selected' : ''}>${t('takt_taeglich')}</option><option value="monthly" ${g.cycle === 'monthly' ? 'selected' : ''}>${t('takt_monatlich')}</option></select><div class="small muted c-takt-tip">${taktTip(g.cycle)}</div>`)
    + row(t('co_rueck'), 'h_co_rueck', backField(g.retroactive_from))
    + row(t('co_schwelle'), 'h_co_schwelle', `<div class="row tight"><input type="number" step="0.01" min="0.01" class="c-sw" value="${g.threshold ?? 0.01}" style="width:110px"> €</div>`)
    + row(t('gegenpartei'), 'h_co_gp', `<input type="text" class="c-gp" value="${esc(g.counterparty || '')}" placeholder="${esc(b.name)}">`)
    + `</div>`;
}
// what a rule would book, behind its count: a click opens it in the side panel (with the way to approve it)
const RPV = {list: []};
const pvOpen = (p, n) => { RPV.list.push(p); return `<a href="#" class="pv-diff pv-open" data-pv="${RPV.list.length - 1}">${n === 1 ? t('buchung_offen_1') : t('buchungen_offen_n', n)}</a>`; };
function pvDrawer(p, title, i = '') {
  const d = $('#drawer'), items = p.items || [], n = Math.max(items.length, p.bookings || p.open || 0);          // the list ends after 300
  if (drawerAgain('pv|' + i + '|' + title)) return;          // a second click on the same: closed, not opened again
  d.innerHTML = `<button class="close icon">✕</button><h2>${esc(title)}</h2><div data-ex="drawer.preview"><div class="note">${tn('pv_n_offen', n)} · <a href="#bookings" id="pv-go">${t('pv_zur_freigabe')}</a></div>`
    + `<div class="wrap auto dr-wrap"><table class="plain small dr-tx"><colgroup><col class="c-d"><col><col class="c-a"></colgroup><tbody>`
    + items.map(x => `<tr><td>${FD(x.date)}</td><td>${esc(x.account.split(' / ').pop())}<div class="muted">${esc(x.purpose)}${x.older ? ` <span class="tag">${t('aelter')}</span>` : ''}</div></td><td class="num">${F(x.amount)}</td></tr>`).join('')
    + `</tbody></table></div></div>`;
  d.classList.add('open'); $('.close', d).onclick = closeDrawer; $('#pv-go', d).onclick = () => closeDrawer();
}
// target, actual and difference of every rule, from /api/rules/preview (the configuration as edited, nothing is saved)
function rulesPreviewShow(rp, r) {
  const eur = v => `${F(v)} €`;
  RPV.list = [];
  $$('.pv, .r-pv', rp).forEach(x => { x.innerHTML = ''; });
  for (const p of r.preview || []) {
    if (p.kind === 'loans') {
      const it = $$('#loans .item', rp)[p.i], el = it && $('.r-pv', it);
      if (el) el.innerHTML = p.bookings ? pvOpen(p, p.bookings) : `<span class="pv-ok">✓ ${t('aktuell')}</span>`;
      continue;
    }
    if (p.kind === 'mirror') {          // mirror: which way, how many mirrored, what is open (the i-th complete row, as saved)
      const accId = (r, c) => $(c, r).value.split('|')[0].trim();
      const rows = $$('#mirrors .gk-row', rp).filter(r => $('.g-a', r).value && $('.g-b', r).value);
      const row = (p.a && rows.find(r => accId(r, '.g-a') === p.a && accId(r, '.g-b') === p.b)) || rows[p.i], el = row && $('.pv', row);
      if (!el || !p.direction) continue;
      const nm = c => { const o = $(c, row).selectedOptions[0]; return o ? o.textContent.trim() : ''; };
      el.innerHTML = (p.direction === 'both' ? t('gk_beide') : t('gk_nur_in', esc(nm(p.direction === 'to_a' ? '.g-a' : '.g-b')))) + (p.mirrored ? ` · ${t('gk_gespiegelt_n', p.mirrored)}` : '') + ' · '
        + (p.open ? pvOpen(p, p.open) : `<span class="pv-ok">✓ ${t('aktuell')}</span>`);
      continue;
    }
    const card = $$('.co-card', rp).find(c => c.dataset.b === String(p.area));
    const el = card && p.kind === 'participation' ? $('[data-pv="b"]', card) : null;
    if (!el || p.soll == null) continue;
    const ok = !p.open;
    // target with its calculation (quiet), actual; no difference -- what is to book is listed under Auto bookings
    const b = p.kind === 'participation' ? companyAreas().find(x => String(x.id) === String(p.area)) : null;
    let h = `${t('soll')} <b>${eur(p.soll)}</b>` + (b && b.share != null ? ` <span class="pv-calc">${t('co_formel', pctText(b.share), eur(p.source))}</span>` : '')
      + ` · ${t('ist')} ${eur(p.ist)}` + (ok ? ` · <span class="pv-ok">✓ ${t('aktuell')}</span>` : '');
    if (p.open) h += ` · ${pvOpen(p, p.open)}`;
    if ((p.unknown || []).length) h += ` · <span class="pv-unk">${t('monate_unbekannt_0', p.unknown.join(', '))}</span>`;
    el.innerHTML = h;
  }
  showFindings($('#rules-warn', rp), (r.warnings || []).map(w => ({severity: 'warning', text: w})));
}
// a rule as one collapsible row: name, what it books into, what is open, whether it is on; the details below
const refName = ref => String(ref || '').split(' | ').slice(1).join(' | ') || '';
// a rule the assistant made or changed: marked until you confirm it (its bookings wait for approval until then)
const reviewMark = r => r && r.review ? `<span class="pill warn rv-pill">${t('regel_ki_pruefen')}</span><button class="small secondary rv-ok" type="button" title="${esc(t('regel_bestaetigen_tip'))}">${t('regel_bestaetigen')}</button>` : '';
function ruleShell(i, name, target, on, open, body, review) {
  return `<details class="item rule" data-i="${i}"${review ? ' data-review="1"' : ''}${open ? ' open' : ''}><summary><span class="r-name">${esc(name || t('ohne_namen'))}</span><span class="r-target small muted">${target ? '→ ' + esc(target) : ''}</span><span class="r-pv small"></span>${on ? '' : `<span class="pill neutral">${t('aus')}</span>`}${reviewMark({review})}</summary>`
    + `<div class="rule-body">${body}<div class="rule-foot"><button class="ghost small del">${t('regel_entfernen')}</button></div></div></details>`;
}
function loanForm(l, i) {
  const z = l.interest || {}, b = l.booking || {}, e = l.detection || {};
  const satz = (z.rate_list || []).map(s => `${s.from_date}: ${s.percent}`).join('; ');
  const f = (label, key, ctl, cls = '') => `<label class="${cls}">${label}${hq(key)}</label><div class="${cls}">${ctl}</div>`;
  const g = title => `<div class="fg full">${title}</div>`;
  return ruleShell(i, l.name, refName(l.loan_account), l.active !== false, l._new, `<div class="form${z.rate_list ? '' : ' no-zins'}">`
    + f(t('name'), 'h_l_name', `<input type="text" class="f-name" value="${esc(l.name || '')}">`)
    + f(t('l_aktiv'), 'h_l_aktiv', `<label class="chk"><input type="checkbox" class="f-aktiv" ${l.active === false ? '' : 'checked'}></label>`)
    + g(t('fg_konten'))
    + f(t('l_darlehenskonto'), 'darlehen_konto', acctPick('f-konto', l.loan_account, onlyManual, t('waehlen')))
    + f(t('l_zahlungen_von'), 'darlehen_quelle', acctPick('f-quelle', (l.source_accounts || [])[0], onlyLeaves, t('waehlen')))
    + f(t('art'), 'h_l_art', `<select class="f-art"><option value="liability" ${l.kind !== 'forderung' ? 'selected' : ''}>${t('verbindlichkeit_ich_zahle')}</option><option value="forderung" ${l.kind === 'forderung' ? 'selected' : ''}>${t('forderung_ich_erhalte')}</option></select>`)
    + g(t('fg_erkennen'))
    + f(t('l_gegen_iban'), 'darlehen_iban', `<input type="text" class="f-iban" value="${esc(e.counter_iban || '')}" placeholder="${t('de_iban_des_darlehensgebers_nehmers')}">`)
    + f(t('oder_text_enthaelt'), 'h_l_text', `<input type="text" class="f-text" value="${esc((e.text_contains || []).join('; '))}" placeholder="${t('z_b_darlehen_mustermann_wenn')}">`)
    + f(t('ausschliessen_wenn_text_enthaelt'), 'h_l_excl', `<input type="text" class="f-excl" value="${esc((e.exclude_text || []).join('; '))}" placeholder="${t('z_b_nebenkosten_kaution')}">`)
    + g(t('fg_zinsen'))
    + f(t('l_zinsmodell'), 'zinsmodell', `<select class="f-modell"><option value="yearly_base" ${z.model !== 'remaining_debt_monthly' && z.rate_list ? 'selected' : ''}>${t('jahresbasis_satz_stand_31_12')}</option><option value="remaining_debt_monthly" ${z.model === 'remaining_debt_monthly' ? 'selected' : ''}>${t('restschuld_monatlich_satz_12_stand')}</option><option value="" ${!z.rate_list ? 'selected' : ''}>${t('keine_zinsen_nur_spiegeln')}</option></select>`)
    + f(t('l_zinssaetze'), 'rate_list', `<input type="text" class="f-satz" value="${esc(satz)}" placeholder="2025-11-20: 3,3; 2027-01-01: 3,0">`, 'zo')
    + f(t('zinsbuchung'), 'h_l_zinstag', `<select class="f-tag"><option value="with_payment" ${z.booking_day !== 'ultimo' ? 'selected' : ''}>${t('am_tag_der_rate_sonst')}</option><option value="ultimo" ${z.booking_day === 'ultimo' ? 'selected' : ''}>${t('ultimo')}</option></select>`, 'zo')
    + f(t('l_zinsbasis'), 'base_override', `<input type="text" class="f-basis" value="${esc(Object.entries(z.base_override || {}).map(([k, v]) => k + '=' + v).join('; '))}" placeholder="2026=160000">`, 'zo')
    + g(t('fg_buchung'))
    + f(t('l_ab'), 'h_l_ab', `<input type="date" class="f-ab" value="${esc(l.from_date || '')}">`)
    + f(t('gegenpartei'), 'h_l_gp', `<input type="text" class="f-gp" value="${esc(b.counterparty || '')}">`)
    + f(t('kategorie_tilgung'), 'h_l_kt', `<select class="f-kt">${catOptions(b.category_repayment)}</select>`)
    + f(t('kategorie_zinsen'), 'h_l_kz', `<select class="f-kz">${catOptions(b.category_interest)}</select>`, 'zo')
    + `</div>`, !!l.review);
}
function catOptions(selected) {
  const leaves = S.KATS.filter(k => !k.group);
  return `<option value="">${t('keine_2')}</option>` + leaves.map(k => `<option value="${esc(k.name)}" ${k.name === selected ? 'selected' : ''}>${esc(CP(k.path))}</option>`).join('') + (selected && !leaves.some(k => k.name === selected) ? `<option value="${esc(selected)}" selected>${t('0_nicht_in_moneymoney', esc(selected))}</option>` : '');
}
// one interest rate as typed: "2026-01-01: 3,3", "01.01.2026: 3,3" (also without the colon, with %) or a rate alone ("3,3": from
// the start) -- anything else is not read (saving stops with a message instead of booking another rate)
function rateIn(x) {
  const m = String(x).trim().match(/^(?:(\d{4})-(\d{1,2})-(\d{1,2})|(\d{1,2})\.(\d{1,2})\.(\d{4}))?\s*[:=]?\s*(-?\d+(?:[.,]\d+)?)\s*%?$/);
  if (!m) return {ok: false, text: String(x).trim()};
  const [y, mo, d] = m[1] ? [m[1], m[2], m[3]] : m[6] ? [m[6], m[5], m[4]] : ['', '', ''];
  const iso = y ? `${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}` : '', dt = iso ? new Date(iso + 'T00:00:00Z') : null;
  if (iso && (Number.isNaN(dt.getTime()) || dt.toISOString().slice(0, 10) !== iso)) return {ok: false, text: String(x).trim()};          // 31.02.2026: no day
  return {ok: true, from_date: iso, percent: parseFloat(m[7].replace(',', '.'))};
}
function collectRules(strict) {
  // strict (saving): an amount that is no number stops it with a message -- it is not saved as 0
  const cfg = JSON.parse(JSON.stringify(S.CFG));
  const lst = s => s.split(';').map(x => x.trim()).filter(Boolean);
  const amount = x => { const n = numIn(x); if (n == null || Number.isNaN(n)) { if (strict) throw new Error(t('zahl_unlesbar', String(x == null ? '' : x).trim())); return 0; } return n; };
  cfg.loans = $$('#loans .item').map(it => {
    const v = s => $(s, it).value.trim();
    const satz = lst(v('.f-satz')).map(rateIn).filter(r => { if (!r.ok && strict) throw new Error(t('zinssatz_unlesbar', r.text)); return r.ok; }).map(r => ({from_date: r.from_date, percent: r.percent}));
    const basis = {}; lst(v('.f-basis')).forEach(x => { const [k, val] = x.split('='); basis[k.trim()] = amount(val); });
    const modell = v('.f-modell');
    const l = { name: v('.f-name'), active: $('.f-aktiv', it).checked, loan_account: v('.f-konto'), source_accounts: v('.f-quelle') ? [v('.f-quelle')] : [],
      detection: { counter_iban: v('.f-iban').replace(/\s/g, '').toUpperCase(), text_contains: lst(v('.f-text')), exclude_text: lst(v('.f-excl')) },
      kind: v('.f-art'), from_date: v('.f-ab'),
      booking: { counterparty: v('.f-gp') || v('.f-name'), category_repayment: v('.f-kt') || null, category_interest: v('.f-kz') || null } };
    if (modell) l.interest = { model: modell, rate_list: satz, booking_day: v('.f-tag'), base_override: basis };
    if (it.dataset.review) l.review = true;          // from the assistant, not confirmed yet
    return l;
  });
  cfg.companies = $$('#companies .co-card').map(c => ({ area: c.dataset.b, participation: $('.c-bet', c).value,
    retroactive_from: backValue(c), cycle: $('.c-takt', c).value, threshold: parseFloat($('.c-sw', c).value) || 0.01, counterparty: $('.c-gp', c).value.trim(),
    ...(c.dataset.review ? {review: true} : {}) }))
    .filter(g => g.participation || g.counterparty);          // a counterparty alone: the name on mirrored bookings
  cfg.account_mirrors = $$('#mirrors .gk-row').map(r => Object.assign({a: $('.g-a', r).value, b: $('.g-b', r).value, from_date: backValue(r)}, r.dataset.kat ? {category: r.dataset.kat} : {}, r.dataset.review ? {review: true} : {}))
    .filter(m => m.a && m.b);
  return cfg;
}
function showFindings(el, befunde, extra, kind = 'hint') {
  el.innerHTML = (extra ? `<div class="${kind}">${esc(extra)}</div>` : '') + (befunde || []).map(f => `<div class="${f.severity}">${esc(f.text)}</div>`).join('');
}
// After a change of address or port the service restarts. Same port: wait for the new process (other instance id), then
// reload. New port: the page may only talk to its own address, so wait until the old process is gone, give the new one a
// moment to listen, then open the same page under the new address (the old one no longer answers).
async function restartTo(port, before) {
  toast(t('kontor_startet_neu'), 60000);
  const samePort = String(port) === (location.port || (location.protocol === 'https:' ? '443' : '80'));
  const target = `${location.protocol}//${location.hostname}:${port}/${location.hash}`;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const leave = () => { if (new URL(target).hostname === location.hostname) location.href = target; };      // the same Mac, another port: nowhere else
  for (let i = 0; i < 60; i++) {
    await sleep(1000);
    let j = null;
    try { const r = await fetch('/api/session', {credentials: 'same-origin', cache: 'no-store', headers: {'X-Kontor-Net': 'direct'}}); j = r.ok ? await r.json() : {}; } catch (e) { j = null; }
    if (samePort && j && j.instance && j.instance !== before) { location.reload(); return; }
    if (!samePort && (!j || (j.instance && j.instance !== before))) { await sleep(2500); leave(); return; }
  }
  if (samePort) location.reload(); else leave();
}
async function saveConfig(cfg, findingsEl, trotzdem, extra) {
  try {
    const r = await api('/api/config', Object.assign({config: cfg, anyway: !!trotzdem, seen: CFG_DRAWN}, extra || {}), 'PUT');
    DIRTY.on = false; CFG_DRAWN = cfgCopy(r.config);
    const probleme = (r.findings || []).filter(f => f.severity !== 'ok');      // erfolgreich gepruefte Verweise nicht einzeln auflisten
    S.CFG = r.config;
    if (r.restart) { restartTo(r.port, r.instance); return true; }
    if (((r.config.ui || {}).language || 'de') !== LANG) { setLang(r.config.ui.language); return true; }
    showFindings(findingsEl, probleme, t('gespeichert_2') + (S.KONTEN.length ? '' : t('noch_nicht_gegen_moneymoney_geprueft')), 'ok'); toast(t('gespeichert'));
    S.STATUS = await api('/api/status'); statusMini();
    return true;
  } catch (e) {
    if (e.data && e.data.findings) { showFindings(findingsEl, e.data.findings.filter(f => f.severity !== 'ok'), t('nicht_gespeichert_fehler_beheben_oder'), 'error'); findingsEl.insertAdjacentHTML('beforeend', `<div class="actions"><button id="save-anyway" class="danger small">${t('trotzdem_speichern')}</button></div>`); $('#save-anyway').addEventListener('click', () => saveConfig(cfg, findingsEl, true, extra)); }
    else if (e.data && e.data.stale) { showFindings(findingsEl, [], e.message, 'error'); findingsEl.insertAdjacentHTML('beforeend', `<div class="actions"><button class="small secondary cfg-reload">${t('neu_laden')}</button></div>`); $('.cfg-reload', findingsEl).addEventListener('click', async () => { DIRTY.on = false; await loadAll(); route(); }); }
    else toast(t('fehler_3') + e.message, 5000);
    return false;
  }
}

// ---------------------------------------------------------------- Kategorien
const subTabs = (base, items) => `<div class="tabs">${items.map(([k, l]) => `<button data-next="#${base}${k ? '/' + k : ''}" class="${S.sub === k ? 'on' : ''}">${l}</button>`).join('')}</div>`;
async function vKategorien() {
  // Zuordnen -- tabs: Offen (what has no category in MoneyMoney yet) · Regeln für MoneyMoney (proposals) · Eingetragen (what
  // Kontor entered in MoneyMoney, to take back). Where a category counts in the cash flow is a setting: Cashflow-Positionen.
  const offen = ((S.DATA && S.DATA.categories || {}).total || {}).without;
  const body = S.sub === 'rules' ? await vRegelVorschlaege() : S.sub === 'written' ? await vEingetragen() : await vZuordnen();
  const nr = KZ.rules ?? (KZ.open || {}).rule_proposals;
  const tabs = subTabs('categories', [['', t('kz_tab_offen') + (offen ? ` (${offen})` : '')], ['rules', t('regeln_fuer_moneymoney') + (nr ? ` (${nr})` : '')], ['written', t('kz_tab_eingetragen') + (KZ.written ? ` (${KZ.written})` : '')]]);
  return `<div class="tabs-row">${tabs}<a class="small tabs-aside" href="#accounts/positions" title="${esc(t('kz_zu_positionen_tip'))}">${t('cashflow_positionen')}</a></div>` + body;
}
// Eingetragen: what Kontor entered in MoneyMoney (newest first); taken back -- one or many -- MoneyMoney gets the category it had
// before. Only at the Mac, only where MoneyMoney still shows Kontor's category.
async function vEingetragen() {
  const r = KZ.w = await api('/api/categories/written'); KZ.written = r.total;
  KZ.wsel = new Set([...(KZ.wsel || [])].filter(i => r.items.some(x => x.id === i && x.undo)));
  let h = `<div class="note">${t('kz_eingetragen_note', hq('kz_eingetragen'))}</div>`;
  if (!r.items.length) return h + `<div class="card" data-ex="categories.written"><div class="v s">${t('kz_eingetragen_leer')}</div></div>`;
  const can = r.items.filter(x => x.undo).length, cat = p => p ? esc(CP(p)) : `<span class="muted">${t('ohne_kategorie_2')}</span>`;
  h += `<div class="toolbar"><span class="small muted">${tn('kz_eingetragen_n', r.total, r.total)}</span><span class="sp"></span><button id="kw-undo" class="secondary" disabled ${r.local ? '' : t('disabled_title_nur_am_mac')}>${t('kz_rueckgaengig')}</button></div>`;
  h += `<div class="wrap auto kw-wrap" data-ex="categories.written"><table class="plain small kw-table"><thead><tr><th><input type="checkbox" id="kw-all" aria-label="${t('alle_2')}" ${can && r.local ? '' : 'disabled'}></th><th>${t('kz_eingetragen_am')}</th><th>${t('datum')}</th><th>${t('konto_2')}</th><th>${t('name')}</th><th class="num">${t('betrag')}</th><th>${t('kz_vorher')}</th><th>${t('kz_eingetragen_col')}</th><th></th></tr></thead><tbody>`
    + r.items.map(x => `<tr class="${x.undo ? '' : 'off'}" data-id="${x.id}"><td><input type="checkbox" class="kw-sel" data-id="${x.id}" ${x.undo && r.local ? '' : 'disabled'} ${KZ.wsel.has(x.id) ? 'checked' : ''}></td>`
      + `<td style="white-space:nowrap">${esc(FDT(x.time || ''))}</td><td style="white-space:nowrap">${x.date ? FD(x.date) : '–'}</td><td>${esc(x.account || '–')}</td><td>${esc(x.name || '–')}</td>`
      + `<td class="num ${x.amount < 0 ? 'neg' : 'pos'}">${x.amount == null ? '–' : F(x.amount)}</td><td>${cat(x.old)}</td><td>${cat(x.new)}</td>`
      + `<td>${x.undo ? '' : `<span class="tag tipped" tabindex="0" data-tip="${esc(t(x.date ? 'kz_geaendert_tip' : 'kz_nicht_gelesen_tip'))}">${t(x.date ? 'kz_geaendert' : 'kz_nicht_gelesen')}</span>`}</td></tr>`).join('')
    + '</tbody></table></div>';
  return h;
}
function bindEingetragen(main) {
  const btn = $('#kw-undo', main); if (!btn) return;
  const upd = () => { const n = KZ.wsel.size; btn.disabled = !n || !KZ.w.local; btn.textContent = n ? tn('kz_rueckgaengig_n', n, n) : t('kz_rueckgaengig');
    const all = $('#kw-all', main), m = $$('.kw-sel:not(:disabled)', main).length; if (all) { all.checked = n > 0 && n === m; all.indeterminate = n > 0 && n < m; } };
  $$('.kw-sel', main).forEach(cb => cb.addEventListener('change', () => { const i = +cb.dataset.id; if (cb.checked) KZ.wsel.add(i); else KZ.wsel.delete(i); upd(); }));
  const all = $('#kw-all', main); if (all) all.addEventListener('change', () => { $$('.kw-sel:not(:disabled)', main).forEach(cb => { cb.checked = all.checked; const i = +cb.dataset.id; if (all.checked) KZ.wsel.add(i); else KZ.wsel.delete(i); }); upd(); });
  btn.addEventListener('click', async () => {
    const ids = [...KZ.wsel]; if (!ids.length || !confirm(tn('kz_rueckgaengig_frage', ids.length, ids.length))) return;
    btn.classList.add('busy'); btn.disabled = true;
    try {
      const r = await api('/api/categories/undo', {ids, wait: true}); KZ.wsel = new Set();
      toast(tn('kz_rueckgaengig_ok', r.undone, r.undone) + (r.changed ? ' · ' + tn('kz_rueckgaengig_geaendert', r.changed, r.changed) : '') + (r.error ? ' · ' + tn('kz_rueckgaengig_fehler', r.error, r.error) : ''), 7000);
      await loadAll(); route();
    } catch (e) { toast(e.message, 7000); btn.classList.remove('busy'); upd(); }
  });
  upd();
}
// Cashflow-Positionen: Kontor's fixed outline; each of MoneyMoney's categories counts in one position (Kontor proposes by
// name, a choice counts for the categories below it too). A property's categories have their own rows.
const POS_SEC = {income: 'einnahmen', expenses: 'ausgaben', investing: 'sek_investitionen', financing: 'finanzierung'};
const posLabel = (k, firma) => t(firma && k === 'housing' ? 'pos_housing_g' : `pos_${k}`);   // one name: a company's where the category is a company's
const OBJ_OUT = ['saving', 'repayment', 'loan_interest', 'ignore'];            // pos_<key>: every position has its text (tests: Positions)
async function vPositionen() {
  const d = await api('/api/categories/positions');
  if (!d.categories.length) return `<div class="card" data-ex="accounts.positions"><div class="d">${esc(d.hint || t('noch_keine_kategorien_geladen_abgleich'))}</div></div>`;
  const secs = []; for (const [k, sec] of d.positions) { if (k === 'ignore') continue; let g = secs.find(x => x[0] === sec); if (!g) secs.push(g = [sec, []]); g[1].push(k); }
  const opts = (sel, firma) => `<option value=""></option>` + secs.map(([sec, ks]) => `<optgroup label="${esc(t(POS_SEC[sec] || sec))}">${ks.map(k => `<option value="${k}" ${sel === k ? 'selected' : ''}>${esc(posLabel(k, firma))}</option>`).join('')}</optgroup>`).join('')
    + `<optgroup label="${esc(t('sonstiges'))}">${['transfer', 'ignore'].map(k => `<option value="${k}" ${sel === k ? 'selected' : ''}>${esc(posLabel(k))}</option>`).join('')}</optgroup>`;
  // a property's categories have its own rows (rent, costs); only saving, financing or leaving out takes them elsewhere
  const objOpts = sel => `<option value=""></option>` + OBJ_OUT.map(k => `<option value="${k}" ${sel === k ? 'selected' : ''}>${esc(posLabel(k))}</option>`).join('');
  let h = `<div data-ex="accounts.positions"><div class="toolbar"><a class="small" href="#cashflow">${t('zum_cashflow')}</a><span class="sp"></span><button id="kp-save" disabled>${t('speichern')}</button></div>
    ${kbCard()}<div class="wrap kp-wrap" data-ex="accounts.positions.table"><table class="plain kp-table"><thead><tr><th>${t('kategorie_in_moneymoney')}</th><th class="num kp-n">${t('umsaetze_2')}</th><th class="num kp-n">${t('letzte_12_monate')}</th><th class="kp-arrow"></th><th>${t('cashflow_position')} ${hq('position_kat')}</th><th>${t('zielkonto')} ${hq('zielkonto')}</th></tr></thead><tbody>`;
  // categories Kontor does not know and you did not place, with payments between your areas: those count as contributions or
  // withdrawals, not under the "other" shown here -- named, so that a later choice changing the figures is no surprise
  const npath = x => String(x || '').split(/ › |\\| \/ /).map(p => p.trim()).filter(Boolean).join(' / '), UNS = {};
  for (const b of Object.values((S.DATA && S.DATA.areas) || {})) for (const [c, v] of Object.entries(((b || {}).cashflow || {}).uncertain || {})) UNS[npath(c)] = Math.max(UNS[npath(c)] || 0, Math.abs(v));
  d.categories.forEach((r, i) => {
    const parent = (d.categories[i + 1] || {}).depth > r.depth, own = r.own || '', uns = !own ? UNS[npath(r.path)] : null;
    h += `<tr data-p="${esc(r.path)}" data-v="${esc(r.proposal)}" data-v2="${esc((r.proposal_also || []).join(','))}" data-init="${esc(own)}" data-konto="${esc(r.account)}" data-own="${r.count ? 1 : 0}" data-firma="${r.company ? 1 : ''}"><td style="padding-left:${10 + 18 * r.depth}px">${parent ? `<b>${esc(r.name)}</b>` : esc(r.name)}${uns != null ? ` <span class="tag warn tipped kp-uns" tabindex="0" data-tip="${esc(t('kp_unsicher_tip', F0(Math.abs(uns))))}">${t('kp_unsicher')}</span>` : ''}</td>
      <td class="num small kp-n">${r.count_all ? `<a href="#" class="kp-tx" data-tx="all">${r.count_all}</a>` : ''}</td><td class="num small kp-n ${r.sum_12m < 0 ? 'neg' : ''}">${r.sum_12m ? `<a href="#" class="kp-tx" data-tx="12m">${F0(r.sum_12m)}</a>` : ''}</td><td class="kp-arrow" aria-hidden="true">→</td>
      <td><select class="kp-pos"${r.property_name ? ` data-obj="${esc(r.property_name)}"` : ''}>${r.property_name ? objOpts(own) : opts(own, r.company)}</select></td>
      <td>${(() => { const at = autoTarget(r.path); return `<select class="kp-konto${at.miss && !r.account ? ' kp-miss' : ''}">${acctOptions(r.account, k => !k.group && (k.depot || k.role === 'term_investments' || k.role === 'cash' || k.role === 'participations' || k.role === 'real_estate')).replace(t('waehlen'), () => esc(at.text))}</select>`; })()}</td></tr>`;
  });
  return h + '</tbody></table></div>' + vAnlageEmpfaenger() + '</div>';
}
// what Kontor needs from your categories in MoneyMoney: per need, whether one of yours counts there (and which), else what to
// create -- updated as you change a position below; the why of each need in its tooltip
const KB_NEEDS = [['work_income', ['work_income']], ['capital_income', ['capital_income']], ['housing', ['housing']], ['living', ['living']],
  ['more', ['mobility', 'insurance', 'health', 'leisure', 'taxes']], ['saving', ['saving']], ['loans', ['repayment', 'loan_interest']],
  ['property', ['property']], ['property_buy', ['property_saving']], ['transfer', ['transfer']]];
let kbSeen = false;
function kbCard() {
  if (!kbSeen && setupOpen()) KEEP_OPEN.add('kp-kb');          // open while you set Kontor up (closed afterwards: as you left it)
  kbSeen = true;
  return `<details class="card kb" data-keep="kp-kb" data-ex="accounts.positions.needs"${keepOpen('kp-kb')}><summary>${t('kb_titel')} <span class="kb-sum small muted" id="kb-sum"></span></summary><div id="kb-body"></div></details>`;
}
// eff: [{path, eff (its position now), obj (a property's)}] -- from the table as it stands
function kbRefresh(eff) {
  const body = $('#kb-body'); if (!body) return;
  const at = new Map();
  for (const r of eff) { const k = r.obj ? (r.eff === 'saving' ? 'property_saving' : ['repayment', 'loan_interest', 'ignore'].includes(r.eff) ? r.eff : 'property') : r.eff;
    if (k) { if (!at.has(k)) at.set(k, []); at.get(k).push(r.path); } }
  const props = ((S.CFG || {}).real_estate || []).length > 0 || eff.some(r => r.obj);
  const needs = KB_NEEDS.filter(([k]) => props || !k.startsWith('property'));
  let ok = 0;
  const rows = needs.map(([k, ps]) => {
    const mine = ps.flatMap(p => at.get(p) || []), have = mine.length > 0, miss = ps.filter(p => !(at.get(p) || []).length);
    if (have) ok++;
    const names = mine.slice(0, 2).map(CP).join(', ') + (mine.length > 2 ? ' ' + t('kb_und_n', mine.length - 2) : '');
    const part = have && miss.length && ps.length > 1 ? ` · <span class="kb-miss">${esc(t('kb_fehlt_noch', miss.map(p => posLabel(p)).join(', ')))}</span>` : '';
    const tip = t(`kb_${k}_tip`) + (have ? '' : ' ' + t('kb_anlegen', t(`kb_${k}_bsp`)));
    return `<tr class="${have ? 'kb-ok' : ''}"><td><span class="kb-mark">${have ? '✓' : '○'}</span>${esc(t(`kb_${k}`))}<span class="hq" tabindex="0" data-tip="${esc(tip)}">?</span></td>`
      + `<td class="${have ? '' : 'muted'}">${have ? esc(names) + part : esc(t('kb_fehlt_bsp', t(`kb_${k}_bsp`)))}</td></tr>`;
  }).join('');
  body.innerHTML = `<table class="plain kb-table"><tbody>${rows}</tbody></table>`;
  const sum = $('#kb-sum'); if (sum) sum.textContent = t('kb_n_von', ok, needs.length);
}
// the target account a saving category gets by itself (from the recipients in the cash flow): not needed (transfers to your
// own accounts), found, or missing -- shown in its menu, so it is clear whether to choose
function autoTarget(path) {
  const lab = acctLabels(S.KONTEN || []), nm = u => lab.get(u) || (S.KONTEN.find(k => k.uuid === u) || {}).name || u;
  const recs = Object.values((S.DATA || {}).areas || {}).flatMap(d => ((d.cashflow || {}).saving_recipients || [])
    .filter(a => a.categories.some(c => c === path || c.startsWith(path + ' / '))));
  if (!recs.length) return {text: t('ziel_nicht_noetig'), miss: false};
  if (recs.some(a => !a.target && a.how !== 'external' && a.how !== 'mixed')) return {text: t('ziel_fehlt'), miss: true};
  const ts = [...new Set(recs.map(a => a.target).filter(Boolean))];
  return {text: ts.length === 1 ? t('automatisch_doppel', nm(ts[0])) : t('automatisch'), miss: false};
}
// Zielkonto je Empfänger: saving that arrives as a booking on none of your accounts (a depot kept by its balances, an account
// outside MoneyMoney) -- per area the account per recipient; Kontor proposes one where it is clear, it counts once chosen
function vAnlageEmpfaenger() {
  const areas = Object.entries((S.DATA || {}).areas || {}).filter(([, d]) => !d.error && ((d.cashflow || {}).saving_recipients || []).length);
  if (!areas.length) return '';
  const cfg = ((S.CFG || {}).cashflow || {}).recipient_to_account || {}, lab = acctLabels(S.KONTEN || []);
  const nm = u => lab.get(u) || (S.KONTEN.find(k => k.uuid === u) || {}).name || u;
  const open = areas.reduce((n, [id, d]) => n + d.cashflow.saving_recipients.filter(a => a.how === '' && !(cfg[id] || {})[a.key]).length, 0);
  let h = `<div data-ex="accounts.positions.recipients"><h2 class="kp-h">${t('anl_titel')} ${hq('anl_empfaenger')}${open ? ` <span class="pill warn">${esc(tn('anl_n_offen', open))}</span>` : ''}</h2>`;
  for (const [id, d] of areas) {
    const KF = d.cashflow, mine = cfg[id] || {};
    if (areas.length > 1) h += `<h3 class="kp-h3">${esc(BN(id))}</h3>`;
    h += `<div class="wrap kp-wrap"><table class="plain kp-table ka-table"><thead><tr><th>${t('empfaenger')}</th><th class="kp-n">${t('kategorie')}</th><th class="num kp-n">${t('umsaetze_2')}</th><th class="num kp-n">${t('summe_label')}</th><th class="kp-arrow"></th><th>${t('zielkonto')}</th></tr></thead><tbody>`;
    for (const a of KF.saving_recipients) {
      const own = mine[a.key] || '', ownId = own === 'external' ? '' : own.split('|')[0].trim();
      const ziele = new Set([...(KF.saving_targets || []), ownId].filter(Boolean));
      const auto = a.auto_how === 'mixed' ? t('anl_nach_kategorie') : a.auto_target ? nm(a.auto_target) : null;
      const opts = acctOptions(ownId, k => ziele.has(k.uuid)).replace(t('waehlen'), () => esc(auto ? t('automatisch_doppel', auto) : t('bitte_waehlen')))
        + `<option value="external" ${own === 'external' ? 'selected' : ''}>${t('anl_extern')}</option>`;
      const prop = a.proposal && !own ? ` <button class="small secondary ka-take" data-v="${esc(a.proposal)}">${esc(t('vorschlag_0', nm(a.proposal)))}</button>` : '';
      const stale = own && own !== 'external' && a.how !== 'recipient' && S.KONTEN.some(k => k.uuid === ownId);   // in another area now: Kontor's choice applies
      h += `<tr data-area="${esc(id)}" data-key="${esc(a.key)}" data-init="${esc(own)}" class="${a.how === '' || (own && own !== 'external' && a.how !== 'recipient') ? 'ka-open' : ''}"${stale ? ` title="${esc(t('anl_nicht_im_bereich'))}"` : ''}><td>${esc(a.name)}${a.iban ? `<div class="small muted">${esc(a.iban)}</div>` : ''}</td>
        <td class="small kp-n">${a.categories.map(k => esc(CP(k))).join(', ')}</td><td class="num small kp-n"><a href="#" class="ka-tx" data-ids="${(a.ids || []).join(',')}">${a.count}</a></td><td class="num small kp-n ${a.sum < 0 ? 'neg' : ''}"><a href="#" class="ka-tx" data-ids="${(a.ids || []).join(',')}">${F0(a.sum)}</a></td>
        <td class="kp-arrow" aria-hidden="true">→</td><td><select class="ka-ziel">${opts}</select>${prop}</td></tr>`;
    }
    h += '</tbody></table></div>';
  }
  return h + '</div>';
}
function bindPositionen(main) {
  // the bookings behind a number: a category (all its bookings, or those of the last 12 months), a recipient's payments
  $$('.kp-table', main).forEach(tb => tb.addEventListener('click', e => {          // (the tables are new with every drawing)
    const a = e.target.closest('.kp-tx, .ka-tx'); if (!a) return; e.preventDefault();
    const tr = a.closest('tr');
    if (a.classList.contains('ka-tx')) { const ids = a.dataset.ids.split(',').filter(Boolean).map(Number); txPanel($('td', tr).firstChild.textContent.trim(), {ids}); return; }
    // as counted there: booked, with MoneyMoney's category; the twelve months up to today
    const p = tr.dataset.p, y = a.dataset.tx === '12m'; txPanel(CP(p), {kats: [p], counted: true, date_from: y ? yearAgo() : '', date_to: y ? isoToday() : ''});
  }));
  const rows = $$('.kp-table tr[data-p]', main); if (!rows.length) return;
  const by = Object.fromEntries(rows.map(r => [r.dataset.p, r]));
  const own = r => ($('.kp-pos', r) || {}).value || '';
  // without your choice: that of the nearest category above it, else Kontor's proposal
  const inherited = r => { const parts = r.dataset.p.split(' / '); for (let i = parts.length - 1; i > 0; i--) { const up = by[parts.slice(0, i).join(' / ')]; if (up && own(up)) return own(up); } return ''; };
  const auto = r => inherited(r) || r.dataset.v;
  // a category with subcategories and no choice of yours (here or above): each subcategory counts on its own -- shown so;
  // a choice of yours on it passes down to them
  const parents = new Set(rows.map(r => r.dataset.p.split(' / ')).filter(p => p.length > 1).flatMap(p => p.slice(1).map((_, i) => p.slice(0, i + 1).join(' / '))));
  const save = $('#kp-save', main);
  const acc = v => (v || '').split('|')[0].trim();               // an account by its id (a renamed account is no change)
  const upd = () => {
    rows.forEach(r => {
      const sel = $('.kp-pos', r); if (!sel) return;
      let a = auto(r);
      if (!sel.dataset.obj && parents.has(r.dataset.p) && !own(r) && !inherited(r)) a = '';
      // a property's category leaves its rows for interest or a repayment, or for saving or leaving out that you chose
      if (sel.dataset.obj && !(['repayment', 'loan_interest'].includes(a) || (inherited(r) && OBJ_OUT.includes(a)))) a = '';
      const eff = own(r) || a;
      const also = !inherited(r) && a === r.dataset.v && r.dataset.v2 ? r.dataset.v2.split(',') : [];       // another area counts it the other way round
      sel.options[0].textContent = sel.dataset.obj && !a ? t('automatisch_0', t('immobilie_0', sel.dataset.obj)) : a ? t('automatisch_0', [posLabel(a, r.dataset.firma), ...also.map(k => posLabel(k))].join(' / ')) : t('automatisch_unter');
      r.classList.toggle('kp-own', !!own(r));
      const k = $('.kp-konto', r); k.classList.toggle('hidden', eff !== 'saving');      // counts for the categories below it too
      r._eff = eff;
    });
    kbRefresh(rows.filter(r => +r.dataset.own).map(r => ({path: r.dataset.p, eff: r._eff, obj: ($('.kp-pos', r) || {dataset: {}}).dataset.obj})));
    const dirty = rows.some(r => own(r) !== r.dataset.init || ($('.kp-konto', r) && acc($('.kp-konto', r).value) !== acc(r.dataset.konto))) || kaDirty().length > 0;
    save.disabled = !dirty; DIRTY.on = dirty;
  };
  // the account per recipient (Zielkonto je Empfänger): a choice of its own, or Kontor's proposal taken over
  const ka = $$('.ka-table tr[data-key]', main), kaVal = r => { const v = $('.ka-ziel', r).value; return v === 'external' ? v : acc(v); };
  const kaDirty = () => ka.filter(r => kaVal(r) !== (r.dataset.init === 'external' ? 'external' : acc(r.dataset.init)));
  const upd2 = () => { ka.forEach(r => r.classList.toggle('kp-own', !!$('.ka-ziel', r).value)); upd(); };
  $$('.kp-table', main).forEach(tb => tb.addEventListener('change', upd2));
  $$('.ka-take', main).forEach(b => b.addEventListener('click', () => {
    const sel = $('.ka-ziel', b.closest('tr')), o = [...sel.options].find(x => acc(x.value) === b.dataset.v);
    if (o) { sel.value = o.value; b.remove(); upd2(); }
  }));
  upd2();
  save.onclick = async () => {
    const positionen = {}, konten = {};
    rows.forEach(r => { if ($('.kp-pos', r) && own(r) !== r.dataset.init) positionen[r.dataset.p] = own(r); const k = $('.kp-konto', r); if (k && acc(k.value) !== acc(r.dataset.konto)) konten[r.dataset.p] = k.value; });
    const empfaenger = {};
    kaDirty().forEach(r => { (empfaenger[r.dataset.area] = empfaenger[r.dataset.area] || {})[r.dataset.key] = $('.ka-ziel', r).value; });
    save.disabled = true;
    try { const r = await api('/api/categories/positions', {positions: positionen, accounts: konten, recipient: empfaenger}); S.CFG = r.config; DIRTY.on = false; toast(t('gespeichert')); afterRebuild(r); route(); }
    catch (e) { save.disabled = false; toast(e.message, 6000); }
  };
}

// ---------------------------------------------------------------- Zuordnen: Kategorien kommen aus MoneyMoney, Kontor trägt dort ein
const KZ = {year: '', area: '', min: '', expanded: {}, aus: {}, open: null, rules: null, written: null, w: null, wsel: new Set()};
async function assignCats(ids, kat, extra = {}) {
  // Kontor trägt die Kategorie in MoneyMoney ein (vorher geprüft), in Teilen zu höchstens 2000 Umsätzen. Steht dort schon eine
  // andere (nicht von Kontor gesetzte): nachfragen, ob sie ersetzt werden soll – sonst bleibt sie (MoneyMoney ist maßgeblich).
  const KEYS = ['written', 'later', 'error', 'waiting', 'mac_only', 'unreachable'];
  const mm = Object.fromEntries(KEYS.map(k => [k, 0])), f = [];
  let r = {count: 0};
  for (let i = 0; i < ids.length; i += 2000) {
    r = await api('/api/categories/assign', Object.assign({ids: ids.slice(i, i + 2000), category: kat}, extra));
    for (const k of KEYS) mm[k] += (r.mm || {})[k] || 0;
    f.push(...((r.mm || {}).foreign || []));
  }
  if (f.length) {
    const bsp = [...new Set(f.map(x => x.mm))].slice(0, 3).map(x => '„' + esc(x) + '“').join(', ');
    const v = await choose(tn('mm_fremd_frage', f.length, bsp, esc(kat)), [['overwrite', t('in_moneymoney_ueberschreiben')]]);
    if (v) {
      // ersetzt wird nur, was die Frage gezeigt hat (steht dort inzwischen etwas anderes, bleibt es)
      for (let i = 0; i < f.length; i += 2000) {
        const part = f.slice(i, i + 2000);
        const r2 = (await api('/api/categories/assign', {ids: part.map(x => x.id), category: kat, mode: v, confirmed: Object.fromEntries(part.map(x => [x.id, x.mm]))})).mm || {};
        for (const k of KEYS) mm[k] += r2[k] || 0;
        mm.error += (r2.foreign || []).length;
      }
    } else mm.kept = f.length;
  }
  return Object.assign({}, r, {count: ids.length, mm});
}
function assignMsg(r) {
  // Rückmeldung: in MoneyMoney eingetragen · beim nächsten Abgleich am Mac · behalten · abweichend
  const m = r.mm || {}, p = [];
  if (m.written) p.push(t('0_in_moneymoney_gesetzt', m.written));
  if (m.later) p.push(t('0_beim_naechsten_abgleich', m.later));
  if (m.kept) p.push(tn('0_moneymoney_behalten', m.kept));
  if (m.mac_only) p.push(tn('n_nur_am_mac_aendern', m.mac_only));
  if (m.unreachable) p.push(tn('n_mm_nicht_erreichbar', m.unreachable));
  if (m.error) p.push(t('0_in_moneymoney_abweichend', m.error));
  if (m.waiting) p.push(t('0_in_moneymoney_abweichend', m.waiting));
  return p.join(' · ') || t('nichts_eingetragen');
}
// Kategorien zum Zuordnen: die aus MoneyMoney (keine Ordner, nicht „Unkategorisiert“)
const katList = id => `<datalist id="${id}">${(S.KATS || []).filter(k => !k.group && !k.default).map(k => `<option value="${esc(CP(k.path))}">`).join('')}</datalist>`;
// alle gewählten Umsätze mit Vorschlag: [id, Kategorie] (der Vorschlag gilt je Umsatz, nicht je Gegenpartei)
const vorschlagIds = off => off.groups.flatMap(g => g.ids.filter(i => !(KZ.aus[g.key] || new Set()).has(i) && g.proposals[i]).map(i => [i, g.proposals[i]]));
async function vZuordnen() {
  if (!S.DATA) return noData;
  const off = await api(`/api/categories/unassigned?year=${KZ.year}&min=${KZ.min}`);
  KZ.open = off; KZ.rules = null; KZ.written = off.written;
  for (const g of off.groups) if (KZ.aus[g.key]) { const ids = new Set(g.ids); for (const i of [...KZ.aus[g.key]]) if (!ids.has(i)) KZ.aus[g.key].delete(i); }
  const years = Object.keys((S.DATA.categories || {}).years || {}).sort().reverse(), can = true;          // assigning is the release (from the iPhone: entered at the next sync at the Mac)
  const mitVorschlag = vorschlagIds(off);
  // the areas you categorise: the others (a company with countless bookings, say) stay out of the list and of the count
  const ohne = new Set(off.skipped || S.CFG.assign_without || []), areas = Object.keys(S.DATA.areas || {});
  const chips = areas.length > 1 ? `<div class="kz-areas" role="group" aria-label="${esc(t('kz_bereiche'))}" title="${esc(t('kz_bereiche_tip'))}">${areas.map(k => `<label class="lc-chip"><input type="checkbox" data-area="${esc(k)}" ${ohne.has(String(k)) ? '' : 'checked'}>${esc(BN(k))}</label>`).join('')}</div>` : '';
  let h = `<div class="toolbar">${chips}
    <select id="kz-jahr"><option value="">${t('alle_jahre')}</option>${years.map(y => `<option ${KZ.year === y ? 'selected' : ''}>${y}</option>`).join('')}</select>
    <label class="chk small">${t('ab')} <input type="number" id="kz-min" value="${esc(KZ.min)}" placeholder="0" style="width:80px"> €</label>
    <span class="sp"></span>${can && mitVorschlag.length ? `<button id="kz-alle" class="secondary small">${t('alle_vorschlaege_n', mitVorschlag.length)}</button>` : ''}</div>
    <div class="note">${tn('n_ohne_kategorie_gruppen', off.open, hq('zuordnen'))}</div>` + katList('kz-kats');
  if (off.waiting) h += `<div class="banner info">${tn('n_warten_auf_mac', off.waiting, off.waiting)}</div>`;
  if (!off.groups.length) return h + `<div class="card" data-ex="categories.open"><div class="v s">${t('nichts_offen_2')}</div><div class="d">${t('alle_umsaetze_haben_eine_kategorie')}</div></div>`;
  h += '<div class="list" data-ex="categories.open">';
  for (const g of off.groups) {
    const open = KZ.expanded[g.key], aus = KZ.aus[g.key] || new Set(), n = g.ids.filter(i => !aus.has(i)).length, mixed = !g.proposal && Object.keys(g.proposals).length > 0;
    h += `<div class="item kz-group" data-key="${esc(g.key)}" data-ex="categories.open.group"><div class="grow">
      <div class="row tight"><b style="min-width:220px">${esc(g.name)}</b><span class="small muted">${esc(g.accounts.join(', '))}${g.iban ? ' · ' + esc(g.iban) : ''}</span><span class="tag kz-count">${n < g.count ? n + ' / ' : ''}${g.count}×</span><span class="num ${g.sum < 0 ? 'neg' : 'pos'}" style="font-weight:600">${F(g.sum)} €</span><span class="small muted">${FD(g.date_from)}${g.date_from !== g.date_to ? ' – ' + FD(g.date_to) : ''}</span><button class="ghost small kz-toggle" aria-expanded="${open ? 'true' : 'false'}">${open ? t('umsaetze_zu') : t('umsaetze_auf')}</button></div>

      ${g.count === 1 && g.transactions[0] ? `<div class="small muted kz-one">${esc(g.transactions[0].purpose || '')}${g.transactions[0].kind ? ` <span class="tag">${esc(g.transactions[0].kind)}</span>` : ''}</div>` : ''}
      <div class="row tight"><input type="text" class="kz-kat" list="kz-kats" value="${esc(CP(g.proposal))}" placeholder="${t('kategorie_aus_moneymoney')}" style="min-width:300px" ${can ? '' : 'disabled'}>${g.proposal ? `<span class="tag tipped" tabindex="0" data-tip="${esc(t('vorschlag_tip'))}">${t('vorschlag_tag')}</span>` : Object.keys(g.proposals).length ? `<span class="tag tipped" tabindex="0" data-tip="${esc(t('vorschlaege_je_umsatz_tip'))}">${t('vorschlaege_je_umsatz')}</span>` : ''}
        <button class="small kz-save" ${can && n ? '' : 'disabled'}>${n < g.count ? tn('n_zuordnen', n, n) : t('zuordnen')}</button>${g.own_account && off.transfer ? `<button class="small secondary kz-umb" title="${esc(t('kz_umbuchung_tip'))}" ${can ? '' : 'disabled'}>${esc(off.transfer)}</button>` : ''}</div>
      ${open ? `<div class="kz-tx-wrap" data-ex="categories.open.group.tx"><table class="plain small kz-tx"><thead><tr><th><input type="checkbox" class="kz-all" ${aus.size ? '' : 'checked'} aria-label="${t('alle_2')}"></th><th>${t('datum')}</th><th>${t('konto_2')}</th><th>${t('zweck')}</th><th class="num">${t('betrag')}</th>${mixed ? `<th>${t('vorschlag_tag')}</th>` : ''}</tr></thead><tbody>${g.transactions.map(u => `<tr><td><input type="checkbox" class="kz-sel" data-id="${u.id}" ${aus.has(u.id) ? '' : 'checked'}></td><td style="white-space:nowrap">${FD(u.date)}</td><td style="white-space:nowrap">${esc(u.account)}</td><td class="kz-zweck">${u.name && u.name !== g.name ? `<b>${esc(u.name)}</b> ` : ''}${esc(u.purpose || '–')}${u.kind ? ` <span class="tag">${esc(u.kind)}</span>` : ''}</td><td class="num ${u.amount < 0 ? 'neg' : 'pos'}">${F(u.amount)}</td>${mixed ? `<td class="muted">${esc(CP(u.proposal) || '–')}</td>` : ''}</tr>`).join('')}</tbody></table></div>` : ''}</div></div>`;
  }
  return h + '</div>';
}
function bindZuordnen(main) {
  const bindF = (id, key) => { const el = $(id, main); if (el) el.addEventListener('change', e => { KZ[key] = e.target.value; KZ.aus = {}; route(); }); };
  bindF('#kz-jahr', 'year'); bindF('#kz-min', 'min');
  const ka = $('.kz-areas', main); if (ka) ka.addEventListener('change', async () => {
    const ohne = $$('input[data-area]', ka).filter(i => !i.checked).map(i => i.dataset.area);
    if (ohne.length === $$('input[data-area]', ka).length) { toast(t('kz_ein_bereich')); route(); return; }       // at least one stays
    try { const r = await api('/api/categories/areas', {without: ohne, wait: true}); S.CFG = r.config; KZ.aus = {}; await loadAll(); route(); } catch (e) { toast(e.message, 5000); }
  });
  $$('.kz-toggle', main).forEach(b => b.addEventListener('click', e => { const k = e.target.closest('.kz-group').dataset.key; KZ.expanded[k] = !KZ.expanded[k]; route(); }));
  // einzelne Umsätze einer Gegenpartei abwählen (z. B. ein Händler, bei dem du Verschiedenes kaufst) -- ohne neu zu laden
  const updGroup = box => {
    const g = KZ.open.groups.find(x => x.key === box.dataset.key), aus = KZ.aus[g.key] || new Set(), n = g.ids.length - aus.size;
    const all = $('.kz-all', box); if (all) { all.checked = !aus.size; all.indeterminate = aus.size > 0 && n > 0; }
    $$('.kz-sel', box).forEach(cb => { cb.checked = !aus.has(+cb.dataset.id); });
    $('.kz-count', box).textContent = (n < g.count ? n + ' / ' : '') + g.count + '×';
    const b = $('.kz-save', box); b.textContent = n < g.count ? tn('n_zuordnen', n) : t('zuordnen'); b.disabled = !n;
    const a = $('#kz-alle', main); if (a) a.textContent = t('alle_vorschlaege_n', vorschlagIds(KZ.open).length);
  };
  $$('.kz-group', main).forEach(updGroup);
  $$('.kz-all', main).forEach(cb => cb.addEventListener('change', e => {
    const box = e.target.closest('.kz-group'), g = KZ.open.groups.find(x => x.key === box.dataset.key);
    KZ.aus[g.key] = e.target.checked ? new Set() : new Set(g.ids); updGroup(box);
  }));
  $$('.kz-sel', main).forEach(cb => cb.addEventListener('change', e => {
    const box = e.target.closest('.kz-group'), id = +e.target.dataset.id, aus = KZ.aus[box.dataset.key] || (KZ.aus[box.dataset.key] = new Set());
    if (e.target.checked) aus.delete(id); else aus.add(id);
    updGroup(box);
  }));
  const assign = async (box, kat) => {
    const g = KZ.open.groups.find(x => x.key === box.dataset.key); if (!g || !kat) return toast(t('kategorie_fehlt'));
    const aus = KZ.aus[g.key] || new Set(), ids = g.ids.filter(i => !aus.has(i)), vorher = KZ.open.rule_proposals || 0;
    if (!ids.length) return;
    try {
      const r = await assignCats(ids, kat); delete KZ.aus[g.key]; await loadAll(); await route();
      toast(assignMsg(r) + ((KZ.open.rule_proposals || 0) > vorher ? ' · ' + t('regel_vorgeschlagen') : ''), 7000);
    } catch (e) { toast(e.message, 6000); }
  };
  $$('.kz-save', main).forEach(b => b.addEventListener('click', e => { const box = e.target.closest('.kz-group'); assign(box, $('.kz-kat', box).value.trim()); }));
  // between two of your areas: a contribution or withdrawal gets your transfer category in one click
  $$('.kz-umb', main).forEach(b => b.addEventListener('click', e => assign(e.target.closest('.kz-group'), KZ.open.transfer)));
  $$('.kz-kat', main).forEach(i => i.addEventListener('keydown', e => { if (e.key === 'Enter') { const box = e.target.closest('.kz-group'); assign(box, e.target.value.trim()); } }));
  const all = $('#kz-alle', main); if (all) all.addEventListener('click', async () => {
    // alle Vorschläge auf einmal, je Umsatz sein eigener Vorschlag (dieselben Prüfungen wie einzeln); Abgewähltes bleibt
    const items = vorschlagIds(KZ.open), by = {};
    for (const [i, k] of items) (by[k] = by[k] || []).push(i);
    if (!items.length || !confirm(tn('alle_vorschlaege_frage', items.length))) return;
    const sum = {written: 0, later: 0, error: 0, kept: 0, mac_only: 0, unreachable: 0, waiting: 0};
    try { for (const [k, ids] of Object.entries(by)) { const r = (await assignCats(ids, k)).mm || {}; for (const x in sum) sum[x] += r[x] || 0; } }
    catch (e) { toast(e.message, 6000); }
    KZ.aus = {}; toast(assignMsg({mm: sum}), 6000); await loadAll(); route();
  });
}
// Regeln für MoneyMoney: Kontor schlägt sie vor (in MoneyMoneys Schreibweise), angelegt werden sie dort
async function vRegelVorschlaege() {
  if (!S.DATA) return noData;
  const r = await api('/api/categories/proposals'), vs = r.proposals || [];
  KZ.rules = vs.length;
  let h = `<div class="note">${t('regeln_mm_note', hq('regeln_mm'))}</div>`;
  if (!vs.length) return h + `<div class="card" data-ex="categories.rules"><div class="v s">${t('keine_regelvorschlaege')}</div><div class="d">${t('keine_regelvorschlaege_d')}</div></div>`;
  h += '<div class="list" data-ex="categories.rules">' + vs.map(v => `<div class="item rv" data-key="${esc(v.key)}"><div class="grow">
    <div class="row tight"><b style="min-width:220px">${esc(CP(v.category))}</b><span class="small muted">${tn('aus_n_zuordnungen', v.yours, v.yours)} · ${tn('trifft_n', v.hits, v.hits)}${v.open ? ' · ' + tn('davon_n_offen', v.open, v.open) : ''}</span></div>
    <div class="row tight"><code class="rv-expr" tabindex="0">${esc(v.phrase)}</code><button class="small rv-copy">${t('kopieren')}</button><button class="small secondary rv-done" title="${t('regel_erledigt_tip')}">${t('erledigt')}</button></div></div></div>`).join('') + '</div>';
  return h;
}
function bindRegelVorschlaege(main) {
  $$('.rv-copy', main).forEach(b => b.addEventListener('click', async e => {
    const code = $('.rv-expr', e.target.closest('.rv')).textContent;
    try { await navigator.clipboard.writeText(code); toast(t('kopiert')); }
    catch (er) { const sel = getSelection(), rg = document.createRange(); rg.selectNodeContents($('.rv-expr', e.target.closest('.rv'))); sel.removeAllRanges(); sel.addRange(rg); toast(t('markiert_kopieren')); }
  }));
  $$('.rv-done', main).forEach(b => b.addEventListener('click', async e => {
    try { await api('/api/categories/proposals', {done_items: e.target.closest('.rv').dataset.key}); route(); } catch (er) { toast(er.message, 5000); }
  }));
}

// ---------------------------------------------------------------- Einstellungen
async function vEinstellungen() {
  // How Kontor runs (nothing here changes a figure): Allgemein · MoneyMoney & Abgleich · Zugang · Belege · Updates · Sichern.
  // What sets your figures (areas, accounts, positions, rules, tax) is under "Konten & Regeln".
  const tabs = subTabs('settings', Object.entries(SUB_LABEL.settings).map(([k, l]) => [k, t(l)]));
  const v = {moneymoney: vEinstellungenMM, access: vEinstellungenZugang, receipts: vEinstellungenBelege, assistant: vEinstellungenAssistent, updates: () => vUpdates(vEinstellungenUpdates()), backup: vSicherung}[S.sub] || vEinstellungenAllgemein;
  return tabs + await v();
}
const saveBar = () => `<div class="actions"><button id="save-settings" data-cmd-s>${t('einstellungen_speichern')}</button></div><div id="findings-e" class="findings"></div>`;
function vEinstellungenAllgemein() {
  return `<div data-ex="settings.general"><div class="note">${t('einstellungen_vs_einrichtung', '<a href="#accounts">' + t('konten_regeln') + '</a>')}</div><div class="form">
    <label>${t('sprache_label')}</label><label class="chk"><select id="e-lang">${langOpts()}</select> <span class="small muted">${t('sprache_hinweis')}</span></label>
    <label>${t('design_label')}</label><label class="chk"><select id="e-theme">${[['dark', t('design_dunkel')], ['light', t('design_hell')], ['auto', t('design_system')]].map(([k, l]) => `<option value="${k}" ${themeGet() === k ? 'selected' : ''}>${l}</option>`).join('')}</select> <span class="small muted">${t('design_hinweis')}</span></label>
    <label>${t('als_app')}${hq('als_app')}</label><div class="chk" id="webapp-row">${webappRow()}</div>
  </div></div>`;          // both take effect at once (no save button)
}
// Kontor as an app: running as one; at the Mac Kontor's own app (built there, mac_app.py) -- else a button (Chrome, Edge) or
// the way in Safari (the iPhone, or without the Mac app)
const macApp = () => { const m = !IS_IOS && (S.STATUS || {}).local ? (S.STATUS || {}).mac_app : null; return m && (m.ready || m.building) ? m : null; };
function webappRow() {
  const m = macApp();
  if (SHELL) return `<span class="pill ok">${t('als_app_laeuft')}</span>`;
  if (m) return m.ready ? `<button id="mac-app-open" class="small">${t('mac_app_oeffnen')}</button>${APP_MODE ? ` <span class="small muted">${t('mac_app_statt_safari')}</span>` : ''}`
    : `<span class="small muted">${t('mac_app_baut')}</span>`;
  if (APP_MODE) return `<span class="pill ok">${t('als_app_laeuft')}</span>`;
  if (INSTALL_PROMPT) return `<button id="webapp-install" class="small">${t('als_app_installieren')}</button>`;
  const how = t(IS_IOS ? 'als_app_iphone' : IS_SAFARI ? 'als_app_safari' : 'als_app_anderer');
  return (S.CFG && (S.CFG.ui || {}).webapp && !IS_IOS) ? `<span class="pill ok">${t('eingerichtet')}</span> <span class="small muted">${how}</span>` : `<span>${how}</span>`;
}
// step 1 of the setup: what to do here and now -- create the app, open it, go on there
function webappStep(ok) {
  if (SHELL) return esc(t('mod_webapp_d'));
  if (macApp()) return esc(t(macApp().ready ? 'webapp_schritt_mac' : 'mac_app_baut'));
  if (APP_MODE) return esc(t('mod_webapp_d'));
  if (IS_IOS) return esc(t('webapp_schritt_iphone'));
  if (ok) return esc(t('webapp_schritt_fertig'));
  return esc(t(INSTALL_PROMPT ? 'webapp_schritt_chrome' : IS_SAFARI ? 'webapp_schritt_safari' : 'webapp_schritt_anderer'));
}
function webappDraw() { const el = $('#webapp-row'); if (el && S.CFG) el.innerHTML = webappRow(); if (S.tab === 'setup' && S.CFG && !DIRTY.on) route(); }
// opened as an app at the Mac (or installed from here): remembered, so the setup counts the step also in the browser
async function webappSeen() {
  if (OFFLINE.mode || !S.CFG || !(S.STATUS || {}).local || (S.CFG.ui || {}).webapp) return;
  const seen = JSON.parse(JSON.stringify(S.CFG)), cfg = JSON.parse(JSON.stringify(S.CFG)); cfg.ui = Object.assign({}, cfg.ui, {webapp: true});
  try { const r = await api('/api/config', {config: cfg, anyway: true, seen}, 'PUT'); S.CFG = r.config; } catch (e) {}
}
document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('#mac-app-open'); if (!b) return;
  b.disabled = true;
  try { const r = await api('/api/mac-app/open', {}); if (S.STATUS && r.mac_app) S.STATUS.mac_app = r.mac_app; } catch (x) { toast(x.message, 6000); }
  b.disabled = false; webappDraw();
});
document.addEventListener('click', async e => {
  if (!e.target.closest('#webapp-install') || !INSTALL_PROMPT) return;
  const p = INSTALL_PROMPT; INSTALL_PROMPT = null;
  try { await p.prompt(); const c = await p.userChoice; if (c && c.outcome === 'accepted') await webappSeen(); } catch (x) {}
  webappDraw();
});
// Konten & Regeln: everything that sets your figures -- which accounts there are and where they belong (accounts, areas,
// balances) and by which rules Kontor counts and books (cash flow positions, booking rules, tax). The accounts open first.
async function vKontenRegeln() {
  const tabs = Object.entries(SUB_LABEL.accounts).map(([k, l]) => [k, t(l)]);
  const v = {areas: vBereicheEditor, history: vMMHistorie, positions: vPositionen, rules: vRegeln, tax: vEinstellungenSteuer}[S.sub] || vKontenEditor;
  return `<div class="tabs-row">${subTabs('accounts', tabs)}${setupOpen() ? '' : `<a class="small tabs-aside" href="#setup">${t('einrichtung_pruefen')}</a>`}</div>` + await v();
}
// MoneyMoney sync: the connection, when and how much Kontor reads, what it may write, and where every account stands
async function vEinstellungenMM() {
  const C = S.CFG, z = C.schedule || {}, b = C.balance || {};
  const ok = mmStepDone(S.STATUS) && S.KONTEN.length > 0 && VB.checked !== location.hash;     // just checked here: the page stays as it was
  const conn = ok ? `<details class="conn-fold" data-keep="mm-conn"${keepOpen('mm-conn')}><summary><h2>${t('verbindung')}</h2><span class="dot ok"></span><span class="small muted">${t('mm_verbunden')}</span></summary>${vVerbindung()}</details>`
    : `<h2>${t('verbindung')}</h2>${vVerbindung()}`;
  // while you set Kontor up: the connection first, open (it is this step), the way on right below it
  const setup = setupNav('connect'), first = setup ? `<h2>${t('verbindung')}</h2>${vVerbindung()}${setup.replace('class="setup-nav', 'class="setup-nav below')}` : ok ? '' : conn;
  return `<div data-ex="settings.moneymoney">` + first + `<div data-ex="settings.moneymoney.sync"><h2>${t('synchronisierung')}</h2>${await vSync()}</div>
  <div data-ex="settings.moneymoney.schedule"><h2>${t('abgleich_h')}</h2><div class="form">
    <label>${t('automatischer_abgleich_0', hq('abgleich'))}</label><label class="chk"><input type="checkbox" id="e-auto" ${z.automatic !== false ? 'checked' : ''}> ${t('alle_2')} <input type="number" id="e-intervall" min="5" value="${z.interval_minutes ?? 30}" style="width:70px"> ${t('minuten_nur_wenn_moneymoney_laeuft')}</label>
    <label>${t('alles_neu_lesen_0', hq('voll_lesen'))}</label><label class="chk">${t('alle_2')} <input type="number" id="e-voll" min="1" value="${z.full_read_days ?? 30}" style="width:70px"> ${t('tage')}</label>
    <label>${t('umsaetze_lesen_0', hq('months_back'))}</label><label class="chk">${t('die_letzten')} <input type="number" id="e-monate" min="0" value="${b.months_back ?? 0}" style="width:70px"> ${t('monate_0_alle')}</label>
  </div>${saveBar()}</div>` + (ok && !setup ? conn : '') + '</div>';
}
// the setup's way on, as one slim line above a page it leads through (only while the setup is open)
const setupNav = id => { const n = nextModule(id); return setupOpen() && n ? `<div class="setup-nav small"><span class="muted">${t('einrichtung_kurz')}</span><a href="#setup">‹ ${esc(t('zurueck_zur_einrichtung'))}</a><a href="${n.href}" class="next">${esc(t('weiter_zu', n.t))} ›</a></div>` : ''; };
// the sub-folder pattern: braces only around the placeholders (as the service checks)
const SUB_PLACEHOLDERS = ['year', 'month', 'entity', 'account'];
const subPatternProblem = v => /[{}]/.test(String(v || '').replace(new RegExp(`\\{(${SUB_PLACEHOLDERS.join('|')})\\}`, 'g'), '')) ? t('muster_nur_platzhalter', SUB_PLACEHOLDERS.map(x => `{${x}}`).join(', ')) : '';
function vEinstellungenBelege() {
  const bl = S.CFG.receipts || {};
  return `<div data-ex="settings.receipts"><div class="form">
    <label>${t('belegordner_0', hq('belege_ordner'))}</label><div><input type="text" id="e-bl-ordner" value="${esc(bl.folder || '~/Documents/Kontor-Belege')}" style="width:100%"><div class="small muted">${bl.folder_confirmed ? t('wird_beim_ersten_beleg_angelegt') : t('noch_nicht_angelegt_beim_ersten')}</div></div>
    <label>${t('unterordner_muster_0', hq('belege_sub'))}</label><input type="text" id="e-bl-sub" value="${esc(bl.subfolder || '{year}')}" placeholder="${t('jahr_jahr_entitaet_entitaet_jahr')}">
    <div class="full note">${t('belege_werden_als_normale_dateien_2')}</div>
  </div>${saveBar()}</div>`;
}
function vEinstellungenSteuer() {
  const st = S.CFG.tax || {}, loans = S.KONTEN.filter(k => !k.group && k.role === 'liabilities');
  return `<div data-ex="accounts.tax"><div class="note">${t('steuer_einstellungen_note')}</div><div class="form">
    <label>${t('vermietungs_oberkategorie')}</label><input type="text" id="e-verm" value="${esc(st.rental_category || 'Vermietung')}">
    <div class="full"><h3>${t('darlehen_objekt')}</h3>${loans.length ? `<table class="plain objloans"><thead><tr><th>${t('darlehenskonto')}</th><th>${t('objekt_wie_in_der_kategorie')}</th></tr></thead><tbody>${loans.map(l => `<tr><td>${esc(l.name)}<div class="small muted">${esc(CP(l.path.split(' / ').slice(0, -1).join(' / ')))}</div></td><td><input type="text" class="e-obj" data-ref="${l.uuid} | ${esc(l.name)}" value="${esc((st.property_loans || {})[l.uuid + ' | ' + l.name] || Object.entries(st.property_loans || {}).find(([k]) => k.startsWith(l.uuid))?.[1] || '')}" placeholder="${t('objektname_wie_in_der_kategorie')}"></td></tr>`).join('')}</tbody></table>` : `<span class="muted small">${t('keine_darlehenskonten_erkannt')}</span>`}</div>
    <label>${t('kategorie_steuerposition')}</label><div class="list" id="tax-positions">${Object.entries(st.positions || {}).filter(([k]) => !k.startsWith('_')).map(([k, v]) => posRow(k, v)).join('')}<button id="add-pos" class="secondary small" style="align-self:flex-start;width:auto">${t('zuordnung_hinzufuegen')}</button></div>
  </div>
  <div class="actions"><button id="save-settings">${t('einstellungen_speichern')}</button></div><div id="findings-e" class="findings"></div></div>`;
}
// Why Tailscale is not usable yet, in words (state from "tailscale status")
function tsReason(ts) {
  if (ts.error) return t('fern_ts_fehler', esc(ts.error));
  return {NeedsLogin: t('fern_ts_needslogin'), Stopped: t('fern_ts_stopped'), Starting: t('fern_ts_starting'), NeedsMachineAuth: t('fern_ts_machineauth')}[ts.state] || t('fern_nicht_verbunden');
}
// Hardening: a Tailscale access rule that only lets your devices reach Kontor on this Mac (no other port)
function vTsHarden(ts, r) {
  const port = (r && r.port) || 8765;
  const rule = JSON.stringify({acls: [{action: 'accept', src: ['autogroup:member'], dst: [ts.ip + ':' + port]}]}, null, 2);
  const a = (href, txt) => `<a href="${href}" target="_blank" rel="noopener">${txt}</a>`;
  return `<details class="adv" style="margin-top:12px"><summary id="fz-acl-sum">${t('fern_absichern')}</summary>
    <div class="banner small info" id="fz-acl-state">${t('acl_wird_geprueft')}</div>
    <div class="note">${t('fern_absichern_text', port)}</div>
    <ol class="steps">
      <li>${t('acl_schritt1')} <button class="secondary small" id="fz-acl-copy">${t('regel_kopieren')}</button></li>
      <li>${t('acl_schritt2')} ${a('https://login.tailscale.com/admin/acls/file', t('tailscale_zugriffsregeln'))}</li>
      <li>${t('acl_schritt3')}</li>
      <li>${t('acl_schritt4')}</li>
      <li>${t('acl_schritt5')} <button class="secondary small" id="fz-acl-check">${t('jetzt_pruefen')}</button></li>
    </ol>
    <pre class="code" id="fz-acl">${esc(rule)}</pre>
    <div class="note">${t('acl_geraetefreigabe')} ${a('https://login.tailscale.com/admin/settings/device-management', t('tailscale_geraetefreigabe'))} ·${more('iphone-security')}</div></details>`;
}
async function vEinstellungenZugang() {
  // On the Mac (lock, Touch ID, address, password), below: access from the iPhone via Tailscale (state, setup, who/where/what, options, hardening)
  const o = (S.CFG || {}).ui || {};
  // the state of Tailscale can take a while (its app answers slowly): the page shows at once, that part follows when it is there
  const rc = S.remoteCache && Date.now() - S.remoteCache.t < 60000 ? S.remoteCache.r : null, r = rc;
  if (!rc && !S.remoteLoading) { S.remoteLoading = true;
    api('/api/remote').then(x => { S.remoteCache = {t: Date.now(), r: x}; }).catch(() => { S.remoteCache = {t: Date.now(), r: null}; })
      .finally(() => { S.remoteLoading = false; if (S.tab === 'settings' && S.sub === 'access' && !DIRTY.on) route(); }); }
  const ts = (r && r.tailscale) || {}, lokal = r ? r.local : S.STATUS.local;
  const ok = b => `<span class="dot ${b ? 'ok' : 'warn'}"></span>`;
  let h = `<div data-ex="settings.access"><div data-ex="settings.access.mac"><h2>${t('am_mac')}</h2><div class="form">
    <label>${t('automatische_sperre')}</label><label class="chk">${t('nach_2')} <input type="number" id="e-sperre" min="1" value="${o.lock_minutes ?? 15}" style="width:70px" ${lokal ? '' : `disabled title="${esc(t('nur_am_mac'))}"`}> ${t('minuten_ohne_aktivitaet')}</label>
    <label>Touch ID ${hq('touchid')}</label><label class="chk"><input type="checkbox" id="e-touchid" ${o.touchid !== false ? 'checked' : ''} ${S.STATUS.touchid && lokal ? '' : 'disabled'}> ${t('am_mac_mit_touch_id', S.STATUS.touchid ? '' : t('an_diesem_geraet_nicht_verfuegbar'))}</label>
  </div>
  <details class="adv"><summary>${t('erweitert_adresse_port')}</summary><div class="form">
    <label>${t('adresse_0', hq('bind'))}</label><input type="text" id="e-bind" value="${esc(o.bind || '127.0.0.1')}" placeholder="${t('127_0_0_1_oder')}">
    <label>${t('port')} ${hq('port')}</label><input type="number" id="e-port" value="${o.port ?? 8765}" style="width:100px">
    <label>${t('tls_zertifikat_optional_0', hq('tls'))}</label><input type="text" id="e-cert" value="${esc(o.tls_cert || '')}" placeholder="/Pfad/zert.crt">
    <label>${t('tls_schluessel_optional')}</label><input type="text" id="e-key" value="${esc(o.tls_key || '')}" placeholder="/Pfad/zert.key">
    <div class="full note">${t('adresse_port_neustart')}</div>
  </div></details>
  <div class="actions"><button id="save-settings">${t('einstellungen_speichern')}</button></div><div id="findings-e" class="findings"></div>
  <h2>${t('passwort')}</h2><div class="form pw-form"><label>${t('altes_passwort')}</label><input type="password" id="pw-alt" autocomplete="current-password"${S.STATUS.touchid && S.STATUS.touchid_active && lokal ? ` placeholder="${esc(t('leer_touch_id'))}"` : ''}><label>${t('neues_passwort')}</label><input type="password" id="pw-neu" autocomplete="new-password"><label>${t('ph_passwort_wiederholen')}</label><input type="password" id="pw-neu2" autocomplete="new-password"></div><div class="actions"><button id="pw-save" class="secondary">${t('passwort_aendern')}</button></div>`;
  h += `</div><div data-ex="settings.access.iphone"><h2>${t('zugriff_vom_iphone')} ${hq('fern')}</h2>`;
  if (!r && S.remoteLoading) return h + `<div class="note"><span class="spin"></span> ${t('wird_geladen')}</div></div></div>`;
  if (r && r.active) {
    h += `<div class="banner ${r.listening ? 'ok' : 'warn'}">${r.listening ? t('fern_an', `<b>${esc(r.url)}</b>`) : t('fern_an_wartet', esc(r.error || ''))}</div>
      <div class="row tight"><button class="secondary small" id="fz-copy" data-url="${esc(r.url)}">${t('link_kopieren')}</button>${lokal ? `<button class="danger small" id="fz-aus">${t('zugriff_ausschalten')}</button>` : ''}</div>
      <div class="kv" style="margin-top:12px"><div>${t('wer')}</div><div>${t('fern_wer', esc(ts.account || '?'))}${(ts.devices || []).length ? `<div class="small muted">${t('geraete_im_tailnet')}: ${ts.devices.map(g => esc(g.name) + (g.os ? ' (' + esc(g.os) + ')' : '') + (g.online ? '' : ' · ' + t('offline_klein'))).join(', ')}</div>` : ''}</div>
        <div>${t('wo')}</div><div>${t('fern_wo')}</div>
        <div>${t('was')}</div><div>${r.read_only ? t('fern_was_lesen') : t('fern_was_bearbeiten')}</div>
        <div>${t('verschluesselung')}</div><div>${r.tls ? t('fern_tls', r.valid_until ? FD(r.valid_until) : '?') : t('fern_ohne_tls')}</div></div>`;
  } else {
    h += `<div class="banner info">${t('fern_aus')}</div><div class="note">${t('fern_warum')}</div>
      <ol class="steps">
        <li>${ok(ts.found && ts.connected)} ${t('fern_schritt_mac')} ${ts.found ? (ts.connected ? `<span class="small muted">${t('fern_verbunden_als', esc(ts.name || ''), esc(ts.account || '?'))}</span>` : `<span class="small">${tsReason(ts)}</span> <button class="secondary small" id="fz-recheck">${t('erneut_pruefen')}</button>`) : `<a href="https://tailscale.com/download/mac" target="_blank" rel="noopener">${t('herunterladen')}</a>`}</li>
        <li>${ok((ts.devices || []).some(g => /ios/i.test(g.os)))} ${t('fern_schritt_iphone')} <a href="https://apps.apple.com/app/tailscale/id1470499037" target="_blank" rel="noopener">App Store</a>${(ts.devices || []).some(g => /ios/i.test(g.os)) ? ` <span class="small muted">${esc(ts.devices.filter(g => /ios/i.test(g.os)).map(g => g.name).join(', '))}</span>` : ''}</li>
        <li>${ok(ts.https)} ${t('fern_schritt_https')} <a href="https://login.tailscale.com/admin/dns" target="_blank" rel="noopener">${t('tailscale_admin')}</a></li>
        <li>${lokal ? `<button id="fz-ein" ${ts.connected ? '' : 'disabled'}>${t('zugriff_einschalten')}</button>${ts.connected && !ts.https ? ` <button id="fz-ein-http" class="secondary small">${t('ohne_zertifikat_einschalten')}</button>` : ''}` : t('nur_am_mac')}</li>
        <li>${t('fern_schritt_oeffnen')}</li>
      </ol><div id="fz-msg" class="findings"></div>`;
  }
  if (ts.connected && ts.ip) h += vTsHarden(ts, r);
  h += `<div class="form" style="margin-top:14px">
    <label>${t('von_unterwegs')} ${hq('fern_was')}</label><label class="chk"><select id="fz-modus" ${lokal ? '' : 'disabled'}><option value="read" ${!r || r.read_only ? 'selected' : ''}>${t('nur_ansehen')}</option><option value="bearbeiten" ${r && !r.read_only ? 'selected' : ''}>${t('ansehen_und_bearbeiten')}</option></select></label>
    <label>${t('offline_ansicht_0', hq('offline'))}</label><label class="chk"><input type="checkbox" id="fz-offline" ${!r || r.offline_copy ? 'checked' : ''} ${lokal ? '' : 'disabled'}> ${t('offline_kopie_erlauben')}</label>
  </div>`;
  if (!IS_LOCAL) h += `<div class="kv" style="margin-top:12px"><div>${t('auf_diesem_geraet')}</div><div id="sw-state">${navigator.serviceWorker && navigator.serviceWorker.controller ? t('aktiv_die_zuletzt_geladenen_daten') : (location.protocol === 'https:' || location.hostname === '127.0.0.1' ? t('wird_beim_naechsten_laden_aktiv') : t('nicht_moeglich_ueber_http_tailscale'))}</div></div>
    <div class="actions"><button id="sw-clear" class="secondary">${t('gespeicherte_daten_auf_diesem_geraet')}</button></div>`;      // on the Mac nothing to say: the offline view is only for the iPhone
  return h + '</div></div>';
}
function bindZugang(main) {
  const msg = (txt, cls) => { const el = $('#fz-msg', main); if (el) showFindings(el, [], txt, cls); else toast(txt, 8000); };
  // the service restarts with the new address: wait for the *new* process (see restartTo), then reload
  const restartWait = before => { msg(t('kontor_startet_neu'), 'hint'); return restartTo(location.port || (location.protocol === 'https:' ? 443 : 80), before); };
  const act = async (aktion, extra = {}) => {
    S.remoteCache = null;
    try { const r = await api('/api/remote', Object.assign({action: aktion}, extra)); if (!r.ok) { msg(r.text, 'error'); return; } if (r.restart) return restartWait(r.instance); S.CFG = await api('/api/config'); route(); }
    catch (e) { msg(e.message, 'error'); }
  };
  const on = $('#fz-ein', main); if (on) on.addEventListener('click', () => { on.disabled = true; on.classList.add('busy'); msg(t('fern_zertifikat_wird_geholt'), 'hint'); act('enable').finally(() => { on.disabled = false; on.classList.remove('busy'); }); });
  const onh = $('#fz-ein-http', main); if (onh) onh.addEventListener('click', () => { if (confirm(t('ohne_zertifikat_frage'))) act('enable_http'); });
  const off = $('#fz-aus', main); if (off) off.addEventListener('click', () => { if (confirm(t('zugriff_ausschalten_frage'))) act('disable'); });
  const rc = $('#fz-recheck', main); if (rc) rc.addEventListener('click', async () => { rc.classList.add('busy'); try { S.remoteCache = {t: Date.now(), r: await api('/api/remote?fresh=1')}; } catch (e) { S.remoteCache = null; } route(); });
  // which ports Tailscale lets in on this Mac (rules as Tailscale applies them)
  const aclState = $('#fz-acl-state', main);
  const aclCheck = async () => {
    if (!aclState) return;
    aclState.className = 'banner small info'; aclState.textContent = t('acl_wird_geprueft');
    let a; try { a = await api('/api/remote/acl'); } catch (e) { a = {state: 'unknown', error: e.message}; }
    const ports = (a.ports || []).map(([x, y]) => x === y ? x : x + '–' + y).join(', ');
    const [cls, txt, sum] = {secured: ['ok', t('acl_abgesichert', a.port), t('acl_sum_ok')],
      open: ['', a.all ? t('acl_offen_alle') : t('acl_offen_ports', ports), t('acl_sum_offen')],
      locked: ['err', t('acl_gesperrt', a.port), t('acl_sum_gesperrt')]}[a.state] || ['info', t('acl_unbekannt', a.error || '?'), t('fern_absichern')];
    aclState.className = 'banner small ' + cls; aclState.textContent = txt; $('#fz-acl-sum', main).textContent = sum;
  };
  aclCheck();
  const acc = $('#fz-acl-check', main); if (acc) acc.addEventListener('click', aclCheck);
  const ac = $('#fz-acl-copy', main); if (ac) ac.addEventListener('click', async () => { const txt = $('#fz-acl', main).textContent; try { await navigator.clipboard.writeText(txt); toast(t('regel_kopiert'), 4000); } catch (e) { prompt(t('regel_kopieren'), txt); } });
  const cp = $('#fz-copy', main); if (cp) cp.addEventListener('click', async () => { try { await navigator.clipboard.writeText(cp.dataset.url); toast(t('link_kopiert_iphone'), 5000); } catch (e) { prompt(t('link'), cp.dataset.url); } });
  const md = $('#fz-modus', main); if (md) md.addEventListener('change', () => act('settings', {remote_read_only: md.value === 'read'}));
  const of = $('#fz-offline', main); if (of) of.addEventListener('change', () => act('settings', {offline_copy: of.checked}));
}
function vEinstellungenUpdates() {
  const up = S.CFG.updates || {};
  return `<h2>${t('einstellungen')}</h2><div class="form">
    <label>${t('automatisch_pruefen_0', hq('updates'))}</label><label class="chk"><select id="e-up-pruefen">${[['daily', t('taeglich')], ['weekly', t('woechentlich')], ['aus', t('nie')]].map(([v, l]) => `<option value="${v}" ${(up.check_mode || 'daily') === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
    <label>${t('quelle_github_0', hq('update_quelle'))}</label><input type="text" id="e-up-repo" value="https://github.com/${esc(up.repo || 'stecrz/Kontor')}">
  </div>
  <div class="actions"><button id="save-settings">${t('einstellungen_speichern')}</button></div><div id="findings-e" class="findings"></div>`;
}
function vEinstellungenDaten() {
  return `<h2>${t('daten')}</h2><div class="kv"><div>${t('datenordner')}</div><div>${esc(S.STATUS.storage.folder)}</div>${S.STATUS.storage.program_folder ? `<div>${t('programmordner')}</div><div>${esc(S.STATUS.storage.program_folder)}</div>` : ''}<div>${t('verschluesselung')}</div><div>${!S.STATUS.storage.encrypted ? t('keine_verschluesselung') : t('aes_256_nach_anmeldung', t(S.STATUS.storage.touchid_unlock ? 'passwort_oder_touch_id' : 'passwort'))}</div><div>${t('belegordner')}</div><div><a href="#settings/receipts" title="${esc(t('belegordner_aendern'))}">${esc(S.STATUS.receipts.folder)}</a></div>
    <div>Time Machine ${hq('timemachine')}</div><div><span id="tm-state" class="muted">…</span> <button id="tm-toggle" class="secondary small hidden"></button></div>
    <div>${t('protokoll')}</div><div><a href="#log">${t('protokoll_und_diagnose')}</a></div></div>
  ${S.STATUS.storage.encrypted ? `<h2>${t('datenschluessel_h')} ${hq('datenschluessel')}</h2>
  <div class="row tight"><input type="password" id="dk-pw" placeholder="${t('passwort_zur_bestaetigung')}" autocomplete="current-password" style="width:220px"><button id="dk-go" class="secondary" ${S.STATUS.local ? '' : t('disabled_title_nur_am_mac')}>${t('datenschluessel_erneuern')}</button></div><div id="dk-report"></div>` : ''}`;
}
const posRow = (k, v) => `<div class="row tight pos-row"><input type="text" class="p-kat" value="${esc(k)}" placeholder="${t('kategorie_oder_oberkategorie')}"><input type="text" class="p-pos" value="${esc(v)}" placeholder="${t('z_b_sonderausgaben_vorsorge')}"><button class="danger small del-row">×</button></div>`;
function collectSettings() {
  // nur die Felder des sichtbaren Reiters; alles andere bleibt, wie es ist
  const cfg = JSON.parse(JSON.stringify(S.CFG));
  if ($('#e-auto')) {
    cfg.schedule = { automatic: $('#e-auto').checked, interval_minutes: Math.max(5, parseInt($('#e-intervall').value) || 30), full_read_days: Math.max(1, parseInt($('#e-voll').value) || 30) };
    cfg.balance = Object.assign(cfg.balance || {}, { months_back: parseInt($('#e-monate').value) || 0 });
  }
  if ($('#e-bl-sub') && subPatternProblem($('#e-bl-sub').value.trim())) { $('#e-bl-sub').classList.add('invalid'); $('#e-bl-sub').focus(); throw new Error(subPatternProblem($('#e-bl-sub').value.trim())); }
  if ($('#e-bl-ordner')) cfg.receipts = Object.assign(cfg.receipts || {}, { folder: $('#e-bl-ordner').value.trim() || '~/Documents/Kontor-Belege', subfolder: $('#e-bl-sub').value.trim() || '{year}',
      folder_confirmed: !!(cfg.receipts || {}).folder_confirmed || $('#e-bl-ordner').value.trim() !== ((S.CFG.receipts || {}).folder || '') });    // ein hier gewählter Ordner gilt als bestätigt
  if ($('#e-verm')) cfg.tax = Object.assign(cfg.tax || {}, { rental_category: $('#e-verm').value.trim() || 'Vermietung',
      property_loans: Object.fromEntries($$('.e-obj').map(i => [i.dataset.ref, i.value.trim()]).filter(([, v]) => v)),
      positions: Object.fromEntries($$('.pos-row').map(r => [$('.p-kat', r).value.trim(), $('.p-pos', r).value.trim()]).filter(([k, v]) => k && v)) });
  if ($('#e-up-pruefen')) {
    // Quelle als GitHub-Adresse (https://github.com/inhaber/projekt); gespeichert wird inhaber/projekt
    const m = $('#e-up-repo').value.trim().match(/^(?:https?:\/\/(?:www\.)?github\.com\/)?([\w.-]+)\/([\w.-]+?)(?:\.git)?\/?$/i);
    if (!m) throw new Error(t('err_nur_github_adresse'));
    cfg.updates = { check_mode: $('#e-up-pruefen').value, repo: m[1] + '/' + m[2] };
  }
  if ($('#e-sperre')) cfg.ui = Object.assign(cfg.ui || {}, { lock_minutes: Math.max(1, parseInt($('#e-sperre').value) || 15), touchid: $('#e-touchid').checked,
    bind: $('#e-bind').value.trim() || '127.0.0.1', port: parseInt($('#e-port').value) || 8765, tls_cert: $('#e-cert').value.trim(), tls_key: $('#e-key').value.trim() });
  return cfg;
}

// ---------------------------------------------------------------- Sicherung & Pakete
let PKG = null, PKG_UNRES = null;
function vSicherung() {
  // Sicherung (alles) · Einstellungspaket (zum Weitergeben) · Laden für beides über dieselbe Fläche · Zurücksetzen
  const C = S.CFG;
  return `<div data-ex="settings.backup"><div data-ex="settings.backup.backup"><h2>${t('sicherung_h')} ${hq('sicherung')}</h2><div class="note">${t('sicherung_text')}</div>
  ${S.STATUS.local ? `<div class="row tight"><input type="password" id="bk-pw" placeholder="${t('passwort_fuer_die_sicherung')}" autocomplete="new-password" style="width:230px"><input type="password" id="bk-pw2" placeholder="${t('ph_passwort_wiederholen')}" autocomplete="new-password" style="width:230px"><button id="bk-save" class="secondary">${t('sicherung_verschluesselt_herunterladen')}</button></div><div class="small muted">${t('sicherung_passwort_hinweis')}</div>` : `<div class="small muted">${t('nur_am_mac')}</div>`}
  </div><div data-ex="settings.backup.package"><h2>${t('einstellungspaket')} ${hq('package')}</h2><div class="note">${t('paket_text', `<code>${t('name_kontor_json')}</code>`)}</div>
  <div class="row tight"><label class="chk">${t('name')} <input type="text" id="pk-name" value="${esc(t('paket_name'))}"></label><button id="pk-export" class="secondary">${t('paket_herunterladen')}</button></div>
  <div class="small muted">${t('aktuell_0_darlehen_1_beteiligungen', (C.loans || []).length, (C.companies || []).length, Object.keys((C.cashflow || {}).positions || {}).length)}</div>
  <h2>${t('datei_laden')}</h2><div class="drop" id="pk-drop">${t('sicherung_hierher_ziehen')}<br><button id="pk-pick" class="small" style="margin-top:8px">${t('datei_waehlen')}</button></div><div id="pk-preview"></div></div>
  <div data-ex="settings.backup.data">${vEinstellungenDaten()}</div>
  <div data-ex="settings.backup.reset"><h2>${t('zuruecksetzen_h')}</h2><div class="note">${t('zuruecksetzen_text')}</div>
  <div class="row tight"><input type="password" id="rs-pw" placeholder="${t('passwort_zur_bestaetigung')}" autocomplete="current-password" style="width:220px"><label class="chk"><input type="checkbox" id="rs-pw-reset"> ${t('passwort_ebenfalls_zuruecksetzen_einri')}</label><button id="rs-go" class="danger" ${S.STATUS.local ? '' : t('disabled_title_nur_am_mac')}>${t('programm_zuruecksetzen')}</button></div><div id="rs-report" class="findings"></div>
  <h2>${t('deinstallieren_h')}</h2><div class="note">${t('deinstallieren_text')}</div>
  <div class="row tight"><input type="password" id="un-pw" placeholder="${t('passwort_zur_bestaetigung')}" autocomplete="current-password" style="width:220px"><label class="chk"><input type="checkbox" id="un-prog" checked> ${t('deinstall_programmordner')}</label><button id="un-go" class="danger" ${S.STATUS.local ? '' : t('disabled_title_nur_am_mac')}>${t('kontor_deinstallieren')}</button></div><div id="un-report" class="findings"></div></div></div>`;
}
function pkgPreview() {
  const el = $('#pk-preview'); if (!PKG) { el.innerHTML = ''; return; }
  const c = PKG.config || {};
  let h = `<div class="card" style="margin-top:12px"><h3>${esc(PKG.name || t('paket'))} <span class="muted">${t('version_0_1', esc(PKG.version || '?'), esc(PKG.created || ''))}</span></h3>
    <div class="small">${t('0_darlehen_1_beteiligungen_2', (c.loans || []).length, (c.companies || []).length, Object.keys((c.cashflow || {}).positions || {}).length, Object.keys((c.tax || {}).positions || {}).length, PKG.plan ? t('planung_enthalten') : '')}</div>
    <div class="row tight" style="margin-top:8px"><div class="seg" id="pk-mode"><button data-m="merge" class="on">${t('ergaenzen_regeln_hinzufuegen_zuordnung')}</button><button data-m="replace">${t('ersetzen_vorhandene_regeln_verwerfen')}</button></div>${PKG.plan ? `<label class="chk"><input type="checkbox" id="pk-withplan"> ${t('planung_uebernehmen')}</label>` : ''}<button id="pk-import" class="small">${t('uebernehmen')}</button></div>`;
  if (PKG_UNRES && PKG_UNRES.length) {
    h += `<h3 style="margin-top:12px">${t('nicht_gefundene_konten_zuordnen')}</h3><div class="list">` + PKG_UNRES.map((u, i) => `<div class="row tight"><span style="min-width:280px"><b>${esc(u.label)}</b> <span class="small muted">(${esc(u.field)})</span></span><select class="pk-map" data-ref="${esc(u.ref)}">${acctOptions('')}</select></div>`).join('') + `</div><div class="row tight"><button id="pk-import2" class="small">${t('mit_zuordnung_uebernehmen')}</button><button id="pk-force" class="small secondary">${t('ohne_zuordnung_uebernehmen_namen_bleib')}</button></div>`;
  }
  el.innerHTML = h + '<div id="pk-report" class="findings"></div></div>';
  let mode = 'merge';
  $$('#pk-mode button').forEach(b => b.onclick = () => { $$('#pk-mode button').forEach(x => x.classList.remove('on')); b.classList.add('on'); mode = b.dataset.m; });
  const doImport = async (mapping, force) => {
    try {
      const r = await api('/api/package/import', {package: PKG, mode: mode, assignment: mapping || {}, anyway: !!force, with_plan: !!($('#pk-withplan') && $('#pk-withplan').checked)});
      if (!r.ok) { PKG_UNRES = r.unresolved; pkgPreview(); showFindings($('#pk-report'), [], r.hint + t('n_offen', r.unresolved.length), 'warning'); return; }
      S.CFG = r.config; PKG_UNRES = null; showFindings($('#pk-report'), r.findings, t('uebernommen_2') + r.report.join(' · '), 'ok'); toast(t('paket_uebernommen'));
    } catch (e) { showFindings($('#pk-report'), [], e.message, 'error'); }
  };
  $('#pk-import').onclick = () => doImport({}, false);
  const i2 = $('#pk-import2'); if (i2) i2.onclick = () => doImport(Object.fromEntries($$('.pk-map').map(s => [s.dataset.ref, s.value]).filter(([, v]) => v)), false);
  const i3 = $('#pk-force'); if (i3) i3.onclick = () => doImport(Object.fromEntries($$('.pk-map').map(s => [s.dataset.ref, s.value]).filter(([, v]) => v)), true);
}
async function readPkgFile(file) {
  try {
    const obj = JSON.parse(await file.text());
    if (obj.kontor_backup_encrypted) {
      const pw = await askPassword(t('sicherung_laden_frage', esc(obj.created || '?'), esc(obj.version || '?')));
      if (!pw) return;
      const r = await api('/api/backup/restore', {backup: obj, password: pw});
      if (r.restart) { restartTo(r.port, r.instance); return; }
      S.CFG = r.config; toast(t('sicherung_geladen') + r.parts.join(', '), 6000); await loadAll(); route(); return;
    }
    if (obj.kontor_backup) {
      const teile = [t('einstellungen'), obj.plan ? t('planung') : '', obj.categories ? t('kategorien') : '', obj.history ? t('verlauf_2') : '', obj.receipts ? t('belegindex') : ''].filter(Boolean).join(', ');
      if (!confirm(t('sicherung_vom') + (obj.created || '?') + ' (' + t('version') + ' ' + (obj.version || '?') + t('wiederherstellen_ersetzt') + teile + '.')) return;
      const r = await api('/api/backup/restore', {backup: obj});
      if (r.restart) { restartTo(r.port, r.instance); return; }
      S.CFG = r.config; toast(t('sicherung_geladen') + r.parts.join(', '), 6000); await loadAll(); route(); return;
    }
    PKG = obj; if (!PKG.config) { if (PKG.loans || PKG.balance) PKG = {kontor_package: 1, name: file.name, config: PKG}; else throw new Error(t('err_kein_paket')); } PKG_UNRES = null; pkgPreview(); }
  catch (e) { toast(t('datei_unlesbar') + e.message, 5000); }
}

// ---------------------------------------------------------------- Updates
function clHtml(md, hv = 'h3') {
  // CHANGELOG (Markdown-Ausschnitt): Versionen als Ueberschrift, Punkte als Liste, `Code`, **fett**
  const inl = s => esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
  let h = '', open = false;
  for (const line of md.split('\n')) {
    const v = line.match(/^##\s+(\S+)(?:\s+\((\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?)\))?/), li = line.match(/^\s*[-*]\s+(.*)/);
    if (v) { if (open) h += '</ul>'; open = false; h += `<${hv}>${esc(v[1])}${v[2] ? `<span class="vdate">${t('vom_0', FDT(v[2]))}</span>` : ''}</${hv}>`; }
    else if (li) { if (!open) h += '<ul>'; open = true; h += `<li${/^(Entwicklung|Development)\s*:/.test(li[1]) ? ' class="dev"' : ''}>${inl(li[1])}</li>`; }     // rules, tests, CI: quieter
    else if (line.trim() && !line.startsWith('# ')) { if (open) h += '</ul>'; open = false; h += `<p>${inl(line)}</p>`; }
  }
  return `<div class="cl">${h}${open ? '</ul>' : ''}</div>`;
}
// Changelog by major version: X.Y.0 closes the steps before it (3.17 = 3.16.1 … 3.17.0), steps whose major version is not
// out yet are "in progress"; the overview always in view, the single versions folded below it; the newest few shown, older folded
const CL_SHOWN = 3;
function clRange(a, b) {
  a = (a || '').slice(0, 10); b = (b || '').slice(0, 10);
  if (!a || !b || a === b) return FD(a || b);
  const dm = d => LANG === 'en' ? d.slice(8, 10) + '/' + d.slice(5, 7) : d.slice(8, 10) + '.' + d.slice(5, 7) + '.';
  return (a.slice(0, 4) === b.slice(0, 4) ? dm(a) : FD(a)) + ' – ' + FD(b);
}
function clSeries(g) {
  const sum = g.highlights.length ? clHtml(g.highlights.join('\n')) : g.topics.length ? `<p class="cl-topics">${esc(t('themen_0', g.topics.join(', ')))}</p>` : '';
  const span = g.first === g.last ? g.first : t('0_bis_1', g.first, g.last), when = [g.released ? '' : t('in_arbeit'), clRange(g.from, g.to)].filter(Boolean).join(' · ');
  return `<section class="cl-series${g.released ? '' : ' wip'}" data-series="${esc(g.series)}"><h3>${esc(g.series)}<span class="vdate">${esc(when)}</span></h3>${sum}
    <details class="cl-versions"><summary>${esc(tn('alle_0_versionen', g.count, span))}</summary>${clHtml(g.text, 'h4')}</details></section>`;
}
function clHistory(hist) {
  if (!hist || !hist.length) return '';
  const old = hist.slice(CL_SHOWN);
  return `<h2>${t('aenderungen_je_hauptversion')}</h2>${hist.slice(0, CL_SHOWN).map(clSeries).join('')}`
    + (old.length ? `<details class="cl-older"><summary>${tn('aeltere_hauptversionen_0', old.length, old.length > 1 ? t('0_bis_1', old[0].series, old[old.length - 1].series) : old[0].series)}</summary>${old.map(clSeries).join('')}</details>` : '');
}
// An update whose files hold something that can be a risk (update_guard.py read them before any of it runs): one entry per
// finding or way out, its title in plain words; opened, what it can do and what to look for, then where it is and -- folded
// -- the lines it concerns ("−" taken away, "+" new). What needs no approval: one quiet line below. Every text of the
// update's files (names, lines) is shown as text.
const UP_KINDS = {guard: ['upd_t_check', 'upd_w_check'], rule: ['upd_t_rules', 'upd_w_rules'], shadow: ['upd_t_shadow', 'upd_w_shadow'],
  module: ['upd_t_module', 'upd_w_module'], call: ['upd_t_new_other', 'upd_w_new_other'], around: ['upd_t_way_other', 'upd_w_way_other'],
  detour: ['upd_t_detour', 'upd_w_detour'], self: ['upd_t_self', 'upd_w_self'], place: ['upd_t_place', 'upd_w_place'], address: ['upd_t_address', 'upd_w_address'],
  page: ['upd_t_page', 'upd_w_page'], file: ['upd_t_file', 'upd_w_file'], extra: ['upd_t_extra', 'upd_w_extra'], unreadable: ['upd_t_unreadable', 'upd_w_unreadable']};
function upLines(x) {
  if (!Array.isArray(x.lines) || !x.lines.length) return '';
  const row = l => { const s = String(l), c = s[0]; return s === '…' ? '<span class="up-gap">⋯</span>' : `<span class="${c === '+' ? 'up-add' : c === '-' ? 'up-del' : 'up-ctx'}">${c === '+' ? '+' : c === '-' ? '−' : ' '} ${esc(s.slice(1))}</span>`; };
  return `<details class="up-lines"><summary>${esc(tn('upd_zeilen_zeigen', x.lines.length))}</summary><pre class="up-diff">${x.lines.map(row).join('\n')}${x.more ? `\n<span class="up-gap">${esc(tn('upd_mehr_zeilen', x.more))}</span>` : ''}</pre></details>`;
}
function upEntry(xs) {
  const x = xs[0], k = UP_KINDS[x.kind] || UP_KINDS.unreadable, crit = xs.some(y => y.level !== 'review');
  const arg = esc(x.arg != null ? x.arg : x.kind === 'extra' ? x.what : x.file || x.what || '');
  const parts = xs.filter(y => !y.dup).map(y => `<div class="up-part"><div class="up-where">${esc(y.file || '')}${y.where ? ` · <code>${esc(y.where)}</code>` : !y.lines && y.what && y.what !== y.file ? ` · ${esc(y.what)}` : ''} <span class="muted">${t(y.gone ? 'upd_entfernt' : y.new ? 'upd_neu' : 'upd_geaendert')}</span></div>${upLines(y)}</div>`).join('');
  return `<details class="up-find${crit ? ' crit' : ''}"><summary><b>${t(x.title || k[0], arg)}</b></summary><div class="up-body"><p class="up-why">${t(x.why || k[1], arg)}</p>${parts}</div></details>`;
}
function upReview(info) {
  const f = upFinds(info), plain = upPlain(info).filter(x => !x.dup);
  if (!f.length && !plain.length) return '';
  const groups = new Map();
  f.forEach(x => { const k = x.topic || x.kind + ':' + x.file; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(x); });
  const entries = [...groups.values()], crit = entries.filter(xs => xs.some(x => x.level !== 'review')).length, rev = entries.length - crit;
  const why = crit && rev ? `${tn('upd_satz_krit', crit)}, ${tn('upd_satz_pruef', rev)}.` : crit ? `${tn('upd_satz_krit', crit)}.` : tn('upd_satz_pruef_allein', rev);
  const asks = f.length ? `<div class="up-review" id="up-review"><div class="note warn"><b>${t('upd_titel', esc(info.available))}</b><div>${why} ${t('upd_text')}${more('updates')}</div></div>
    <div class="up-list">${entries.map(upEntry).join('')}</div></div>` : '';
  return asks + (plain.length ? `<details class="up-plain" id="up-plain"><summary>${tn('upd_ruhig', plain.length)}</summary><div class="up-quiet">${plain.map(x => `<div>${esc(x.file || '')}${x.where ? ` · <code>${esc(x.where)}</code>` : ''}</div>`).join('')}</div></details>` : '');
}
// the click is the decision: installed without a second question (the button rests meanwhile -- a double click installs once).
// Only a version with findings is asked about -- and installed with your approval for exactly the files you were shown; if
// Kontor finds something (else) when it reads them again, the page shows that instead and nothing is installed.
async function upInstall(ui) { if (ui.disabled) return;
    const rev = (S.STATUS.update || {}).review, finds = upFinds(S.STATUS.update);
    if (finds.length && !confirm(t('upd_frage', S.STATUS.update.available))) return;
    ui.disabled = true; toast(t('update_wird_installiert'), 30000);
    try { const r = await api('/api/update/install', finds.length ? {approved: rev.digest} : {}); toast(r.text, 8000);
      if (r.ok && r.restart) waitAndReload(true); else if (r.needs_approval) { S.STATUS = await api('/api/status'); statusMini(); softRoute(); } else ui.disabled = false; } catch (e) { ui.disabled = false; toast(e.message, 8000); } }
async function vUpdates(form) {
  const r = await api('/api/update/status'), st = S.STATUS, info = r.info, finds = upFinds(info);
  let h = `<div data-ex="settings.updates"><div class="cards"><div class="card"><div class="l">${t('installiert')}</div><div class="v">${esc(r.version)}${r.date ? `<span class="vdate">${t('vom_0', FDT(r.date))}</span>` : ''}</div><div class="d">${t('programmordner_wird_beim_update_ersetz')}</div></div>
    <div class="card"><div class="l">${t('verfuegbar_3')}</div><div class="v">${info ? (info.error ? '<span class="pill err">?</span>' : esc(info.available || '–') + (info.date ? `<span class="vdate">${t('vom_0', FDT(info.date))}</span>` : '')) : '–'}</div><div class="d">${info ? (info.error ? esc(info.error) : (info.newer ? `<span class="pill ${finds.length ? 'warn' : 'ok'}">${t(finds.length ? 'upd_wartet' : 'neuer_als_installiert')}</span>` : t('kontor_ist_aktuell')) + (info.newer && info.review && !finds.length ? t('upd_geprueft_ok') : '')) : t('noch_nicht_geprueft')}${r.verified ? t('geprueft') + new Date(r.verified * 1000).toLocaleString(LOCALE) : ''}</div></div></div>
    <div class="actions"><button id="up-check" class="secondary">${t('jetzt_pruefen')}</button><button id="up-install" ${finds.length ? 'class="danger" ' : ''}${info && info.newer && st.local ? '' : 'disabled'}>${t(finds.length ? 'upd_freigeben' : 'update_installieren_und_dienst_neu')}</button>${((S.CFG.updates || {}).repo || 'stecrz/Kontor') !== 'stecrz/Kontor' ? ` <span class="tag warn">${t('update_fremde_quelle', esc((S.CFG.updates || {}).repo))}</span>` : ''}</div>
    ${upReview(info)}
    ${form || ''}
    <div data-ex="settings.updates.changes">${info && info.notes && info.newer ? `<h2>${t('neu_in_0', esc(info.since && info.since !== info.available ? t('0_bis_1', info.since, info.available) : info.available))}</h2>${clHtml(info.notes)}` : ''}
    ${clHistory(r.history)}</div>
    <div class="note">${t('updates_note', esc('https://github.com/' + ((S.CFG.updates || {}).repo || 'stecrz/Kontor')))}${more('updates')}</div></div>`;
  return h;
}

// ---------------------------------------------------------------- Protokoll / Hilfe
// the log: what to see (everything, notes, only warnings and errors) -- warnings amber, errors red, details quiet
const LOG_RANK = {DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3, CRITICAL: 3};
function logLines(lines, min) {
  let lv = 'INFO';
  return lines.map(l => { const m = l.match(/^\S+ \S+ (DEBUG|INFO|WARNING|ERROR|CRITICAL) /); if (m) lv = m[1]; return [lv, l]; })     // a traceback keeps its line's level
    .filter(([v]) => LOG_RANK[v] >= min).map(([v, l]) => `<span class="lg-${v.toLowerCase()}">${esc(l)}</span>`).join('\n');
}
async function vProtokoll() {
  const r = await api('/api/log?n=2000');
  const ordner = (S.STATUS && S.STATUS.storage && S.STATUS.storage.folder) || t('library_application_support_kontor');
  const min = S.logMin ?? 1, body = logLines(r.rows, min);
  const seg = `<div class="seg small" id="log-min" role="group">${[[0, 'log_alles'], [1, 'log_hinweise'], [2, 'log_probleme']].map(([k, l]) => `<button data-min="${k}" class="${min === k ? 'on' : ''}" aria-pressed="${min === k}">${t(l)}</button>`).join('')}</div>`;
  return `<div class="toolbar" data-ex="log.tools">${seg}<button id="log-refresh" class="secondary small">${t('aktualisieren')}</button><button id="diag2" class="secondary small">${t('diagnosedatei_maskiert')}</button><button id="diag3" class="secondary small">${t('diagnosedatei_mit_kontonamen')}</button>${hq('diagnose')}${S.STATUS && S.STATUS.local ? `<button id="log-show" class="secondary small">${t('im_finder_zeigen')}</button>` : ''}</div>
    <div class="note" data-ex="log.file">${t('datei')} <code>${esc(ordner)}/kontor.log</code> ${t('klartext_rotiert_bei_5_mb')} <code>${t('dienst_err_log')}</code> ${t('fuer_abstuerze_des_dienstes_zur')} <code>${t('library_application_support_kontor')}</code>.</div><pre class="log" data-ex="log.lines">` + (body || `<span class="lg-info">${esc(t(min >= 2 ? 'log_nichts' : 'log_leer'))}</span>`) + '</pre>';
}
// Help: docs/help.de.md or docs/help.en.md (the same file as on GitHub), with contents, search and anchors (#help/<section>)
const HELP = {md: null, lang: null, q: '', images: {}};
function mdInline(s) {
  // Markdown in einer Zeile: Code, Fettschrift, Kursiv, Links (intern -> #help/…, extern in neuem Fenster)
  return esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<i>$2</i>')
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, txt, url) => url.startsWith('#') ? `<a href="#help/${url.slice(1)}">${txt}</a>` : `<a href="${url}" target="_blank" rel="noopener">${txt}</a>`);
}
function mdHtml(md) {
  // kleiner Markdown-Leser fuer die Hilfe: Ueberschriften (mit Anker aus <a id>), Absaetze, Listen, Tabellen, Bilder, Code
  const out = []; let list = null, para = [], table = null, anchor = null, code = null;
  const flush = () => { if (para.length) out.push(`<p>${mdInline(para.join(' '))}</p>`); para = []; if (list) out.push(`</${list}>`); list = null; if (table) { out.push(table + '</tbody></table></div>'); table = null; } };
  for (const raw of md.split('\n')) {
    if (code !== null) { if (raw.trim() === '```') { out.push(`<pre class="code">${esc(code.join('\n'))}</pre>`); code = null; } else code.push(raw); continue; }
    if (raw.trim().startsWith('```')) { flush(); code = []; continue; }
    const line = raw.trimEnd(), a = line.match(/^<a id="([\w-]+)"><\/a>$/), hd = line.match(/^(#{1,3})\s+(.*)/), img = line.match(/^!\[([^\]]*)\]\(([\w/.-]+)\)$/);
    const li = line.match(/^\s*(?:[-*]|(\d+)\.)\s+(.*)/), tr = line.match(/^\|(.*)\|$/);
    if (a) { flush(); anchor = a[1]; continue; }
    if (hd) { flush(); const lvl = hd[1].length; if (lvl === 1) { anchor = null; continue; } out.push(`<h${lvl + 1}${anchor ? ` id="hl-${anchor}" data-a="${anchor}"` : ''}>${mdInline(hd[2])}</h${lvl + 1}>`); anchor = null; continue; }
    if (img) {                                   // Groesse vorab (aus dem PNG-Kopf): Platz freihalten, Anker treffen; Aufnahmen mit 2- bzw. 3-facher Aufloesung (iPhone)
      flush(); const wh = HELP.images[img[2]], k = /iphone/.test(img[2]) ? 3 : 2;
      out.push(`<figure><img src="/docs/${img[2]}" alt="${esc(img[1])}"${wh ? ` width="${Math.round(wh[0] / k)}" height="${Math.round(wh[1] / k)}"` : ''} loading="lazy"></figure>`); continue;
    }
    if (tr) {
      const cells = tr[1].split('|').map(c => c.trim());
      if (cells.every(c => /^-+$/.test(c))) continue;
      if (!table) { flush(); table = `<div class="wrap auto" data-ex="help.table"><table class="plain"><thead><tr>${cells.map(c => `<th>${mdInline(c)}</th>`).join('')}</tr></thead><tbody>`; continue; }
      table += `<tr>${cells.map(c => `<td>${mdInline(c)}</td>`).join('')}</tr>`; continue;
    }
    if (li) { const kind = li[1] ? 'ol' : 'ul'; if (para.length || table || (list && list !== kind)) flush(); if (!list) { list = kind; out.push(`<${kind}>`); }
      const la = li[2].match(/^<a id="([\w-]+)"><\/a>/);          // an anchor at the start of an item: the help icon of a chart leads right there
      out.push(`<li${la ? ` id="hl-${la[1]}"` : ''}>${mdInline(la ? li[2].slice(la[0].length) : li[2])}</li>`); continue; }
    if (!line.trim()) { flush(); continue; }
    if (list) flush();
    para.push(line.trim());
  }
  flush();
  return out.join('\n');
}
async function vHilfe() {
  if (HELP.md === null || HELP.lang !== LANG) { try { const r = await api('/api/help?lang=' + LANG); HELP.md = r.text || ''; HELP.images = r.images || {}; HELP.lang = LANG; } catch (e) { return `<div class="card">${esc(e.message)}</div>`; } }
  const toc = [...HELP.md.matchAll(/<a id="([\w-]+)"><\/a>\n##\s+(.*)/g)].map(m => [m[1], m[2]]);
  return `<div class="help-top" data-ex="help.search"><input type="search" id="help-q" data-find placeholder="${t('hilfe_durchsuchen')}" value="${esc(HELP.q)}"><span class="small muted" id="help-n"></span></div>
    <div class="help-layout"><nav class="help-toc" data-ex="help.toc">${toc.map(([id, title]) => `<a href="#help/${id}" data-a="${id}">${mdInline(title)}</a>`).join('')}<a href="#log" class="help-toc-x">${t('protokoll')}</a></nav>
    <div class="help" id="help-body" data-ex="help.article">${mdHtml(HELP.md)}</div></div>`;
}
// A page of Kontor named in the help as the pages call it -- "Einstellungen → Zugang", "Konten & Regeln → Kontostände", "unter
// Kategorisieren" -- opens it: a jump into Kontor, marked ↗ (unlike a jump within the help). The help text stays plain Markdown.
function helpAppLinks(body) {
  const open = Object.keys(TITLES).filter(k => !['help', 'log', 'setup', 'assistant'].includes(k)), pairs = [];
  for (const tab of open) { for (const [sub, key] of Object.entries(SUB_LABEL[tab] || {})) pairs.push([`${TITLES[tab]} → ${t(key)}`, '#' + tab + (sub ? '/' + sub : '')]); }
  const pages = open.map(tab => [TITLES[tab], '#' + tab]);
  const rx = l => l.slice().sort((x, y) => y[0].length - x[0].length).map(([x]) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  const re = new RegExp(`(${rx(pairs)})|(\\b${t('hilfe_unter')}\\s+)(${rx(pages)})(?![\\wäöüÄÖÜß])`, 'g'), to = new Map(pairs.concat(pages));
  const tw = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, {acceptNode: n => n.parentElement.closest('a, code, pre, h2, h3, h4') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT});
  const nodes = []; while (tw.nextNode()) nodes.push(tw.currentNode);
  for (const nd of nodes) {
    const txt = nd.nodeValue; re.lastIndex = 0; if (!re.test(txt)) continue; re.lastIndex = 0;
    const frag = document.createDocumentFragment(); let at = 0, m;
    while ((m = re.exec(txt))) {
      const name = m[1] || m[3], start = m.index + (m[1] ? 0 : m[2].length);
      frag.append(txt.slice(at, start));
      const a = document.createElement('a'); a.className = 'app-jump'; a.href = to.get(name); a.title = t('hilfe_in_kontor_oeffnen'); a.textContent = name; frag.append(a);
      at = start + name.length;
    }
    frag.append(txt.slice(at)); nd.replaceWith(frag);
  }
}
function bindHilfe(main) {
  const body = $('#help-body', main); if (!body) return;
  helpAppLinks(body);
  // Abschnitte = Ueberschrift h3 (## im Text) bis zur naechsten; Suche blendet Abschnitte ohne Treffer aus und markiert Treffer
  const secs = []; let cur = null;
  for (const el of [...body.children]) { if (el.tagName === 'H3' || el.tagName === 'H2') { cur = {head: el, els: [el], a: el.dataset.a || ''}; secs.push(cur); } else { if (!cur) { cur = {head: null, els: [], a: ''}; secs.push(cur); } cur.els.push(el); } }
  const plain = new Map(secs.map(s => [s, s.els.map(e => e.textContent).join(' ').toLowerCase()]));
  const unmark = () => $$('mark.hm', body).forEach(m => m.replaceWith(document.createTextNode(m.textContent)));
  const search = q => {
    HELP.q = q; unmark(); body.normalize();
    const w = q.trim().toLowerCase(); let n = 0;
    for (const s of secs) {
      const hit = !w || plain.get(s).includes(w); if (hit && w) n++;
      s.els.forEach(e => e.classList.toggle('hidden', !hit));
      const tl = $(`.help-toc a[data-a="${s.a}"]`, main); if (tl) tl.classList.toggle('hidden', !hit);
      if (hit && w) s.els.forEach(e => { const tw = document.createTreeWalker(e, NodeFilter.SHOW_TEXT); const nodes = []; while (tw.nextNode()) nodes.push(tw.currentNode);
        nodes.forEach(nd => { const i = nd.nodeValue.toLowerCase().indexOf(w); if (i < 0) return; const r = document.createRange(); r.setStart(nd, i); r.setEnd(nd, i + w.length); const m = document.createElement('mark'); m.className = 'hm'; r.surroundContents(m); }); });
    }
    $('#help-n', main).textContent = w ? tn('n_abschnitte', n, n) : '';
  };
  const qi = $('#help-q', main); qi.addEventListener('input', () => search(qi.value)); if (HELP.q) search(HELP.q);
  if (S.sub) { const h = $(`#hl-${CSS.escape(S.sub)}`, body); if (h) { if (h.classList.contains('hidden')) { qi.value = ''; search(''); } setTimeout(() => h.scrollIntoView({block: 'start'}), 30); } }
}

// ---------------------------------------------------------------- Steuerung
const TITLES = {overview: t('uebersicht'), balance: t('bilanz'), cashflow: t('kapitalfluss'), planning: t('planung'), bookings: t('nav_auto_buchungen'), tax: t('steuer'), properties: t('immobilien'), transactions: t('umsaetze_belege'), setup: t('einrichtung'), accounts: t('konten_regeln'), categories: t('nav_zuordnen'), settings: t('einstellungen'), log: t('protokoll'), help: t('hilfe'), assistant: t('ki_assistent')};
async function route() {
  if (DIRTY.on && location.hash !== DIRTY.hash) {
    if (!confirm(t('ungespeicherte_aenderungen_verwerfen'))) { history.replaceState(null, '', DIRTY.hash || '#overview'); return; }
    DIRTY.on = false;
  }
  const raw = (location.hash || '#overview').slice(1), [path, qs] = raw.split('?'), [tab, sub] = path.split('/');
  const y0 = pageY();
  if (SCROLL.key) SCROLL.pos[SCROLL.key] = y0;                 // Position des bisherigen Reiters merken
  S.tab = TITLES[tab] && !(demoOn() && DEMO_OFF.has(tab)) ? tab : 'overview'; S.sub = S.tab === tab ? sub || '' : '';
  if (S.tab !== tab && location.hash && demoOn()) history.replaceState(null, '', '#overview');
  const key = S.tab + '/' + S.sub, sameTab = key === SCROLL.key;
  if (!sameTab) KEEP_OPEN.clear();          // folded sections open only while the same page is drawn again
  if (qs && S.tab === 'transactions') { const p = new URLSearchParams(qs); S.uf.uncategorized_flag = p.get('uncategorized') === '1'; S.uf.ohne_beleg = p.get('no_receipt') === '1'; if (p.get('year')) S.uf.year = p.get('year'); if (p.get('entity')) S.uf.entity = p.get('entity'); history.replaceState(null, '', '#transactions'); }
  $$('#nav a').forEach(a => a.classList.toggle('on', a.getAttribute('href') === '#' + (S.tab === 'log' ? 'settings' : S.tab)));          // the log: reached from the settings (and the help)
  { const ns = $('#nav-setup'); if (ns) ns.classList.toggle('hidden', demoOn() || (!setupOpen() && S.tab !== 'setup')); }
  $('#page-title').textContent = (S.tab === 'properties' && S.sub ? t('immobilie') : TITLES[S.tab]);
  if (ALPHA_TABS.has(S.tab)) $('#page-title').insertAdjacentHTML('beforeend', alphaTag('alpha-tag big'));
  $('#page-title').insertAdjacentHTML('beforeend', pageHq(S.tab, S.sub));       // what this page is (a click: its help section)
  $('#bereich-seg').classList.toggle('hidden', !(S.DATA && Object.keys(S.DATA.areas || {}).length > 1 && ['overview', 'balance', 'cashflow', 'planning'].includes(S.tab)));
  $('.side').classList.remove('open');
  if (S.tab !== 'transactions') closeDrawer();
  if (S.tab !== 'assistant') AS.prev = location.hash || '#overview';
  asLayout();
  const main = $('#main');
  const myRoute = ++ROUTE_SEQ;
  const slow = setTimeout(() => { if (ROUTE_SEQ === myRoute) main.innerHTML = `<div class="loading"><span class="spin"></span>${t('0_wird_geladen', esc(TITLES[S.tab] || ''))}<div class="note">${t('der_dienst_antwortet_noch_nicht')}</div></div>`; }, 400);
  try {
    let h = '';
    if (S.tab === 'overview') h = await vUebersicht();
    else if (S.tab === 'balance') h = vBilanz();
    else if (S.tab === 'cashflow') h = vKapitalfluss(false);
    else if (S.tab === 'planning') h = vKapitalfluss(true);
    else if (S.tab === 'bookings') h = vBuchungen(await api('/api/runs'));
    else if (S.tab === 'tax') h = vSteuer();
    else if (S.tab === 'properties') h = vImmobilien(S.sub);
    else if (S.tab === 'setup') h = vEinrichtung(S.sub);
    else if (S.tab === 'accounts') h = await vKontenRegeln();
    else if (S.tab === 'transactions') h = await vUmsaetze();
    else if (S.tab === 'categories') h = await vKategorien();
    else if (S.tab === 'settings') h = await vEinstellungen();
    else if (S.tab === 'log') h = await vProtokoll();
    else if (S.tab === 'help') h = await vHilfe();
    else if (S.tab === 'assistant') h = vAssistent();
    clearTimeout(slow);
    if (ROUTE_SEQ !== myRoute) return;          // inzwischen woanders hin geklickt
    const keepX = sameTab ? $$('.wrap', main).map(scrollMark) : null;   // same page again: tables stay put
    main.style.paddingBottom = '';               // room left by routeKeeping
    main.innerHTML = sameTab ? `<div>${h}</div>` : `<div class="fade">${h}</div>`;          // the same page again (a row opened): in place, no fade-in (it moves it)
    SCROLL.key = key; SCROLL.keepX = keepX;
    pageTo(sameTab ? y0 : (SCROLL.pos[key] || 0));      // eigener Reiter: bleibt; anderer Reiter: dessen letzte Position, sonst oben
    bind(main);
    guardDirty(main);
    vbPoll(); mmhPoll();
    if (S.tab === 'properties') bindImmo(main);
    if (S.tab === 'cashflow') bindCfCharts(main);
    if (S.tab === 'overview') bindOverview(main);
    ovArrive(main);
    if (S.tab === 'categories') { bindZuordnen(main); bindRegelVorschlaege(main); bindEingetragen(main); }
    if (S.tab === 'accounts' && S.sub === 'positions') bindPositionen(main);
    if (S.tab === 'settings' && S.sub === 'access') bindZugang(main);
    if (S.tab === 'settings' && S.sub === 'assistant') bindAssistent(main);
    if (S.tab === 'help') bindHilfe(main);
    keysShow();
    // the same page again: what was drawn just now (the charts) changed heights above -- a browser that keeps what is in view
    // in place (scroll anchoring) moves the page along with it; it stays where it was
    if (sameTab && pageY() !== y0) pageTo(y0);
  } catch (e) { clearTimeout(slow); if (ROUTE_SEQ === myRoute && e.message !== t('nicht_angemeldet')) main.innerHTML = `<div class="banner err">${esc(e.message)} <button class="small secondary" id="route-retry">${t('erneut_versuchen')}</button></div>`; const rb = $('#route-retry', main); if (rb) rb.addEventListener('click', () => route()); }
}
let ROUTE_SEQ = 0;
const softRoute = () => DIRTY.on ? statusMini() : route();      // redraw unless something on the page is not saved yet
const SCROLL = {key: '', pos: {}};
// Ungespeicherte Aenderungen: Formulare auf Seiten mit Speichern-Knopf melden Aenderungen; Wegnavigieren fragt nach
const DIRTY = {on: false, hash: location.hash};
// the settings as the open page was drawn from them: sent along when it saves, so the service keeps what another window or device
// changed meanwhile (and refuses only where both changed the same thing)
const cfgCopy = c => c ? JSON.parse(JSON.stringify(c)) : null;
let CFG_DRAWN = null;
const GUARDED = ['accounts', 'accounts/areas', 'accounts/rules', 'accounts/tax', 'settings/moneymoney', 'settings/receipts', 'settings/access', 'settings/updates'];   // "Allgemein" saves at once
const guarded = () => GUARDED.includes(S.tab + (S.sub ? '/' + S.sub : ''));
(function dirtyListeners() {
  // einmal am Hauptbereich (bleibt bestehen); ob die Seite geschuetzt ist, wird beim Ereignis geprueft
  const main = $('#main');
  const mark = e => { if (!guarded() || e.target.closest('#hi-preview, .toolbar, .rules-page, .sync-table, .ab-sel, .pw-form') || e.target.id === 'k-show-inactive') return; DIRTY.on = true; };
  main.addEventListener('input', mark); main.addEventListener('change', mark);
  main.addEventListener('click', e => { if (guarded() && e.target.closest('.del, #add-bereich, .add-item, .b-mv')) DIRTY.on = true; });
})();
function guardDirty(main) {
  DIRTY.on = false; DIRTY.hash = location.hash; CFG_DRAWN = cfgCopy(S.CFG);
  $$('[data-next]', main).forEach(b => b.addEventListener('click', () => { go(b.dataset.next); }));     // Rueckfrage bei Ungespeichertem: route()
  $$('[data-savenext]', main).forEach(b => b.addEventListener('click', async () => {
    $$('.findings', main).forEach(f => { f.innerHTML = ''; });
    b.disabled = true;
    try {
      if (!(await SAVE[b.dataset.save]())) return;          // Fehler stehen auf der Seite
      await api('/api/report/rebuild', {});
      if (!(await waitRebuild(t('auswertung_wird_mit_den_gespeicherten')))) return;
      await loadAll();
      go(b.dataset.savenext);
    } finally { b.disabled = false; }
  }));
}
async function waitRebuild(title) {
  // Ladeanzeige mit Fortschritt, bis die Auswertung im Hintergrund fertig ist. Laufende Streifen und Sekundenzähler zeigen,
  // dass gearbeitet wird; zwischen zwei Meldungen rückt der Balken langsam weiter (nie über die nächste Etappe hinaus)
  const ov = document.createElement('div'); ov.className = 'busy-ov';
  ov.innerHTML = `<div class="box"><div class="t">${esc(title)} …</div><div class="bar"><i style="width:3%"></i></div><div class="s small muted"><span class="st">${t('startet')}</span><span class="el"></span></div></div>`;
  document.body.appendChild(ov);
  const t0 = Date.now(), P = {target: 0.03, zeige: 0.03};
  const tick = setInterval(() => {
    const sec = Math.round((Date.now() - t0) / 1000); $('.el', ov).textContent = sec >= 2 ? sec + ' s' : '';
    P.zeige = Math.min(Math.max(P.zeige, P.target) + 0.004, P.target + 0.06, 0.97);          // langsam weiter bis kurz vor die nächste Meldung
    $('.bar i', ov).style.width = Math.round(P.zeige * 100) + '%';
  }, 500);
  try {
    for (let i = 0; i < 1500; i++) {
      await new Promise(r => setTimeout(r, i < 5 ? 150 : 400));
      let st; try { st = await api('/api/status'); } catch (e) { if (e.status === 401) return false; continue; }    // locked meanwhile: the sign-in, not the progress
      S.STATUS = st; const b = st.report || {};
      if (!b.running) {
        if (b.error) { toast(t('auswertung_konnte_nicht_aktualisiert_w') + b.error, 8000); return false; }
        clearInterval(tick); $('.bar i', ov).style.width = '100%'; await new Promise(r => setTimeout(r, 200));
        BER.as_of = b.as_of || ''; return true;
      }
      const f = b.progress || {};
      if ((f.share || 0) > P.target) { P.target = f.share; P.zeige = Math.max(P.zeige, P.target); }
      $('.st', ov).textContent = (f.step || t('laeuft')) + ' · ' + Math.round(P.target * 100) + ' %';
    }
    toast(t('die_auswertung_dauert_ungewoehnlich_la'), 8000); return true;
  } finally { clearInterval(tick); ov.remove(); }
}
// Speichern je Einrichtungsschritt (true = gespeichert)
const SAVE = {
  areas: async () => {
    const f = $('#findings-b'), cfg = collectBereiche();
    if (!cfg.areas.length) { showFindings(f, [], t('mindestens_ein_bereich_ist_noetig'), 'error'); return false; }
    if (cfg.areas.some(b => !b.name)) { showFindings(f, [], t('jeder_bereich_braucht_einen_namen'), 'error'); return false; }
    if (cfg.areas.some(b => !b.accounts.length)) { showFindings(f, [], t('jeder_bereich_braucht_mindestens_ein'), 'error'); return false; }
    return saveConfig(cfg, f);
  },
  accounts: async () => saveConfig(collectKonten(), $('#findings-k2')),
};
window.addEventListener('beforeunload', e => { if (DIRTY.on) { e.preventDefault(); e.returnValue = ''; } });
// A figure in a table double-clicked or held (a long touch): toggle(td) -- its row opens or closes. cell(e): the figure, if
// its row opens at all. The click that ends a hold does nothing else, nor does the menu of a long touch.
const HOLD = {at: 0};          // when a hold last opened a row: the page is drawn anew, the click that ends the hold lands on the new table
function rowByFigure(tbl, cell, toggle) {
  let hold = null;
  const stop = () => { if (hold) { clearTimeout(hold.t); hold = null; } };
  tbl.addEventListener('mousedown', e => { if (e.detail > 1 && cell(e)) e.preventDefault(); });          // no word selected by the double click
  tbl.addEventListener('dblclick', e => { const td = cell(e); if (td) toggle(td); });
  tbl.addEventListener('pointerdown', e => { const td = cell(e); stop(); HOLD.at = 0; if (!td || e.button) return;          // a new press: what the last hold blocked is over
    hold = {x: e.clientX, y: e.clientY, t: setTimeout(() => { hold = null; toggle(td); HOLD.at = Date.now(); }, 550)}; });          // after the toggle: its own click goes through
  tbl.addEventListener('pointermove', e => { if (hold && Math.hypot(e.clientX - hold.x, e.clientY - hold.y) > 8) stop(); });
  for (const ev of ['pointerup', 'pointercancel', 'pointerleave']) tbl.addEventListener(ev, stop);
  tbl.addEventListener('click', e => { if (Date.now() - HOLD.at < 700) { e.stopPropagation(); e.preventDefault(); HOLD.at = 0; } }, true);
  tbl.addEventListener('contextmenu', e => { if (Date.now() - HOLD.at < 700 && cell(e)) e.preventDefault(); });
}
function bind(main) {
  $$('tr.group[data-id]', main).forEach(tr => tr.addEventListener('click', () => { S.collapsed[tr.dataset.id] = !S.collapsed[tr.dataset.id]; route(); }));
  // balance sheet: a click on the name opens the position (or the account's history), on a value it marks month and row in the chart
  // -- and, in a row that opens (a position, a portfolio, the key figures under the net worth), opens or closes it as on its name
  const valueCell = (e, tr) => { const td = e.target.closest('td'); return td && td !== tr.firstElementChild && tr.closest('.bil-tbl') ? td : null; };
  // the page is drawn anew: the chart is marked from the row (sel) and the column of the click there
  const redrawnMark = (sel, td, mark) => { const i = td.cellIndex; Promise.resolve(route()).then(() => requestAnimationFrame(() => { const tr = $(sel, $('#main')), c = tr && tr.children[i]; if (c) mark(tr, c); })); };
  const monthOf = td => { const th = td.closest('table').querySelector('thead tr').children[td.cellIndex]; return th ? th.dataset.key : null; };
  $$('.bil-tbl tr.ekq', main).forEach(tr => tr.addEventListener('click', e => {      // equity ratio: the calculation of the month (name: the current one)
    const td = e.target.closest('td'), ks = Object.keys(((B() || {}).balance || {}).equity_ratio?.months || {}), cur = (B() || {}).actual_until;
    const mk = td && td.dataset.m ? td.dataset.m : (ks.includes(cur) ? cur : ks[ks.length - 1]); if (mk && td && (td.dataset.m || td === tr.firstElementChild)) openEkqDrawer(mk); }));
  $$('.bil-tbl tr.total', main).forEach(tr => tr.addEventListener('click', e => {      // net worth: like the month heading, and its dot blinks
    const fold = tr.classList.contains('fold'), td = valueCell(e, tr), focus = (r, c) => { const k = monthOf(c); if (k) bchFocus(k, true); };
    if (fold && (td || e.target.closest('td') === tr.firstElementChild)) S.posOpen._kennzahlen = !S.posOpen._kennzahlen;      // key figures open/close
    if (!td) { if (fold && e.target.closest('td') === tr.firstElementChild) route(); return; }
    if (fold) redrawnMark('.bil-tbl tr.total.fold', td, focus); else focus(tr, td); }));
  $$('tr.pos[data-pos]', main).forEach(tr => tr.addEventListener('click', e => { const td = valueCell(e, tr); S.posOpen[tr.dataset.pos] = !S.posOpen[tr.dataset.pos];
    if (td) redrawnMark(`tr.pos[data-pos="${CSS.escape(tr.dataset.pos)}"]`, td, bchFlash); else route(); }));
  const pa = $('#pos-all', main); if (pa) pa.addEventListener('click', () => { const D = B(), pos = D.balance.rows.filter(r => r.group), open = !pos.every(r => S.posOpen[r.role]); pos.forEach(r => { S.posOpen[r.role] = open; }); route(); });
  $$('[data-dep]', main).forEach(el => el.addEventListener('click', e => { e.stopPropagation(); S.depOpen = S.depOpen || {}; S.depOpen[el.dataset.dep] = !S.depOpen[el.dataset.dep]; route(); }));
  // cash flow / planning: the names as one pinned piece (see freezeNames); a click on the triangle or the name opens and closes
  // a row (not on a field or link in it)
  $$('table.cf-tbl:not(.cf-names)', main).forEach(freezeNames);
  $$('.cf-tbl td.to-bal', main).forEach(td => td.addEventListener('click', () => cfToBalance(td.dataset.bal)));
  if (S.tab === 'cashflow') {
    const D = B(), endM = D && (cfMonths(D, S.cfZeit)[0] || []).slice(-1)[0];
    $$('table.cf-tbl:not(.cf-names) thead th[data-key]', main).forEach(th => { const k = th.dataset.key;
      if (k === endM || (k.length === 4 && S.cfZeit === k)) th.classList.add('cf-endsel');          // the charts end here
      th.title = (th.title ? th.title + ' · ' : '') + t('cf_th_tip');
      th.addEventListener('click', () => { const pick = cfPick(D); let v, b;
        if (k.length === 7) { b = k; v = pick.find(m => m >= mShift(k, -11)) || k; } else { const ys = pick.filter(m => m.startsWith(k)); if (!ys.length) return; v = ys[0]; b = ys[ys.length - 1]; }
        cfSetRange(v, b); }); });
  }          // the bank balance: shown in the balance sheet
  // a figure: the bookings behind it -- of a single row or of all rows under it (e.g. everything unclear at once), in the side panel
  $$('.cf-tbl:not(.ptable) tr[data-zs] td.tx', main).forEach(td => td.addEventListener('click', e => {
    e.stopPropagation(); const tr = td.parentNode, c = (CF.tblCols || [])[td.cellIndex - 1], row = (CF.zs || [])[+tr.dataset.zs]; if (!c || !row) return;
    const keys = row.zs.filter(z => z.n && c.months.some(m => z.n[m])).map(z => CF.zsec.get(z) + '\u001f' + z.row); if (!keys.length) return;
    cfOpenTx({cfRows: keys, months: c.months, title: row.label + ' · ' + c.label}); }));
  // the check against the balance sheet: its reasons, and the bookings behind them (left out, a transfer in transit)
  $$('.cf-tbl:not(.ptable) tr.check td.tx[data-chk]', main).forEach(td => td.addEventListener('click', e => {
    e.stopPropagation(); const c = (CF.tblCols || [])[td.cellIndex - 1], ue = (B().cashflow || {}).reconciliation || {}; if (!c) return;
    const why = td.dataset.chk, liq = why === 'reasons_cash', ms = c.months.filter(m => m <= B().actual_until);          // as in the cell's tooltip (month named in a longer column)
    const gr = ueGruende(ue, ms, why).split('\n').filter(Boolean), n = ms.reduce((a, m) => a + ((ue[m] || {})[liq ? 'n_liq' : 'n_nw'] || 0), 0);
    cfOpenTx({cfRows: n ? ['\u001f' + (liq ? 'check_cash' : 'check_nw')] : [], months: c.months, title: t('cf_abgleich') + ' · ' + c.label,
      kopf: `<ul class="cf-tx-why">${gr.map(g => `<li>${esc(g)}</li>`).join('')}</ul>`}); }));
  // a category's figure: the transactions behind it (that column's closed months), as from the heat map
  $$('.cf-tbl:not(.ptable) tr.det[data-kat] td:not(:first-child)', main).forEach(td => td.addEventListener('click', () => {
    const c = (CF.tblCols || [])[td.cellIndex - 1], kat = td.parentNode.dataset.kat; if (!c || !c.months.length || !kat) return;
    cfOpenTx({kats: [kat], months: c.months, title: CP(kat).split(' › ').slice(-1)[0] + ' · ' + c.label}); }));
  // a figure double-clicked or held: its row opens or closes, as on its name (the side panel of the first click closes again)
  $$('.cf-tbl:not(.ptable):not(.cf-names)', main).forEach(tbl => rowByFigure(tbl,
    e => { const td = e.target.closest('td'); return td && td !== td.parentNode.firstElementChild && td.parentNode.matches('tr[data-tog]') ? td : null; },
    td => { closeDrawer(); const n = td.parentNode.firstElementChild; if (n) n.dispatchEvent(new MouseEvent('click', {bubbles: true})); }));
  // the balance sheet opens a row by a single click on a figure (see above): no word selected by clicking twice
  $$('.bil-tbl table', main).forEach(tbl => tbl.addEventListener('mousedown', e => { const td = e.target.closest('td'), tr = td && td.parentNode;
    if (e.detail > 1 && td && td !== tr.firstElementChild && (tr.matches('tr.pos[data-pos], tr.total.fold') || tr.querySelector('[data-dep]'))) e.preventDefault(); }));
  // a click on a row's name opens or closes it (its figures show the bookings behind them; in planning they are edited)
  $$('.cf-tbl [data-tog]', main).forEach(el => el.addEventListener('click', e => {
    if (el.tagName === 'TR' && (e.target.closest('td') !== el.firstElementChild || e.target.closest('select, input, a, .edit, .hq, .tag, .to-bal, .tipped, button:not(.disc)'))) return;
    e.stopPropagation(); S.cfTog[el.dataset.tog] = !cfOpen(el.dataset.tog, +el.dataset.depth);
    // the page is drawn anew: the row stays where it was on the screen (not scrolled up)
    const id = el.dataset.tog, top0 = el.getBoundingClientRect().top;
    Promise.resolve(route()).then(() => { const r = $(`.cf-tbl:not(.cf-names) [data-tog="${CSS.escape(id)}"]`); if (!r) return;
      let sc = document.scrollingElement; for (let p = r.parentElement; p; p = p.parentElement) { const o = getComputedStyle(p).overflowY; if ((o === 'auto' || o === 'scroll') && p.scrollHeight > p.clientHeight) { sc = p; break; } }
      sc.scrollTop += r.getBoundingClientRect().top - top0; }); }));
  $$('.card[data-b]', main).forEach(c => c.addEventListener('click', () => { S.area = c.dataset.b; bereichSeg(); route(); }));
  // Waagerecht: aktuelle Spalte (Monat bzw. Jahr) rechts im Blick, ältere Jahre links davon; Plan-Spalten rechts anschließend
  if (['balance', 'cashflow', 'planning'].includes(S.tab)) $$('.wrap', main).forEach((w, k) => {
    snapTable(w);
    const c = $('th[data-cur]', w), keep = (SCROLL.keepX || [])[k];
    if (S.toEarlier) { w.scrollLeft = 0; return; }                // earlier months shown: start with them
    // the same page redrawn (a row opened, a chart clicked): the table stays where it was, without moving (not after a switch
    // between months and years: other columns)
    if (keep && keep.n === w.querySelectorAll('thead th').length) { scrollBack(w, keep); return; }
    // balance sheet: the current month (or year) is the rightmost column; elsewhere with plan a part of the plan stays in view
    if (c && w.scrollWidth > w.clientWidth) w.scrollLeft = S.tab === 'cashflow' ? cfScrollTo(w, c)
      : snapLeft(w, colX(w, c) + c.offsetWidth - w.clientWidth * (S.tab !== 'balance' && planOn() ? 0.62 : 1));
  });
  S.toEarlier = false;
  if (S.tab === 'balance') { bindBilanzChart(main); bindBilanzLines(main); setTimeout(() => balFlash(main), 30); }
  const vs = $('#vorschlag-an', main); if (vs) vs.addEventListener('change', e => { S.proposal = e.target.checked; route(); });
  $$('[data-goto]', main).forEach(c => c.addEventListener('click', e => { if (!e.target.closest('a, button, input, select')) go(c.dataset.goto); }));
  $$('[data-xlsx]', main).forEach(b => b.addEventListener('click', () => download(b.dataset.xlsx === 'property' ? `/api/export/property.xlsx?id=${encodeURIComponent(b.dataset.immo || '')}&calculation=${encodeURIComponent(b.dataset.kalk || '')}` : `/api/export/${b.dataset.xlsx}.xlsx?area=${encodeURIComponent(b.dataset.bereich || S.area || '')}&mode=${S.mode === 'years' ? 'years' : 'months'}`
    + (b.dataset.xlsx === 'transactions' ? '&' + umsQuery().toString() : '')
    + (b.dataset.xlsx === 'balance' ? `&open=${encodeURIComponent(Object.keys(S.posOpen || {}).filter(k => S.posOpen[k]).join(','))}&dep=${encodeURIComponent(Object.keys(S.depOpen || {}).filter(k => S.depOpen[k]).join(','))}&all=${S.alleB ? 1 : 0}` : ''))));

  // Einrichtung
  const wc = $('#w-check', main); if (wc) wc.addEventListener('click', async () => {
    wc.classList.add('busy'); wc.disabled = true; const busy = $('#w-busy'); if (busy) busy.classList.remove('hidden'); $('#w-findings').innerHTML = '';
    const stop = readProgress();
    let r; try { r = await api('/api/check', {}); } catch (e) { stop(); wc.classList.remove('busy'); wc.disabled = false; if (busy) busy.classList.add('hidden'); showFindings($('#w-findings'), [], e.message, 'error'); return; }
    stop();
    if (!r.available) { wc.classList.remove('busy'); wc.disabled = false; if (busy) busy.classList.add('hidden'); showFindings($('#w-findings'), [], r.text, 'error'); return; }
    S.KONTEN = r.accounts; S.KATS = r.categories || S.KATS; VB.checked = location.hash; await softRoute(); showFindings($('#w-findings'), r.findings, t('verbindung_steht') + r.accounts.length + t('konten_gelesen'), 'ok'); });
  const wr = $('#w-report', main); if (wr) wr.addEventListener('click', () => rebuildReport(true));
  const et = $('#e-theme', main); if (et) et.addEventListener('change', () => { try { LS.set('kontor.theme', et.value); } catch (e) {} applyTheme(et.value); route(); });
  for (const wl of [$('#w-lang', main), $('#e-lang', main)]) if (wl) wl.addEventListener('change', async () => { if (wl.value === LANG) return; try { await api('/api/language', {language: wl.value}); setLang(wl.value); } catch (e) { wl.value = LANG; toast(e.message, 5000); } });
  const abr = $('#add-bereich', main); if (abr) { bindBereichKonten(main); abr.addEventListener('click', () => { $('#bereiche').insertAdjacentHTML('beforeend', bereichForm({name: t('neuer_bereich'), id: '', accounts: [], main_area: false}, $$('#bereiche .item').length)); bindDel(main); bindBereichKonten($('#bereiche .item:last-child')); bereichMvState(); }); }
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
  const sbr = $('#save-bereiche', main); if (sbr) sbr.addEventListener('click', async () => { if (await SAVE.areas()) { const box = $('#findings-b').innerHTML; await rebuildReport(false); const f = $('#findings-b'); if (f) f.innerHTML = box; } });
  const skn = $('#save-konten', main); if (skn) skn.addEventListener('click', async () => { if (await SAVE.accounts()) { const box = $('#findings-k2').innerHTML; await rebuildReport(false); const f = $('#findings-k2'); if (f) f.innerHTML = box; } });
  $$('.k-hist', main).forEach(b => b.addEventListener('click', async e => { const btn = e.target; btn.classList.add('busy'); try { const tr = btn.closest('tr'), sel = $('.k-verlauf', tr); await openHistDrawer(tr.dataset.uuid, sel ? sel.value : null); } catch (er) { toast(t('verlauf_konnte_nicht_geladen_werden') + er.message, 6000); } finally { btn.classList.remove('busy'); } }));
  const hp = $('#hi-pick', main); if (hp) hp.addEventListener('click', () => { const inp = $('#file-input'); inp.value = ''; inp.setAttribute('accept', '.csv,.txt,.xlsx,.xlsm'); inp.removeAttribute('capture'); inp.onchange = () => { if (inp.files[0]) histImportPreview(inp.files[0]); }; inp.click(); });
  const hd = $('#hi-drop', main); if (hd) { hd.addEventListener('dragover', e => { e.preventDefault(); hd.classList.add('over'); }); hd.addEventListener('dragleave', () => hd.classList.remove('over')); hd.addEventListener('drop', e => { e.preventDefault(); hd.classList.remove('over'); if (e.dataTransfer.files[0]) histImportPreview(e.dataTransfer.files[0]); }); if (HI) renderHistImport(); }
  if ($('#mmh-names', main)) mmhNames();
  const mz = $('#mmh-zeigen', main); if (mz) mz.addEventListener('click', async () => { try { await api('/api/history/mm-reveal', {}); } catch (e) { toast(e.message, 6000); } });
  const md = $('#mmh-drop', main); if (md) {
    const send = async file => {
      // Datei (verschlüsselt) direkt als Bytes an den Dienst auf diesem Mac; nichts davon wird gespeichert
      const res = $('#mmh-res', main); if (!file) return;
      if (MMH.busy) return; MMH.busy = true; md.classList.add('busy'); res.innerHTML = `<div class="working"><span class="spin"></span>${t('datei_wird_uebergeben')}</div>`;
      try {
        const r = await fetch('/api/history/mm-import', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/octet-stream', 'X-CSRF-Token': S.csrf, 'X-Kontor-Net': 'direct'}, body: file});
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.error || (t('fehler') + r.status));
        if (j.running) await mmhFollow(); else showFindings($('#mmh-res') || res, [], j.text, 'error');
      } catch (e) { showFindings($('#mmh-res') || res, [], e.message, 'error'); }
      finally { MMH.busy = false; const d2 = $('#mmh-drop'); if (d2) d2.classList.remove('busy'); }
    };
    md.addEventListener('dragover', e => { e.preventDefault(); md.classList.add('over'); });
    md.addEventListener('dragleave', () => md.classList.remove('over'));
    md.addEventListener('drop', e => { e.preventDefault(); md.classList.remove('over'); send(e.dataTransfer.files[0]); });
    $('#mmh-pick', main).addEventListener('click', () => $('#mmh-file', main).click());
    $('#mmh-file', main).addEventListener('change', e => { send(e.target.files[0]); e.target.value = ''; });
  }
  const go = $('#gap-ok', main); if (go) go.addEventListener('click', async () => { try { await api('/api/sync/gaps', {}); S.STATUS = await api('/api/status'); statusMini(); softRoute(); } catch (e) { toast(e.message, 5000); } });
  $$('.dep-hist', main).forEach(b => b.addEventListener('click', async () => { b.classList.add('busy'); try { await openHistDrawer(b.closest('tr').dataset.uuid); } catch (e) { toast(e.message, 6000); } finally { b.classList.remove('busy'); } }));
  const sn = $('#sync-now', main); if (sn) sn.addEventListener('click', async () => { sn.classList.add('busy'); try { await syncNow(); } finally { sn.classList.remove('busy'); } });
  const sf = $('#sync-full', main); if (sf) sf.addEventListener('click', async () => { sf.classList.add('busy'); try { await syncNow(true); } finally { sf.classList.remove('busy'); } });
  $$('.ab-sel', main).forEach(sel => sel.addEventListener('change', async () => {
    try { await api('/api/sync', {account: sel.closest('tr').dataset.uuid, fetched: sel.value === 'online'}); S.STATUS = await api('/api/status'); S.KONTEN = (await api('/api/accounts')).accounts || S.KONTEN; statusMini(); softRoute(); }
    catch (e) { toast(e.message, 5000); sel.value = sel.value === 'online' ? 'offline' : 'online'; }
  }));
  const ksi = $('#k-show-inactive', main); if (ksi) ksi.addEventListener('change', e => $$('tr.inactive', main).forEach(tr => tr.style.display = e.target.checked ? '' : 'none'));
  $$('.k-show', main).forEach(sel => sel.addEventListener('change', () => { const tr = sel.closest('tr'); tr.classList.toggle('inactive', kontoHidden(sel.value, tr.dataset.auto === '1')); }));
  $$('.acct-table select[data-vor]', main).forEach(sel => sel.addEventListener('change', () => {
    sel.classList.toggle('proposal', sel.value === sel.dataset.vor);
  }));
  const kin = $('#k-inaktiv', main); if (kin) kin.addEventListener('input', () => $$('tr[data-grenze]', main).forEach(tr => {   // ausgegraut sofort neu
    tr.dataset.auto = autoHidden(tr.dataset.grenze, kin.value) ? '1' : '0';
    const on = kontoHidden($('.k-show', tr).value, tr.dataset.auto === '1'); tr.classList.toggle('inactive', on);
    if (!$('#k-show-inactive', main).checked) tr.style.display = on ? 'none' : '';
  }));

  // Bilanz
  $$('tr.acct[data-id]', main).forEach(tr => tr.addEventListener('click', e => { const td = valueCell(e, tr), dep = td && $('[data-dep]', tr);
    if (!td) openHistDrawer(tr.dataset.id);
    else if (dep) { S.depOpen = S.depOpen || {}; S.depOpen[dep.dataset.dep] = !S.depOpen[dep.dataset.dep]; redrawnMark(`tr.acct[data-id="${CSS.escape(tr.dataset.id)}"]`, td, bchFlash); }      // a portfolio: its securities open/close
    else bchFlash(tr, td); }));
  $$('tr.wpr[data-wp]', main).forEach(tr => tr.addEventListener('click', e => { const td = valueCell(e, tr); if (td) bchFlash(tr, td); else openWpDrawer(tr.dataset.wp); }));
  $$('tr.transit', main).forEach(tr => tr.addEventListener('click', e => { const td = valueCell(e, tr);          // a month: what was under way at its end
    if (!td) { openTransitDrawer(); return; } bchFlash(tr, td);
    const k = td.closest('table').querySelector('thead tr').children[td.cellIndex]?.dataset.key || '', D = B();
    const m = k.length === 7 ? k : k.length === 4 ? ((D.actual_until || '').startsWith(k) ? D.actual_until : k + '-12') : null; if (m) openTransitDrawer(m); }));

  // Planung: a rule (the area's default, a position, a category) -- asked first where your own values or rules lie beneath it
  $$('.edit .meth', main).forEach(sel => sel.addEventListener('change', () => { const box = sel.closest('.edit'); $('.amount', box).classList.toggle('hidden', !['fix', 'yearly_amount'].includes(sel.value)); syncNamesOf(box); }));
  $$('.edit .steig-art', main).forEach(sel => sel.addEventListener('change', () => { const box = sel.closest('.edit'), inp = $('.steig', box); inp.classList.toggle('hidden', sel.value !== 'own'); if (sel.value === 'own') inp.focus(); syncNamesOf(box); }));
  $$('.edit .save', main).forEach(b => b.addEventListener('click', e => { const box = e.target.closest('.edit'), ga = $('.steig-art', box).value;
    planRule(Object.assign({row: box.dataset.key, method: $('.meth', box).value, amount: $('.amount', box).value, increase: ga === 'own' ? $('.steig', box).value : ga}, box.dataset.cat != null ? {category: box.dataset.cat} : {})); }));
  $$('.reset-row', main).forEach(b => b.addEventListener('click', async e => { const x = e.target.closest('.reset-row'); await plan(Object.assign({row: x.dataset.key, clear_all_overrides: true}, x.dataset.cat != null ? {category: x.dataset.cat} : {})); }));
  $$('td.plan.editable', main).forEach(td => td.addEventListener('dblclick', () => {
    if ($('input', td)) return;
    TIP.hide();
    const tr = td.closest('tr'), key = tr.dataset.key, cat = tr.dataset.cat, m = td.dataset.month, old = [...td.childNodes].filter(n => n.nodeName !== 'DIV').map(n => n.textContent).join('').split(GRP).join('').trim();
    td.classList.remove('tipped');
    td.innerHTML = `<input type="text" value="${esc(old === '–' ? '' : old)}" style="width:90px;text-align:right;padding:1px 4px" title="${t('leer_vorschlag_verwenden')}">`;
    const inp = $('input', td); inp.focus(); inp.select();
    let done = false; const fin = async save => {
      if (done) return;
      const v = save ? numIn(inp.value) : null;
      if (save && Number.isNaN(v)) { toast(t('zahl_unlesbar', inp.value.trim()), 6000); inp.focus(); inp.select(); return; }          // stays open: not saved, not thrown away
      done = true; if (save) await plan(Object.assign({row: key, month: m, value: v == null ? '' : v}, cat != null ? {category: cat} : {})); else route();
    };
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') fin(true); if (e.key === 'Escape') fin(false); }); inp.addEventListener('blur', () => fin(true));
  }));
  $$('#p_model button', main).forEach(b => b.addEventListener('click', () => planRule({model: b.dataset.m})));
  const ps = $('#p_save', main); if (ps) ps.addEventListener('click', () => planRule({parameter: {horizon_months: +$('#p_horizont').value, inflation_percent_pa: +$('#p_infl').value, income_increase_percent_pa: +$('#p_se').value, expense_increase_percent_pa: $('#p_sa').value === '' ? '' : +$('#p_sa').value, return_percent_pa: +$('#p_rendite').value},
    defaults: {income: {method: $('#p_m_in').value, increase: $('#p_g_in').value}, expenses: {method: $('#p_m_out').value, increase: $('#p_g_out').value}}}));
  const pr = $('#p_reset', main); if (pr) pr.addEventListener('click', () => { if (confirm(t('alle_planeinstellungen_und_ueberschrei') + BN() + t('loeschen_2'))) plan({reset_flag: true}); });
  $$('.save-loan', main).forEach(b => b.addEventListener('click', e => { const tr = e.target.closest('tr'); plan({loans: {[tr.dataset.loan]: {interest_percent_pa: $('.lz', tr).value, model: $('.lm', tr).value, payment: $('.lp', tr).value}}}); }));
  $$('.save-wert', main).forEach(b => b.addEventListener('click', e => { const tr = e.target.closest('tr'); const p = $('.wp', tr).value, bs = $('.wb', tr).value, br = $('.wbr', tr).value, an = $('.wa', tr).value; plan({appreciation: {[tr.dataset.acct]: (p === '' && bs === '' && !br) ? null : {percent_pa: p, base: bs, area: br, share: an}}}); }));
  $$('.ev-save', main).forEach(b => b.addEventListener('click', e => { const tr = e.target.closest('.ev-row'); const ev = {id: tr.dataset.id || undefined, text: $('.ev-text', tr).value, kind: $('.ev-art', tr).value, amount: $('.ev-betrag', tr).value, month: $('.ev-monat', tr).value, recurrence: $('.ev-wdh', tr).value, date_to: $('.ev-bis', tr).value, date_from: $('.ev-von', tr).value, after: $('.ev-nach', tr).value, active: $('.ev-aktiv', tr).checked}; if (!ev.text.trim()) return toast(t('bezeichnung_fehlt')); if (!ev.amount) return toast(t('betrag_fehlt')); plan({event: ev}); }));
  $$('.ev-del', main).forEach(b => b.addEventListener('click', e => { const tr = e.target.closest('.ev-row'); if (confirm(t('ereignis_loeschen'))) plan({event: {id: tr.dataset.id, delete: true}}); }));

  // Buchungen
  const autoSw = $('#auto-book', main); if (autoSw) autoSw.addEventListener('change', async () => {      // book automatically (on) or with approval (off)
    if (autoSw.checked && !confirm(t('modus_auto_frage'))) { autoSw.checked = false; return; }
    const cfg = JSON.parse(JSON.stringify(S.CFG)); cfg.dry_run = !autoSw.checked;
    // back to "with approval": never held up by errors elsewhere in the settings; on: only without errors (they are named)
    autoSw.disabled = true;          // one switch at a time: a second click waits for the first
    try { await api('/api/config', {config: cfg, anyway: cfg.dry_run, seen: CFG_DRAWN}, 'PUT'); S.CFG = await api('/api/config'); S.STATUS = await api('/api/status'); route(); }
    catch (e) { autoSw.checked = !autoSw.checked; toast([e.message].concat(((e.data || {}).findings || []).filter(f => f.severity === 'error').slice(0, 3).map(f => f.text)).join('\n'), 8000); }
    finally { autoSw.disabled = false; }
  });
  const bt = $('.bk-table', main);
  if (bt) {
    const rows = () => $$('tr[data-key]', bt).filter(r => r.dataset.key && !r.classList.contains('gone'));
    const count = () => { const n = rows().filter(r => !BOOK.off.has(r.dataset.key)).length, b = $('#run-live', main); if (b) { $('#sel-n', b).textContent = n; b.disabled = !n || !(S.STATUS || {}).local; } };
    bt.addEventListener('change', e => {
      // what you leave out or change moves the bookings after it: the list is recalculated (what you see is what is booked)
      // all or none: every booking of the list, also those added by a recalculation (none: nothing left to work out)
      if (e.target.id === 'bk-all') { const all = bkRows((BOOK.runs || {}).last_run || {}).map(x => x.k).filter(Boolean);
        BOOK.off = e.target.checked ? new Set() : new Set(all);
        $$('tr[data-key]', bt).forEach(x => { if (!x.dataset.key) return; x.classList.toggle('off', !e.target.checked); const c = $('.bk-on', x); if (c) c.checked = e.target.checked; });
        count(); return bkRecalc(); }
      const r = e.target.closest('tr[data-key]'); if (!r || !r.dataset.key) return;
      const key = r.dataset.key;
      if (e.target.classList.contains('bk-on')) { r.classList.toggle('off', !e.target.checked); if (e.target.checked) BOOK.off.delete(key); else BOOK.off.add(key); count(); return bkRecalc(); }
      const l = BOOK.runs.last_run || {}, v = (l.proposals || []).find(x => x.key === key) || BOOK.extra[key] || {}, ch = BOOK.edits[key] = BOOK.edits[key] || {};
      const now = (bkRows(l).find(x => x.k === key) || {}).b ?? v.amount;          // the amount without your change
      if (e.target.classList.contains('bk-d')) { if (e.target.value && e.target.value !== v.date) ch.date = e.target.value; else delete ch.date; }
      if (e.target.classList.contains('bk-b')) { const n = parseFloat(e.target.value); if (!isNaN(n) && Math.abs(n) >= 0.01 && (ch.amount != null || Math.abs(n - now) >= 0.005)) ch.amount = Math.round(n * 100) / 100; else delete ch.amount; }
      if (e.target.classList.contains('bk-z')) { const z = String(v.text || '').replace(/\s*·?\s*#kontor-[a-z]+-[A-Za-z0-9-]+/g, '').trim(); if (e.target.value.trim() !== z) ch.purpose = e.target.value.trim(); else delete ch.purpose; }
      if (!Object.keys(ch).length) delete BOOK.edits[key];
      if (e.target.classList.contains('bk-b') || e.target.classList.contains('bk-d')) bkRecalc();
    });
    bt.addEventListener('click', async e => {
      const r = e.target.closest('tr[data-key]'); if (!r || !r.dataset.key) return;
      if (e.target.closest('.bk-edit')) { const k = r.dataset.key, on = !BOOK.editing.has(k); if (on) { BOOK.editing.add(k); r.classList.add('editing'); ($('.bk-b', r) || $('.bk-z', r)).focus(); } else { BOOK.editing.delete(k); route(); } return; }
      if (e.target.closest('.bk-rej')) {
        // half of a pair entered by hand (days apart): both halves at once
        const l = (BOOK.runs || {}).last_run || {}, v = (l.proposals || []).find(x => x.key === r.dataset.key) || {}, other = v.pair && (l.proposals || []).some(x => x.key === v.pair) ? v.pair : null;
        if (!confirm(t(other ? 'verwerfen_paar_frage' : 'verwerfen_frage'))) return;
        const keys = other ? [r.dataset.key, other] : [r.dataset.key];
        try {
          await api('/api/bookings/reject', {keys}); keys.forEach(k => { BOOK.off.delete(k); delete BOOK.edits[k]; delete BOOK.extra[k]; });
          toast(t('verworfen_ok')); BOOK.calc = null; await route();
          if (BOOK.off.size || Object.keys(BOOK.edits).length) bkRecalc();
        } catch (er) { toast(er.message, 5000); }
      }
    });
    count();
    if (BOOK.needCalc) { BOOK.needCalc = false; bkRecalc(); }          // noted ones not chosen: the list as it would be booked
  }
  $$('.re-book', main).forEach(b => b.addEventListener('click', async () => {
    // propose again: off the list; if it is still needed it waits for approval (planned again at once) -- "Not booked" stays
    // open and in its place, so several can be proposed again one after the other
    try { b.disabled = true; await api('/api/bookings/restore', {key: b.dataset.key}); toast(t('wieder_vorgeschlagen'), 3000); await routeKeeping('#nb-list'); nbRefresh(); } catch (e) { b.disabled = false; toast(e.message, 5000); }
  }));
  // only what the approval list depends on: the accounts of the rules read again, the list planned again (nothing booked)
  const rf = $('#bk-refresh', main); if (rf) rf.addEventListener('click', async () => {
    if (SYNC.busy) return;
    SYNC.busy = true; rf.disabled = true; rf.classList.add('busy'); statusMini();
    try {
      const r = await api('/api/bookings/refresh', {});
      if (r.status === 'unavailable' || r.status === 'error') toast(r.text || t('synchronisieren_fehlgeschlagen'), 7000);
      else toast(r.wartend ? (r.wartend === 1 ? t('aktualisiert_1') : t('aktualisiert_n', r.wartend)) : t('aktualisiert_0'), 4000);
      S.STATUS = await api('/api/status');
    } catch (e) { toast(e.message, 6000); }
    finally { SYNC.busy = false; statusMini(); route(); }
  });
  const rl = $('#run-live', main); if (rl) rl.addEventListener('click', () => {
    // what is ticked, with the amount shown: booked only if it is still the same
    const pick = bkRows((BOOK.runs || {}).last_run || {}).filter(r => r.k && !r.off && !r.gone);
    if (!pick.length || !confirm(t('jetzt_buchen_buchungen_werden_jetzt'))) return;
    const freigabe = {}; pick.forEach(r => { freigabe[r.k] = {...(BOOK.edits[r.k] || {}), shown: r.b}; });
    BOOK.time = null;                 // what stays waiting starts a new round (all ticked, no changes)
    startRun(false, freigabe);
  });

  // Steuer
  const sj = $('#st-jahr', main); if (sj) sj.addEventListener('change', e => { S.steuerJahr = e.target.value; route(); });
  const se = $('#st-ent', main); if (se) se.addEventListener('change', e => { S.steuerEnt = e.target.value; route(); });
  const sb = $('#st-belege', main); if (sb) sb.addEventListener('click', async () => { try { const r = await belegeApi('/api/receipts/export', {year: S.steuerJahr, entity: S.steuerEnt}); toast(t('export_erstellt') + r.file, 8000); } catch (e) { toast(e.message, 6000); } });
  const afa = $('#afa-save', main); if (afa) afa.addEventListener('click', async () => {
    const cfg = JSON.parse(JSON.stringify(S.CFG)); cfg.tax = cfg.tax || {}; cfg.tax.depreciation = cfg.tax.depreciation || {};
    $$('.depreciation', main).forEach(i => { const o = i.dataset.obj; cfg.tax.depreciation[o] = typeof cfg.tax.depreciation[o] === 'object' && cfg.tax.depreciation[o] ? cfg.tax.depreciation[o] : {}; if (i.value === '') delete cfg.tax.depreciation[o][S.steuerJahr]; else cfg.tax.depreciation[o][S.steuerJahr] = parseFloat(i.value); });
    const fe = document.createElement('div'); if (await saveConfig(cfg, fe)) toast(t('afa_gespeichert_wirkt_nach_dem')); else if (fe.textContent.trim()) toast(fe.textContent.trim(), 8000);
  });

  // Umsaetze & Belege
  const uf = S.uf;
  const bindF = (id, key, prop = 'value') => { const el = $(id, main); if (el) el.addEventListener('change', e => { uf[key] = e.target[prop]; S.sel.clear(); route(); }); };
  $$('[data-ids-x]', main).forEach(b => b.addEventListener('click', () => { Object.assign(uf, {ids: null, cfRows: null, title: '', date_from: '', date_to: ''}); S.sel.clear(); route(); }));
  const ux = $('#uf-chip-x', main); if (ux) ux.addEventListener('click', () => { Object.assign(uf, {ids: null, cfRows: null, kats: null, date_from: '', date_to: '', title: '', est: false, katsLabel: '', mitOhne: false, uncategorized_flag: uf.title ? false : uf.uncategorized_flag, direction: uf.title || uf.rChart ? '' : uf.direction, rChart: false}); S.sel.clear(); route(); });
  for (const [id, key] of [['#uf-von', 'date_from'], ['#uf-bis', 'date_to']]) { const el = $(id, main); if (el) el.addEventListener('change', () => { uf[key] = el.value; uf.title = ''; S.sel.clear(); route(); }); }
  const ka = $('#uf-kat-add', main); if (ka) ka.addEventListener('change', () => { const v = ka.value.trim(); if (!v) return;
    const k = v.split(' › ').join(' / '); uf.kats = [...new Set([...(uf.katsLabel ? [] : uf.kats || []), k])]; Object.assign(uf, {title: '', est: false, katsLabel: '', mitOhne: false}); S.sel.clear(); route(); });
  $$('[data-kat-all]', main).forEach(b => b.addEventListener('click', () => { Object.assign(uf, {kats: null, katsLabel: '', mitOhne: false, title: '', est: false}, uf.rChart ? {direction: '', rChart: false} : {}); S.sel.clear(); route(); }));
  $$('[data-kat-x]', main).forEach(b => b.addEventListener('click', () => { const k = (uf.kats || []).slice(); k.splice(+b.dataset.katX, 1); uf.kats = k.length ? k : null; uf.title = ''; uf.est = false; S.sel.clear(); route(); }));
  bindF('#uf-ent', 'entity'); bindF('#uf-jahr', 'year'); bindF('#uf-konto', 'account'); bindF('#uf-ob', 'ohne_beleg', 'checked'); bindF('#uf-ok', 'uncategorized_flag', 'checked');
  const q = $('#uf-q', main); if (q) { let t; q.addEventListener('input', e => { clearTimeout(t); t = setTimeout(() => { uf.q = e.target.value; route().then(() => { const n = $('#uf-q'); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } }); }, 350); }); }
  $$('.seg button[data-r]', main).forEach(b => b.addEventListener('click', () => { uf.direction = b.dataset.r; route(); }));
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
    $('#sel-all', tbl).addEventListener('change', e => { S.sel.clear(); if (e.target.checked) UMS.transactions.forEach(u => S.sel.add(u.id)); route(); });
  }
  const bc = $('#bulk-clear', main); if (bc) bc.addEventListener('click', () => { S.sel.clear(); route(); });
  const bk = $('#bulk-cat-btn', main); if (bk) bk.addEventListener('click', async () => { const kat = $('#bulk-cat').value.trim(); if (!kat) return toast(t('kategorie_waehlen')); if (!confirm(S.sel.size + t('umsaetzen_die_kategorie') + kat + t('zuweisen'))) return; try { const r = await assignCats([...S.sel], kat, {wait: true}); toast(assignMsg(r), 6000); S.sel.clear(); await loadAll(); route(); } catch (e) { toast(e.message, 6000); } });
  const bf = $('#bl-folder', main); if (bf) bf.addEventListener('click', async () => { try { await belegeApi('/api/receipts/open', {}); } catch (e) { toast(e.message, 5000); } });
  const be = $('#bl-export', main); if (be) be.addEventListener('click', async () => { const jahr = prompt(t('jahr_leer_alle'), uf.year || new Date().getFullYear()); if (jahr === null) return; try { const r = await belegeApi('/api/receipts/export', {year: jahr, entity: uf.entity}); toast(t('export_erstellt') + r.file, 9000); } catch (e) { toast(e.message, 6000); } });

  // Buchungsregeln: every change marks the page unsaved and updates target/actual/difference (debounced); ⌘S saves
  const rp = $('.rules-page', main);
  if (rp) {
    const sr = $('#save-rules', rp), st = $('#rules-state', rp);
    let pvTimer = null, pvSeq = 0;
    const preview = async () => { const n = ++pvSeq; try { const r = await api('/api/rules/preview', {config: collectRules()}); if (n === pvSeq) rulesPreviewShow(rp, r); } catch (e) { /* preview only */ } };
    const rulesJson = () => { const c = collectRules(); return JSON.stringify([c.loans, c.companies, $$('#mirrors .gk-row', rp).map(r => [$('.g-a', r).value, $('.g-b', r).value, backValue(r), !!r.dataset.review])]); };   // rows as they stand, also unfinished ones
    let saved = rulesJson();
    // the rules this page was drawn from: sent with its save -- refused if the assistant's card changed one meanwhile (S.CFG is
    // loaded anew in the background, the page with unsaved changes is not drawn anew: so taken now, renewed only by its own save)
    const seenNow = () => JSON.parse(JSON.stringify([S.CFG.loans || [], S.CFG.companies || [], S.CFG.account_mirrors || []]));
    let seen = seenNow();
    const changed = () => {
      const same = rulesJson() === saved;
      sr.disabled = same; DIRTY.on = !same; st.textContent = t(same ? 'regeln_gespeichert' : 'regeln_ungespeichert');
      clearTimeout(pvTimer); pvTimer = setTimeout(preview, 450);
    };
    $('#add-loan', rp).addEventListener('click', () => {
      $('#loans', rp).insertAdjacentHTML('beforeend', loanForm({name: t('neues_darlehen'), _new: true, from_date: new Date().toISOString().slice(0, 10), interest: {model: 'yearly_base', rate_list: [], booking_day: 'with_payment'}, booking: {category_repayment: 'Umbuchung'}}, $$('#loans .item', rp).length));
      bindDel(main); changed();
      const it = $('#loans', rp).lastElementChild; it.scrollIntoView({block: 'nearest', behavior: 'smooth'}); const n = $('.f-name', it); n.focus(); n.select();
    });
    rp.addEventListener('click', e => {          // a rule from the assistant confirmed: unmarked (saved with the page)
      const ok = e.target.closest('.rv-ok'); if (!ok) return;
      e.preventDefault(); e.stopPropagation();
      const el = ok.closest('[data-review]'); if (!el) return;
      delete el.dataset.review; el.querySelectorAll('.rv-pill, .rv-ok').forEach(x => { if (x.closest('[data-review], .rule, .co-card, .gk-row') === el) x.remove(); });
      changed();
    });
    rp.addEventListener('input', e => {
      if (!e.target.closest('.rule, .co-card, #mirrors')) return;
      changed();
      const r = e.target.closest('.rule'); if (r && e.target.classList.contains('f-name')) $('.r-name', r).textContent = e.target.value || t('ohne_namen');
    });
    rp.addEventListener('change', e => {
      if (!e.target.closest('.rule, .co-card, #mirrors')) return;
      if (e.target.classList.contains('f-modell')) e.target.closest('.form').classList.toggle('no-zins', !e.target.value);
      if (e.target.classList.contains('c-takt')) $('.c-takt-tip', e.target.closest('.co-card')).textContent = taktTip(e.target.value);
      if (e.target.classList.contains('c-rmode')) { const f = $('.c-ab', e.target.closest('.co-card, .gk-row')); f.classList.toggle('hidden', e.target.value !== 'date'); if (e.target.value === 'date') { if (!f.value) f.value = isoToday(); f.focus(); } }
      const gk = e.target.closest('.gk-row');
      if (gk) gk.classList.remove('invalid');
      changed();
    });
    rp.addEventListener('click', e => {
      const po = e.target.closest('.pv-open');
      if (po) { e.preventDefault(); e.stopPropagation(); const box = po.closest('.rule, .co-card, .gk-row');
        // a mirror: its two accounts (all mirrors share one heading)
        const gk = box && box.classList.contains('gk-row') ? [$('.g-a', box), $('.g-b', box)].map(x => x && x.selectedIndex >= 0 ? x.options[x.selectedIndex].textContent.trim() : '').filter(Boolean).join(' ↔ ') : '';
        const title = gk ? t('co_gegenkonten') + ': ' + gk : box ? (($('.r-name', box) || $('h3', box) || {}).textContent || '') : t('nav_auto_buchungen');
        pvDrawer(RPV.list[+po.dataset.pv] || {}, title, po.dataset.pv); return; }
      if (e.target.closest('.rule .del')) { setTimeout(changed); return; }
      if (e.target.closest('#add-mirror')) { $('#mirrors', rp).insertAdjacentHTML('beforeend', mirrorRow({})); $('#mirrors .gk-row:last-child .g-a', rp).focus(); changed(); return; }
      const del = e.target.closest('.gk-del'); if (del) { del.closest('.gk-row').remove(); changed(); return; }
    });
    sr.addEventListener('click', async () => {
      const rows = $$('.gk-row', rp);
      rows.filter(r => !$('.g-a', r).value && !$('.g-b', r).value).forEach(r => r.remove());
      const same = r => !!$('.g-a', r).value && $('.g-a', r).value === $('.g-b', r).value;
      const pairOf = r => [$('.g-a', r).value, $('.g-b', r).value].map(v => v.split('|')[0].trim()).sort().join('|');
      const live = rows.filter(r => r.isConnected);
      const twice = r => !!$('.g-a', r).value && !!$('.g-b', r).value && live.findIndex(x => pairOf(x) === pairOf(r)) < live.indexOf(r);
      const bad = live.filter(r => !$('.g-a', r).value || !$('.g-b', r).value || same(r) || twice(r));
      if (bad.length) { bad.forEach(r => r.classList.add('invalid')); bad[0].scrollIntoView({block: 'center', behavior: 'smooth'}); toast(t(bad.every(same) ? 'gk_gleiches_konto' : bad.every(twice) ? 'gk_doppelt' : 'gk_unvollstaendig'), 5000); return; }
      let rules; try { rules = collectRules(true); } catch (e) { toast(e.message, 6000); return; }
      if (await saveConfig(rules, $('#findings', rp), false, {rules_seen: seen})) {
        seen = seenNow(); saved = rulesJson(); sr.disabled = true; st.textContent = t('regeln_gespeichert'); preview();
        rulesFollowUp(preview);
      }
    });
    preview();
  }
  bindDel(main);

  // Einstellungen
  const ss = $('#save-settings', main); if (ss) ss.addEventListener('click', () => { try { saveConfig(collectSettings(), $('#findings-e')); } catch (e) { toast(e.message, 6000); } });
  const bs = $('#e-bl-sub', main); if (bs) bs.addEventListener('input', () => { const why = subPatternProblem(bs.value.trim()); bs.classList.toggle('invalid', !!why); bs.title = why; });
  for (const [id, done] of [['#setup-done', true], ['#setup-again', false]]) { const b = $(id, main); if (b) b.addEventListener('click', async () => {
    const cfg = JSON.parse(JSON.stringify(S.CFG)); cfg.ui = Object.assign({}, cfg.ui, {setup_done: done});
    if (await saveConfig(cfg, $('#findings-e', main)) !== false) { if (done) go('#overview'); else route(); } }); }
  const cb = $('#check-btn', main); if (cb) cb.addEventListener('click', async () => { toast(t('pruefe')); const r = await api('/api/check', {}); if (!r.available) { showFindings($('#findings-e'), [], r.text, 'error'); return; } S.KONTEN = r.accounts; S.KATS = r.categories || S.KATS; showFindings($('#findings-e'), r.findings, t('geprueft_gegen_den_aktuellen_stand') + r.accounts.length + t('konten_klammer_zu'), 'ok'); });
  const ap = $('#add-pos', main); if (ap) ap.addEventListener('click', e => { e.target.insertAdjacentHTML('beforebegin', posRow('', '')); bindDel(main); });
  const pw = $('#pw-save', main); if (pw) pw.addEventListener('click', async () => { try { const neu = $('#pw-neu').value; if (neu !== $('#pw-neu2').value) return toast(t('passwoerter_ungleich'), 4000);
    await api('/api/password', {old: $('#pw-alt').value, new: neu}); OFFKEY = null; await offKeyEnsure(neu); toast(t('passwort_geaendert')); $('#pw-alt').value = $('#pw-neu').value = $('#pw-neu2').value = ''; } catch (e) { toast(e.message, 4000); } });
  const tms = $('#tm-state', main);
  if (tms) {
    // Time Machine: aktuellen Stand zeigen, ein Knopf schaltet um
    const show = st => { tms.textContent = {backed_up: t('tm_gesichert'), excluded: t('tm_ausgeschlossen')}[st] || t('unbekannt'); const b = $('#tm-toggle', main); b.classList.toggle('hidden', !(st in {backed_up: 1, excluded: 1}) || !S.STATUS.local); b.textContent = st === 'excluded' ? t('wieder_sichern') : t('ausschliessen'); b.dataset.st = st; };
    api('/api/timemachine').then(r => show(r.status)).catch(() => show('unknown'));
    $('#tm-toggle', main).addEventListener('click', async e => { const aus = e.target.dataset.st !== 'excluded'; if (aus && !confirm(t('tm_ausschliessen_frage'))) return; const r = await api('/api/timemachine-exclusion', {exclude: aus}); if (!r.ok) toast(t('fehler_3') + r.text, 5000); show(r.status); });
  }
  for (const [id, url] of [['#diag2', '/api/diagnostics'], ['#diag3', '/api/diagnostics?names=1']]) { const d = $(id, main); if (d) d.addEventListener('click', () => download(url)); }
  const bks = $('#bk-save', main); if (bks) bks.addEventListener('click', async () => {
    const pw = $('#bk-pw', main).value; if (pw.length < 8) return toast(t('sicherungspasswort_mind_8'), 5000); if (pw !== $('#bk-pw2', main).value) return toast(t('passwoerter_ungleich'), 5000);
    try { const r = await api('/api/backup', {password: pw}); saveJson(r, `Kontor-Sicherung-${new Date().toISOString().slice(0, 10)}.kontor-sicherung.json`); $('#bk-pw', main).value = $('#bk-pw2', main).value = ''; toast(t('sicherung_erstellt'), 5000); } catch (e) { toast(e.message, 6000); }
  });
  const swc = $('#sw-clear', main); if (swc) swc.addEventListener('click', async () => { try { await offForget(); toast(t('gespeicherte_daten_geloescht')); } catch (e) { toast(t('nicht_moeglich') + e.message, 4000); } });
  // uninstall: everything of Kontor on this Mac; afterwards a last page that needs nothing from the (then gone) service
  const dk = $('#dk-go', main); if (dk) dk.addEventListener('click', async () => {
    const pw = $('#dk-pw').value;
    if (!pw) return showFindings($('#dk-report'), [], t('passwort_eingeben'), 'error');
    if (!confirm(t('datenschluessel_frage'))) return;
    dk.disabled = true;
    try { const r = await api('/api/key/renew', {password: pw}); $('#dk-pw').value = ''; showFindings($('#dk-report'), (r.left || []).length ? [{severity: 'warning', text: t('datenschluessel_rest', r.left.join(', '))}] : [], tn('datenschluessel_erneuert', r.files), 'ok'); }
    catch (e) { showFindings($('#dk-report'), [], e.message, 'error'); }
    finally { dk.disabled = false; } });
  const un = $('#un-go', main); if (un) un.addEventListener('click', async () => {
    const pw = $('#un-pw').value, prog = $('#un-prog').checked;
    if (!pw) return showFindings($('#un-report'), [], t('passwort_eingeben'), 'error');
    if (!confirm(t('deinstall_frage'))) return;
    try { const r = await api('/api/uninstall', {password: pw, program_folder: prog});
      S.csrf = null; S.bye = true;          // nothing more from the service: it is gone
      const left = r.kept || [], other = r.foreign || [];
      document.body.innerHTML = `<div class="bye"><h1>${esc(t('deinstalliert_h'))}</h1><p>${esc(t(r.key_removed ? 'deinstalliert_text' : 'deinstalliert_ohne_schluessel'))}</p>${r.receipts ? `<p>${esc(t('deinstall_belege_bleiben', r.receipts))}</p>` : ''}${left.length ? `<p>${esc(t('deinstall_geblieben', left.join(', ')))}</p>` : ''}${other.length ? `<p>${esc(t('deinstall_fremd', S.STATUS.storage.folder, other.join(', ')))}</p>` : ''}<p>${esc(t('deinstall_freigaben'))}</p><pre>tccutil reset AppleEvents org.python.python</pre><p class="muted">${esc(t('fenster_schliessen'))}</p></div>`;
    } catch (e) { showFindings($('#un-report'), [], e.message, 'error'); } });
  const rs = $('#rs-go', main); if (rs) rs.addEventListener('click', async () => {
    const pw = $('#rs-pw').value, withPw = $('#rs-pw-reset').checked;
    if (!pw) return showFindings($('#rs-report'), [], t('passwort_eingeben'), 'error');
    if (!confirm(t('wirklich_alle_kontor_daten_auf') + (withPw ? t('und_das_passwort_zuruecksetzen') : '') + t('belegdateien_und_protokoll_bleiben_vor'))) return;
    try { await api('/api/reset', {password: pw, with_password: withPw}); toast(t('zurueckgesetzt_neustart_der_oberflaech'), 4000); waitAndReload(false); }
    catch (e) { showFindings($('#rs-report'), [], e.message, 'error'); } });

  // Pakete
  const pe = $('#pk-export', main); if (pe) pe.addEventListener('click', () => download(`/api/package/export?name=${encodeURIComponent($('#pk-name').value || t('paket_name'))}`));
  const pp = $('#pk-pick', main); if (pp) pp.addEventListener('click', () => { const inp = $('#file-input'); inp.value = ''; inp.setAttribute('accept', '.json'); inp.removeAttribute('capture'); inp.onchange = () => { if (inp.files[0]) readPkgFile(inp.files[0]); }; inp.click(); });
  const pd = $('#pk-drop', main); if (pd) { pd.addEventListener('dragover', e => { e.preventDefault(); pd.classList.add('over'); }); pd.addEventListener('dragleave', () => pd.classList.remove('over')); pd.addEventListener('drop', e => { e.preventDefault(); pd.classList.remove('over'); if (e.dataTransfer.files[0]) readPkgFile(e.dataTransfer.files[0]); }); if (PKG) pkgPreview(); }

  // Updates
  const uc = $('#up-check', main); if (uc) uc.addEventListener('click', async () => { toast(t('pruefe')); await api('/api/update/check', {}); S.STATUS = await api('/api/status'); softRoute(); });
  const ui = $('#up-install', main); if (ui) ui.addEventListener('click', () => upInstall(ui));
  const lr = $('#log-refresh', main); if (lr) lr.addEventListener('click', route);
  $$('#log-min button', main).forEach(bt => bt.addEventListener('click', () => { S.logMin = +bt.dataset.min; route(); }));
  const ls = $('#log-show', main); if (ls) ls.addEventListener('click', async () => { try { await api('/api/file/reveal', {path: ((S.STATUS.storage || {}).folder || '') + '/kontor.log'}); } catch (e) { toast(e.message, 5000); } });
}
function bindDel(main) {
  $$('.item .del', main).forEach(b => { b.onclick = e => e.target.closest('.item').remove(); });
  $$('.del-row', main).forEach(b => { b.onclick = e => e.target.closest('.row').remove(); });
}
async function rebuildReport(fresh) {
  // fresh: zuerst MoneyMoney neu lesen (wartet); sonst aus dem letzten Stand neu rechnen -- läuft im Hintergrund,
  // der Status unten links zeigt den Fortschritt, danach werden die Daten automatisch neu geladen
  toast(fresh ? t('moneymoney_wird_gelesen_auswertung_wir') : t('auswertung_wird_im_hintergrund_aktuali'), fresh ? 60000 : 4000);
  try {
    let r = fresh ? await api('/api/report', {}) : await api('/api/report/rebuild', {});
    if (!r.ok && fresh) r = await api('/api/report/rebuild', {});
    if (!r.ok) { toast(r.text || t('moneymoney_nicht_verfuegbar_bericht_sp'), 7000); await loadAll(); route(); return false; }
    if (r.ok === 'requested') { await pollStatus(); return true; }
  } catch (e) { toast(e.message, 7000); return false; }
  await loadAll(); route(); toast(t('auswertung_aktualisiert')); return true;
}
async function plan(body) {
  try { await api('/api/plan', Object.assign({area: S.area}, body)); S.DATA = await api('/api/dataset'); route(); toast(t('plan_gespeichert')); }
  catch (e) { toast(t('fehler_3') + e.message, 4000); }
}
// a changed rule of the planning: where your own values or rules lie beneath it, Kontor lists them first -- keep or replace
async function planRule(body) {
  try {
    const r = await api('/api/plan', Object.assign({area: S.area, conflicts: 'ask'}, body));
    if (r && r.conflicts) {
      const how = await choose(planConflictHtml(r.conflicts), [['keep', t('pk_behalten')], ['replace', t('pk_ersetzen'), 'danger']]);
      if (!how) return;
      await api('/api/plan', Object.assign({area: S.area}, body, {conflicts: how, confirmed: r.conflicts}));          // exactly what the dialog listed (else refused)
    }
    S.DATA = await api('/api/dataset'); route(); toast(t('plan_gespeichert'));
  } catch (e) { toast(t('fehler_3') + e.message, 4000); }
}
async function syncNow(voll, page) {
  // page: asked for by you (the Sync button): the open page is drawn again when something changed
  // Wie der automatische Abgleich, nur sofort: MoneyMoney lesen, Regeln anwenden (Testmodus laut Einstellung), Auswertung bauen.
  // voll: read all transactions instead of only the last 30 days
  if (SYNC.busy) return;
  SYNC.busy = true; statusMini();
  try {
    try { await api('/api/run', voll ? {force: false, full_read: true} : {force: false}); }
    catch (e) { if (e.status !== 409) throw e; }          // a check is running already: wait for it
    let tries = 0;
    do { await new Promise(r => setTimeout(r, tries ? 1000 : 600)); S.STATUS = await api('/api/status'); statusMini(); } while (S.STATUS.service.running && tries++ < 300);
    const r = S.STATUS.last_result || {};
    const n = (r.proposals || []).length;
    const msg = r.status === 'unchanged' ? t('synchronisiert_keine_aenderung_in_mone')
      : r.status === 'ok' ? t('synchronisiert') + (r.booked_count ? ' – ' + r.booked_count + ' ' + t('gebucht') : '') + (r.dry_run && n ? ' – ' + tn('0_buchungsvorschlaege', n) : '') + ((r.warnings || []).length ? ' – ' + tn('n_hinweise_unter_buchungen', r.warnings.length) : '')
      : (r.text || r.error || t('synchronisiert'));
    toast(msg, r.status === 'unavailable' || r.status === 'error' ? 7000 : 4500);
    // the open page shows the new state: at once (accounts, categories and settings may have changed), and again once the
    // report is rebuilt (pollStatus) -- unless you are in the middle of changing something on it
    const changed = !!page && r.status === 'ok' && !DIRTY.on;
    if (changed) {
      const [cfg, konten, kats] = await Promise.all([api('/api/config'), api('/api/accounts'), api('/api/categories')]);
      S.CFG = cfg; S.KONTEN = konten.accounts || []; S.KATS = kats.categories || [];
      if (!$('#drawer').classList.contains('open')) route();
    } else if (S.tab === 'bookings' || (S.tab === 'settings' && S.sub === 'moneymoney')) softRoute();
    pollStatus(changed).catch(() => {});                             // the figures follow: loaded once the report is rebuilt
  } catch (e) { toast(t('synchronisieren_fehlgeschlagen') + e.message, 6000); }
  finally { SYNC.busy = false; statusMini(); }
}
async function startRun(dry, freigabe, anchor) {
  try { await api('/api/run', {dry_run: dry, force: true, ...(freigabe ? {approval: freigabe} : {})}); toast(dry ? t('abgleich_gestartet_test') : t('abgleich_mit_buchung_gestartet')); } catch (e) { toast(e.message, 4000); return; }
  let tries = 0;
  const poll = async () => {
    try { S.STATUS = await api('/api/status'); } catch (e) { return setTimeout(poll, 1500); }
    statusMini();
    const rl = $('#run-live', $('#main'));
    if (S.STATUS.service.running && tries++ < 300) { if (rl) { rl.disabled = true; $('span', rl).textContent = runStep(S.STATUS); } return setTimeout(poll, 1000); }
    const r = S.STATUS.last_result || {};
    toast(r.booked_count ? t('x_gebucht', r.booked_count) : ((r.warnings || [])[0] || r.text || t('abgleich_beendet')), 5000);
    await (anchor ? routeKeeping(anchor) : route());             // the bookings at once
    pollStatus().catch(() => {});                                  // the figures follow
  };
  setTimeout(poll, 600);
}

// ---------------------------------------------------------------- Assistent
// A language model on this Mac (assistant.py) beside every page: its panel stands at the right like the side panel and the page
// makes room for it (a narrow window: it lies over the page); "#assistant" shows the same conversation as a page. What it may
// do is set under Einstellungen -> Assistent, at the Mac only; an entry it proposes is made only by a click on its card.
const AS = {st: null, open: false, msgs: [], refs: [], files: [], conv: '', job: null, n: 0, busy: false, prev: '#overview', setT: null, effort: '', list: false, chats: null, save: true, cw: 0, hover: null, sel: null, ptr: ''};
const AS_HIDDEN = ['settings', 'log', 'setup', 'assistant'];          // pages the assistant never reads
// the thinking effort: chosen only at the top of the panel and remembered on this device (like the theme); before the first choice
// balanced
const AS_EFFORTS = ['fast', 'balanced', 'thorough'];
const asEffort = () => {
  if (!AS.effort) { try { const e = LS.get('kontor.effort'); if (AS_EFFORTS.includes(e)) AS.effort = e; } catch (x) { /* kept in memory only */ } }
  return AS.effort || 'balanced';
};
const asOn = () => !!(AS.st && AS.st.settings && AS.st.settings.enabled && !OFFLINE.mode);
// newer versions of llama.cpp or of the models in use, found by the look (only told at the Mac): what the menu marks at Settings
function asNewer() { return asOn() ? ((AS.st.newer || {}).marked || 0) : 0; }
const asN = v => Math.round(v).toLocaleString(LOCALE);
const asRAM = b => (b / 2 ** 30).toLocaleString(LOCALE, {maximumFractionDigits: b >= 10 * 2 ** 30 ? 0 : 1}) + ' GB';          // memory as the Mac names it (64 GB)
const asGB = b => b < 5e7 ? Math.round(b / 1e6).toLocaleString(LOCALE) + ' MB' : (b / 1e9).toLocaleString(LOCALE, {maximumFractionDigits: b >= 1e10 ? 0 : 1}) + ' GB';
async function asLoad() { try { AS.st = await api('/api/assistant/status'); } catch (e) { AS.st = null; } asChrome(); statusMini(); asWatch(); if (AS.open || S.tab === 'assistant') asWarm(); return AS.st; }
function asChrome() {
  // the button in the title bar and the menu entry: there while the assistant is switched on
  const on = asOn(), b = $('#assist-btn');
  b.classList.toggle('hidden', !on); $('#nav-assist').classList.toggle('hidden', !on); b.title = t('ki_tip') + keyHint('assistant');
  if (!on && AS.open) AS.open = false;
  asLayout();
}
function asLayout() {
  pageKeep();                     // where the page stands, before the panel docks or goes
  const page = S.tab === 'assistant' && asOn(), open = (AS.open && asOn()) || page, as = $('#assist');
  document.body.classList.toggle('as-open', open && !page); document.body.classList.toggle('as-page', page);
  as.classList.toggle('open', open); $('#assist-btn').classList.toggle('on', open && !page); $('#assist-btn').classList.toggle('hidden', !asOn() || page);
  if (page) { const m = $('main').getBoundingClientRect(), top = $('#main').getBoundingClientRect().top + pageY(); as.style.left = m.left + 'px'; as.style.top = Math.max(0, top) + 'px'; }
  else { as.style.left = as.style.top = ''; }
  pageHandover();
  if (open) { if (!$('#as-body')) asDraw(); else { asHead(); asMicSync(); } asWarm(); }
  else asMicStop(false);          // the question field is gone (another page, switched off): a recording ends with it, unsent
}
// the speech model ready at once (Einstellungen -> KI-Assistent -> Diktieren): started as soon as the question field is on screen,
// so that a dictation starts without waiting -- asked again at most every minute (it then stays as long as the model that answers)
let AS_WARM = 0;
function asWarm() {
  const a = AS.st || {};
  if (!a.dictation || !a.speech_early || !(a.settings || {}).enabled || !asOn() || Date.now() - AS_WARM < 60000) return;
  AS_WARM = Date.now(); api('/api/assistant/listen', {warm: true}).catch(() => {});
}
function asShow(open) {
  if (!open) asMicStop(false);
  AS.open = !!open && asOn();
  try { LS.set('kontor.assist', AS.open ? '1' : ''); } catch (e) {}
  asLayout();
  if (AS.open) { asLoad(); const ta = $('#as-in'); if (ta && matchMedia('(hover: hover)').matches) ta.focus(); }
}
// what the model answers, as text with a little Markdown (bold, lists, small tables, code) -- built from escaped text only
const LI = /^(\s*)([-*•+]|\d+[.)])\s+(.*)$/;
// the addresses Kontor fetched from the internet in this conversation: only these become links in an answer (an address the
// model makes up -- perhaps told to by a web page, perhaps carrying your figures -- stays plain text)
const asLinks = () => new Set(AS.msgs.flatMap(m => (m.parts || []).filter(p => p.k === 'web').flatMap(p => asWebItems(p).filter(it => it.state === 'done').flatMap(it => it.links || []))));
const asUnesc = s => s.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
function asMd(src, links) {
  const ok = links instanceof Set ? links : new Set();
  const link = s => s.replace(/\[([^\]]{1,200})\]\((https:\/\/[^\s)]{1,500})\)|(https:\/\/[^\s<>()]{1,500}[^\s<>().,;:!?])/g, (m, txt, u1, u2) => {
    const u = u1 || u2;
    if (!ok.has(asUnesc(u))) return txt ? `${txt} (${u})` : m;
    let host = ''; try { host = new URL(asUnesc(u)).hostname; } catch (e) { return txt ? `${txt} (${u})` : m; }
    // the host always beside the model's words (they alone could pretend to be something else) -- also where there is no tooltip
    return `<a href="${u}" target="_blank" rel="noopener noreferrer" title="${u}">${txt || u}</a>${txt ? `<span class="as-lh"> (${esc(host)})</span>` : ''}`;
  });
  const inline = s => link(esc(s)).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/(^|[\s(])\*([^*\s][^*]*)\*(?=[\s).,;:!?]|$)/g, '$1<i>$2</i>');
  const cells = l => l.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
  const lines = String(src || '').replace(/\r/g, '').split('\n'); let h = '', i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (/^\s*```/.test(l)) { const buf = []; i++; while (i < lines.length && !/^\s*```/.test(lines[i])) buf.push(lines[i++]); i++;
      h += `<div class="as-code"><button type="button" class="ghost small as-copy">${t('ki_kopieren')}</button><pre>${esc(buf.join('\n'))}</pre></div>`; continue; }
    if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < lines.length && lines[i + 1].includes('-') && /^[\s:|-]+$/.test(lines[i + 1])) {
      const head = cells(l), rows = []; i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]));
      const num = c => /\d/.test(c) && /^[+\-−–]?\s?[€$£]?\s?[\d.,\s]+\s?(€|%|EUR|T€|k)?$/.test(c);          // a figure, with or without its currency
      const numCol = head.map((_, k) => rows.length > 0 && rows.every(r => !r[k] || num(r[k])) && rows.some(r => r[k]));          // a column of figures: its heading at the right too
      h += `<div class="as-tw"><div class="as-tw-in"><table><thead><tr>${head.map((c, k) => `<th${numCol[k] ? ' class="num"' : ''}>${inline(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td${num(c) ? ' class="num"' : ''}>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div>`;
      continue;
    }
    const li = LI.exec(l);
    if (li) {          // a list: its items also with blank lines between them (numbered on from its first number), a text that goes on
      // below an item (indented) and a list inside an item stay with it
      const ord = /\d/.test(li[2]), base = li[1].length, items = [];
      let loose = false;
      while (i < lines.length) {
        const m = LI.exec(lines[i]), ind = m ? m[1].length : 0;
        if (m && ind <= base + 1 && /\d/.test(m[2]) === ord) { items.push({text: m[3], more: [], sub: []}); i++; continue; }
        const cur = items[items.length - 1];
        if (m && ind >= base + 2) { cur.sub.push({ord: /\d/.test(m[2]), text: m[3]}); i++; continue; }
        if (lines[i].trim() && /^\s/.test(lines[i]) && lines[i].search(/\S/) >= base + 2) { cur.more.push(lines[i].trim()); i++; continue; }
        if (!lines[i].trim()) {
          let j = i; while (j < lines.length && !lines[j].trim()) j++;
          const n = j < lines.length ? LI.exec(lines[j]) : null;
          if (n && (n[1].length >= base + 2 || (n[1].length <= base + 1 && /\d/.test(n[2]) === ord)) || (j < lines.length && lines[j].search(/\S/) >= base + 2)) { i = j; loose = true; continue; }
        }
        break;
      }
      const start = ord ? parseInt(li[2], 10) : 1, sub = it => it.sub.length ? `<${it.sub[0].ord ? 'ol' : 'ul'}>${it.sub.map(x => `<li>${inline(x.text)}</li>`).join('')}</${it.sub[0].ord ? 'ol' : 'ul'}>` : '';
      h += `<${ord ? 'ol' : 'ul'}${ord && start !== 1 ? ` start="${start}"` : ''}${loose ? ' class="loose"' : ''}>${items.map(it => `<li>${inline(it.text)}${it.more.map(x => '<br>' + inline(x)).join('')}${sub(it)}</li>`).join('')}</${ord ? 'ol' : 'ul'}>`;
      continue;
    }
    if (/^#{1,4}\s+/.test(l)) { h += `<p><b>${inline(l.replace(/^#{1,4}\s+/, ''))}</b></p>`; i++; continue; }
    if (!l.trim()) { i++; continue; }
    const par = [];
    while (i < lines.length && lines[i].trim() && !/^\s*(```|#{1,4}\s|([-*•]|\d+[.)])\s)/.test(lines[i]) && !(/^\s*\|.*\|\s*$/.test(lines[i]) && par.length)) par.push(lines[i++]);
    if (!par.length) par.push(lines[i++]);
    h += `<p>${par.map(inline).join('<br>')}</p>`;
  }
  return h;
}
function asEntry(p, ask) {
  // a change the assistant proposes: what, where, old and new -- carried out only with the click on the card of all changes of the
  // answer (ask: that card waits now; each change can be left out by its tick), and taken back here
  const kind = asKind(p.kind);
  const lab = s => /^\d{4}-\d{2}$/.test(s) ? MLL(s) : s, n = v => p.kind === 'params' ? (+v).toLocaleString(LOCALE, {maximumFractionDigits: 2}) : fmt.format(v);          // assumptions: plain numbers (2,5), not amounts
  const rows = (p.rows || []).map(r => `<tr><td>${esc(lab(r.label))}</td><td class="num muted">${r.old != null ? n(r.old) : r.shown != null ? n(r.shown) : '–'}</td><td class="num"><b>${r.new == null ? t('ki_e_leer') : n(r.new)}</b></td></tr>`).join('');
  const ev = p.event ? `<div class="muted small">${t(`ki_e_kind_${p.event.kind}`)} · ${t(`ki_e_rec_${p.event.recurrence}`)}${p.event.until ? ' ' + t('ki_e_bis', MLL(p.event.until)) : ''}</div>` : '';
  const why = p.reason ? `<div class="as-e-why">${esc(p.reason)}</div>` : '';
  const fin = p.final && p.state === 'queued' ? `<div class="as-e-fin">${t(p.kind === 'book' ? 'ki_e_endgueltig_buchen' : 'ki_e_endgueltig')}</div>` : '';
  const st = p.state === 'queued' ? (ask ? '' : `<div class="as-e-st">${t('ki_e_wartet')}</div>`)
    : p.state === 'done' ? `<div class="as-e-st ok">${ICON.check}<span>${t('ki_e_done')}</span>${p.fixed ? '' : `<button class="ghost small as-undo" data-id="${esc(p.id)}">${t('ki_e_zurueck')}</button>`}</div>${p.text ? `<div class="as-e-why">${esc(p.text)}</div>` : ''}`
    : `<div class="as-e-st">${p.state === 'failed' ? esc(t('ki_e_failed', p.text || '')) : t(p.state === 'undone' ? 'ki_e_undone' : 'ki_e_declined')}</div>${p.state === 'undone' && p.text ? `<div class="as-e-why">${esc(p.text)}</div>` : ''}`;
  if (p.kind === 'rule') {          // a booking rule: each setting before and after, and what it would book (each booking waiting for approval)
    const trs = (p.rows || []).map(r => `<tr><td>${esc(r.label)}</td><td class="muted">${esc(r.old_text || '–')}</td><td><b>${esc(r.new_text || '–')}</b></td></tr>`).join('');
    return asCard(p, ask, kind, `${why}<table class="as-e-t"><thead><tr><th></th><th>${t('ki_e_bisher')}</th><th>${t('ki_e_neu_wert')}</th></tr></thead><tbody>${trs}</tbody></table>
      <div class="muted small">${[p.count ? tn('ki_e_rule_vorschau', p.count, p.count) : '', p.dropped ? tn('ki_e_rule_weg', p.dropped, p.dropped) : '', t('ki_e_rule_freigabe')].filter(Boolean).join(' · ')}</div>`, fin, st);
  }
  if (p.kind === 'planrule') {          // a rule of the planning: before and after, and your own values and rules beneath it -- replaced or kept
    const trs = rs => rs.map(r => `<tr><td>${esc(String(r.label || '').replace(/ · (\d{4}-\d{2})$/, (_, m) => ' · ' + ML(m)))}</td><td class="muted">${esc(r.old_text || '–')}</td><td><b>${esc(r.new_text || '–')}</b></td></tr>`).join('');
    const own = p.replace || p.keep, more = (p.count || 0) - (own || []).length;
    return asCard(p, ask, kind, `${why}<table class="as-e-t"><thead><tr><th></th><th>${t('ki_e_bisher')}</th><th>${t('ki_e_neu_wert')}</th></tr></thead><tbody>${trs(p.rows || [])}</tbody></table>`
      + (own ? `<div class="${p.replace ? 'as-e-fin' : 'muted small'}">${tn(p.replace ? 'ki_e_pr_ersetzt' : 'ki_e_pr_bleibt', p.count || own.length)}</div><table class="as-e-t as-e-tc"><tbody>${trs(own)}${more > 0 ? `<tr><td colspan="3" class="muted">${t('ki_e_weitere', more)}</td></tr>` : ''}</tbody></table>` : ''), fin, st);
  }
  if (p.kind === 'book' || p.kind === 'hold') {          // waiting auto bookings to book (final in MoneyMoney) or to hold back: how many, how much, each of them
    // every booking stands on the card: the first ones at once, a long list unfolds (all can be read before the click); a card
    // saved before 3.17 has only its first rows
    const all = p.rows || [], cut = all.length > 8 ? 6 : all.length, more = (p.count || 0) - all.length;
    const who = r => [r.account, r.counterparty].filter(Boolean).join(' · ');          // which account, to whom: each row on its own (a card saved before 3.17: the text only)
    const line = r => `<tr><td class="nowrap">${esc(FD(r.label))}</td><td class="as-e-zw" title="${esc([who(r), r.text].filter(Boolean).join('\n'))}">${who(r) ? `<div>${esc(who(r))}</div>` : ''}<div class="muted">${esc(r.text || '')}</div></td><td class="num">${r.new == null ? '' : fmt.format(r.new)}</td></tr>`;
    const rest = all.length > cut ? `<details class="as-e-more" data-id="${esc(p.id)}"${p.more ? ' open' : ''}><summary class="muted small" style="cursor:pointer">${t('ki_e_weitere', all.length - cut)}</summary><table class="as-e-t as-e-tc"><tbody>${all.slice(cut).map(line).join('')}</tbody></table></details>` : '';
    return asCard(p, ask, kind, `<div class="muted small">${tn('ki_e_buchungen', p.count || 0, p.count || 0)}${p.sum != null ? ' · ' + fmt.format(p.sum) : ''}</div>${why}
      <table class="as-e-t as-e-tc"><tbody>${all.slice(0, cut).map(line).join('')}${more > 0 ? `<tr><td colspan="3" class="muted">${t('ki_e_weitere', more)}</td></tr>` : ''}</tbody></table>${rest}`, fin, st);
  }
  if (p.kind === 'receipt') {          // a receipt given in the panel, to be filed: with which transaction, where (the folder under the title), what differs
    const r = (p.rows || [])[0];
    const tx = r ? `<table class="as-e-t as-e-tc"><tbody><tr><td class="nowrap">${esc(FD(r.label))}</td><td class="muted as-e-zw" title="${esc(r.text || '')}">${esc(r.text || '')}</td><td class="num">${r.new == null ? '' : fmt.format(r.new)}</td></tr></tbody></table>` : `<div class="muted small">${t('ki_e_ohne_umsatz')}</div>`;
    const diffs = (p.diffs || []).map(d => `<div class="as-e-fin">${esc(d.what === 'amount' ? t('ki_e_abw_betrag', fmt.format(d.receipt), fmt.format(d.transaction)) : d.what === 'date' ? tn('ki_e_abw_tage', d.days, d.days) : t('ki_e_ungeprueft'))}</div>`).join('');
    return asCard(p, ask, kind, `${why}${tx}${diffs}${p.note ? `<div class="as-e-why">${esc(p.note)}</div>` : ''}${p.create && p.state === 'queued' ? `<div class="as-e-why">${t('ki_e_ordner_neu')}</div>` : ''}`, fin, st);
  }
  if (p.kind === 'category') {          // a category for transactions without one: which, how many, the first of them
    const more = (p.count || 0) - (p.rows || []).length;
    const trs = (p.rows || []).map(r => `<tr><td class="nowrap">${esc(FD(r.label))}</td><td class="muted as-e-zw" title="${esc(r.text || '')}">${esc(r.text || '')}</td><td class="num">${r.new == null ? '' : fmt.format(r.new)}</td></tr>`).join('');
    return asCard(p, ask, kind, `<div class="as-e-cat">→ <b>${esc(String(p.category || '').replace(/ \/ /g, ' › '))}</b></div><div class="muted small">${tn('ki_e_umsaetze', p.count || 0, p.count || 0)}${p.sum != null ? ' · ' + fmt.format(p.sum) : ''}</div>${why}
      <table class="as-e-t as-e-tc"><tbody>${trs}${more > 0 ? `<tr><td colspan="3" class="muted">${t('ki_e_weitere', more)}</td></tr>` : ''}</tbody></table>`, fin, st);
  }
  return asCard(p, ask, kind, `${ev}${why}
    <table class="as-e-t"><thead><tr><th>${t(p.kind === 'params' ? 'ki_e_annahme' : 'ki_e_monat')}</th><th class="num">${t('ki_e_bisher')}</th><th class="num">${t('ki_e_neu_wert')}</th></tr></thead><tbody>${rows}</tbody></table>`, fin, st);
}
const asKind = k => ({balances: t('ki_e_balances'), plan: t('ki_e_plan'), planrule: t('ki_e_planrule'), event: t('ki_e_event'), params: t('ki_e_params'), category: t('ki_e_category'), book: t('ki_e_book'), hold: t('ki_e_hold'), rule: t('ki_e_rule'), receipt: t('ki_e_receipt'), web: t('ki_a_web')}[k] || '');
function asCard(p, ask, kind, body, fin, st) {
  // the frame of a proposed change: the tick while the card of changes waits, its kind, title and where, what it changes, its state
  const tick = p.state === 'queued' && ask ? `<label class="as-e-pick" title="${esc(t('ki_e_auswahl_tip'))}"><input type="checkbox" class="as-pick" data-id="${esc(p.id)}" ${p.off ? '' : 'checked'}></label>` : '';
  return `<div class="as-entry ${esc(p.state)}${p.state === 'queued' && ask ? ' ask' : ''}${p.off ? ' off' : ''}" data-ex="assistant.change">${tick}<div class="as-e-k">${kind}</div><div class="as-e-h">${esc(p.title || '')}</div>${p.sub ? `<div class="muted small">${esc(p.sub)}</div>` : ''}${body}${fin}${st}</div>`;
}
function asBatch(p, m) {
  // the card of all changes of an answer: one click carries out the ticked ones (or none); afterwards what came of them
  const mine = (m.parts || []).filter(x => x.k === 'entry' && (p.ids || []).includes(x.id)), on = mine.filter(x => !x.off).length;
  if (p.state === 'ask') return `<div class="as-batch" data-ex="assistant.change"><span class="muted small">${tn('ki_b_frage', mine.length, mine.length)}</span>
    <div class="as-e-btn"><button class="small as-b-yes" data-id="${esc(p.id)}" ${on ? '' : 'disabled'}>${on === mine.length ? tn('ki_b_alle', on, on) : tn('ki_b_ausgewaehlte', on, on)}</button><button class="small secondary as-b-no" data-id="${esc(p.id)}">${t('ki_b_nichts')}</button></div></div>`;
  if (p.state === 'declined') return `<div class="as-batch done" data-ex="assistant.change"><span class="muted small">${t('ki_b_nichts_geaendert')}</span></div>`;
  const bits = [p.done ? tn('ki_b_done', p.done, p.done) : '', p.left ? tn('ki_b_left', p.left, p.left) : '', p.failed ? tn('ki_b_failed', p.failed, p.failed) : ''].filter(Boolean);
  return `<div class="as-batch done" data-ex="assistant.change"><span class="muted small">${esc(bits.join(' · '))}</span></div>`;
}
// The requests on the card of a research: each {id, what: search | read, source, label, tier, query, addresses, sent, state}
// (reads: a line of cards saved by 3.16.76-3.16.88, results read with the search's approval). A card saved before the lookups
// of an answer were asked together named one request: shown as its only one.
const asWebItems = p => Array.isArray(p.items) ? p.items : (p.items = [{id: p.id, what: p.what || 'search', label: p.label, tier: p.tier, query: p.query, addresses: p.addresses || [],
  state: p.state === 'ask' ? undefined : p.state === 'expired' ? 'declined' : p.state, count: p.count, text: p.text, links: p.links, old: true}]);          // (old: what was sent is not known any more)
const asWebFetched = p => asWebItems(p).some(it => it.state === 'done');
function asWebState(p, ev) {
  // the card after the click or at its end -- the same steps as _web_state() in assistant.py: what was not ticked, and what was
  // not fetched by the time it ended, was not fetched
  for (const it of p.items || []) {
    if (ev.state === 'run' && Array.isArray(ev.chosen) && !ev.chosen.includes(it.id)) it.state = 'declined';
    else if (['declined', 'expired', 'stopped', 'done'].includes(ev.state) && (!it.state || it.state === 'run') && (it.what !== 'reads' || ev.state !== 'done')) it.state = 'declined';
  }
  p.state = ev.state === 'stopped' ? 'done' : ev.state;
}
function asWebCard(p, i, j) {
  // the lookups of a research, asked for together: each request with its words, source and tier -- its address and what is sent
  // with it on demand (the row opens); Kontor fetches the ticked ones with one click (chat: that click allows the conversation),
  // afterwards each row says what came of it. free: trusted, in a conversation that allows the internet -- no buttons, just shown
  const items = asWebItems(p), ask = p.state === 'ask', none = p.state === 'declined' || p.state === 'expired', reqs = items.filter(it => it.what !== 'reads'), on = reqs.filter(it => !it.off).length;
  const state = it => it.state === 'done' ? `<span class="as-w-st ok">${ICON.check}${it.what === 'read' ? t('ki_w_done_read') : tn('ki_w_treffer', it.count || 0, it.count || 0)}</span>`
    : it.state === 'run' ? `<span class="as-w-st"><span class="spin xs"></span></span>`
    : it.state === 'failed' ? `<span class="as-w-st">${esc(t('ki_w_fehler', it.text || ''))}</span>`
    : it.state === 'unneeded' ? `<span class="as-w-st">${t('ki_w_unneeded')}</span>`
    : it.state === 'declined' ? `<span class="as-w-st">${t('ki_w_declined')}</span>` : '';
  const tick = it => ask && items.length > 1 ? `<label class="as-w-pick" title="${esc(t('ki_w_auswahl_tip'))}"><input type="checkbox" class="as-w-tick" data-id="${esc(p.id)}" data-item="${esc(it.id)}" aria-label="${esc(it.what === 'reads' ? tn('ki_w_reads', it.count || 0, it.count || 0) : it.query || '')}" ${it.off || (it.what === 'reads' && !on) ? '' : 'checked'} ${it.what === 'reads' && !on ? 'disabled' : ''}></label>` : '';          // (one request alone: the buttons say it all)
  const row = it => {
    const off = it.off || (it.what === 'reads' && ask && !on);
    if (it.what === 'reads') return `<div class="as-w-row reads ${esc(it.state || '')}${off ? ' off' : ''}">${tick(it)}<div class="as-w-plain"><span class="as-w-q">${tn('ki_w_reads', it.count || 0, it.count || 0)}</span>${ask || none ? '' : `<span class="as-w-st${it.state ? '' : ' ok'}">${it.state ? t('ki_w_reads_nein') : ICON.check + t('ki_w_reads_ja')}</span>`}</div></div>`;
    const adr = it.addresses || [], what = it.what === 'read' ? String(it.query || '').replace(/^https:\/\//, '') : it.query || '';
    const meta = (it.site ? [it.site, t('ki_w_ueber', it.label || '')] : [it.label || '', t('ki_w_stufe', it.tier || 1), it.fallback ? t('ki_w_falls') : '']).filter(Boolean).join(' · ');          // a page on some website: the website first
    return `<div class="as-w-row ${esc(it.state || '')}${off ? ' off' : ''}">${tick(it)}<details class="as-w-d" data-m="${i}" data-p="${j}" data-i="${esc(it.id || '')}"${it.open ? ' open' : ''}>
      <summary><span class="as-w-q${it.what === 'read' ? ' one' : ''}">${esc(what)}</span><span class="as-w-sub"><span class="as-w-src">${esc(meta)}</span>${ask || none ? '' : state(it)}</span></summary>
      <dl class="as-w-more"><dt>${tn('ki_w_adresse', adr.length)}</dt><dd>${adr.map(u => `<code>${esc(u)}</code>`).join('')}</dd>
      ${it.old ? '' : `<dt>${t('ki_w_gesendet')}</dt><dd>${it.sent ? `<code>${esc(it.sent)}</code><span class="muted">${it.key ? t('ki_w_schluessel') : ''}</span>` : `<span class="muted">${tn('ki_w_nur_adresse', adr.length)}</span>`}</dd>`}</dl></details></div>`;
  };
  const yes = p.chat ? t('ki_w_chat_ja') : on === reqs.length ? tn('ki_w_alle', on, on) : tn('ki_w_auswahl', on, on);
  const end = ask ? `<div class="as-e-btn"><button class="small as-w-yes" data-id="${esc(p.id)}" ${on ? '' : 'disabled'}${p.chat ? ` title="${esc(t('ki_w_chat_tip'))}"` : ''}>${yes}</button><button class="small secondary as-w-no" data-id="${esc(p.id)}">${t(p.chat ? 'ki_w_chat_nein' : reqs.length > 1 ? 'ki_w_nichts' : 'ki_w_nein')}</button></div>`
    : none ? `<div class="as-e-st">${t(p.state === 'expired' ? 'ki_w_expired' : 'ki_w_declined')}</div>` : '';
  const free = !!p.free, kind = (reqs.length && reqs.every(it => it.what === 'read') ? tn('ki_w_lesen', reqs.length) : t('ki_w_kind'))
    + (free ? ' · ' + t('ki_w_frei') : p.auto ? ' · ' + t('ki_w_auto') : '');          // (auto: read with the approval of a search, 3.16.76-3.16.88)
  return `<div class="as-entry as-web ${esc(asWebFetched(p) && p.state !== 'run' ? 'done' : p.state || '')}${ask ? ' ask' : ''}${free ? ' free' : ''}" data-ex="assistant.web"><div class="as-e-k" title="${esc(t(free ? 'ki_w_frei_tip' : 'ki_w_tip'))}">${kind}</div>
    ${p.reason ? `<div class="as-e-why">${esc(p.reason)}</div>` : ''}<div class="as-w-list">${items.map(row).join('')}</div>${end}</div>`;
}
// A chart the assistant asked for: the figures are Kontor's own (the model chose only what to show), drawn here as the charts on
// the pages are -- the values on hover, a click shows the figure on its page (on a touch screen: tap to see it, tap again to go)
const AS_TONE = {net_worth: '--c-nw', assets: '--c-liq', liabilities: '--c-verb', income: '--c-ein', expenses: '--c-aus', surplus: '--c-ford', investing: '--c-anl',
  financing: '--c-bet', interest: '--c-immo', value_changes: '--c-fest', unclear: '--c-neutral', bank_balance_change: '--c-liq', net_worth_change: '--c-nw'};
const AS_PAL = ['--c-ford', '--c-anl', '--c-bet', '--c-immo', '--c-fest', '--c-verb', '--c-liq', '--c-nw'];
function asChColors(c) {
  // the colours of the pages where a series has one (a position, income, expenses ...), else the next one not in use
  const used = new Set(), pick = want => { let v = want; if (!v || used.has(v)) v = 'var(' + (AS_PAL.find(p => !used.has('var(' + p + ')')) || AS_PAL[used.size % AS_PAL.length]) + ')'; used.add(v); return v; };
  const of = (role, tone) => role && ROLE[role] ? ROLE[role][1] : AS_TONE[tone] ? 'var(' + AS_TONE[tone] + ')' : '';
  if (c.kind === 'hbar') { const s = c.series[0] || {}; return (c.x || []).map((_, i) => of((s.roles || [])[i], '') || 'var(' + (AS_TONE[s.tone] || AS_PAL[0]) + ')'); }
  return (c.series || []).map(s => pick(of(s.role, s.tone)));
}
const asChPage = c => t({'#balance': 'bilanz', '#cashflow': 'kapitalfluss'}[(c.link || {}).route] || 'uebersicht');
function asChX(c, i, long) {
  // a column's name: a month (Jan 26 / January 2026), a year -- with the months it holds where they are not all twelve
  const k = String((c.x || [])[i] || '');
  if (c.step === 'month') return long ? MLL(k) : ML(k);
  if (c.step !== 'year' || !long) return k;
  const sp = (c.spans || [])[i];
  return sp && (sp[0].slice(5) !== '01' || sp[1].slice(5) !== '12') ? `${k} (${sp[0] === sp[1] ? MONATE[+sp[0].slice(5) - 1] : MONATE[+sp[0].slice(5) - 1] + ' – ' + MONATE[+sp[1].slice(5) - 1]})` : k;
}
function asChSub(c) {
  const p = c.period || [], n = (c.x || []).length;
  const per = c.kind === 'hbar' ? (p[0] === p[1] ? MLL(p[0] || '') : ML(p[0] || '') + ' – ' + ML(p[1] || '')) : n ? asChX(c, 0) + (n > 1 ? ' – ' + asChX(c, n - 1) : '') : '';
  return [c.area, per, c.kind === 'hbar' ? '' : t(c.step === 'year' ? 'ki_ch_je_jahr' : 'ki_ch_je_monat'), c.as_of && c.as_of !== isoToday() ? t('ki_ch_stand', FD(c.as_of)) : ''].filter(Boolean).join(' · ');
}
function asChart(c, mi, pj) {
  if (!Array.isArray(c.series) || !c.series.length || !Array.isArray(c.x) || !c.x.length) return '';
  const col = asChColors(c), svg = c.kind === 'hbar' ? asChBars(c, AS.cw || 340, col) : asChPlot(c, AS.cw || 340, col);
  const legend = c.kind !== 'hbar' && c.series.length > 1 ? `<div class="chart-legend">${c.series.map((s, k) => `<span><i style="background:${col[k]}"></i>${esc(s.name)}</span>`).join('')}</div>` : '';
  return `<div class="as-chart" data-ex="assistant.chart" data-c="${mi}-${pj}"><div class="as-ch-h"><div class="as-ch-t"><b>${esc(c.title)}</b><span>${esc(asChSub(c))}</span></div>`
    + `<button type="button" class="ghost small as-ch-open" title="${esc(t('ki_ch_oeffnen', asChPage(c)))}">${esc(asChPage(c))} ›</button></div>`
    + `<div class="as-ch-plot">${svg}<div class="bch-tip as-ch-tip hidden" aria-live="polite"></div></div>${legend}</div>`;
}
function asChPlot(c, W, col) {
  // months or years along, lines or bars; planned columns dashed (lines) or paler (bars), the running month dotted
  const n = c.x.length, vals = c.series.flatMap(s => s.values || []).filter(v => v != null && isFinite(v)), f = v => v.toFixed(1), fl = c.flags || [];
  let lo = vals.length ? Math.min(...vals) : 0, hi = vals.length ? Math.max(...vals) : 1;
  if (c.kind === 'bar' || (lo > 0 && lo < hi * 0.35) || (hi < 0 && hi > lo * 0.35)) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }          // bars from zero; a line near it too
  if (hi - lo < 1e-9) { const d = Math.max(1, Math.abs(hi) * 0.1); lo -= d; hi += d; }
  const ticks = niceTicks(lo, hi, 4), st = ticks.length > 1 ? ticks[1] - ticks[0] : 0;
  if (st && ticks[ticks.length - 1] < hi - (hi - lo) * 0.04) ticks.push(ticks[ticks.length - 1] + st);          // a line at both ends of the values (not for a sliver)
  if (st && ticks[0] > lo + (hi - lo) * 0.04) ticks.unshift(ticks[0] - st);
  lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
  const ref = Math.max(...ticks.map(Math.abs)), labs = ticks.map(tk => Fk(tk, false, ref));
  const P = {l: Math.ceil(Math.max(...labs.map(l => textW(l)))) + 10, r: 10, t: 10, b: 20}, H = Math.round(Math.min(260, Math.max(176, W * 0.4))), iw = W - P.l - P.r, band = iw / n;          // wider (as a page): a little taller
  const x = c.kind === 'bar' ? i => P.l + band * (i + 0.5) : i => n > 1 ? P.l + i * iw / (n - 1) : P.l + iw / 2;
  const y = v => P.t + (hi - v) * (H - P.t - P.b) / (hi - lo);
  const G = {W, H, P, n, x, y, band, iw, gw: band * (c.series.length > 1 ? 0.8 : 0.62)};
  c._g = G;
  let g = '';
  ticks.forEach((tk, k) => { g += `<line class="bch-grid${Math.abs(tk) < 1e-9 ? ' zero' : ''}" x1="${P.l}" x2="${W - P.r}" y1="${f(y(tk))}" y2="${f(y(tk))}"/><text class="bch-y" x="${P.l - 6}" y="${f(y(tk) + 4)}">${labs[k]}</text>`; });
  // the names along: as many as fit (months on a round step: every month, quarter, half year, year)
  const each = (iw / n) / (textW(c.step === 'month' ? 'Mär 26' : '2026') + 12), step = c.step === 'month' ? [1, 2, 3, 6, 12, 24, 60].find(k => k * each >= 1) || 60 : Math.max(1, Math.ceil(1 / each));
  for (let i = 0; i < n; i++) {
    const k = String(c.x[i]), mo = c.step === 'month' ? +k.slice(5) : 1, yr = +k.slice(0, 4);
    const show = c.step === 'month' ? (step < 12 ? (mo - 1) % step === 0 : mo === 1 && yr % (step / 12) === 0) : (n - 1 - i) % step === 0;
    if (c.step === 'month' && mo === 1 && i > 0) g += `<line class="bch-year" x1="${f(c.kind === 'bar' ? x(i) - band / 2 : x(i))}" x2="${f(c.kind === 'bar' ? x(i) - band / 2 : x(i))}" y1="${P.t}" y2="${H - P.b}"/>`;
    if (!show) continue;
    const lab = c.step === 'month' ? (step < 12 && mo !== 1 ? ML(k) : String(yr)) : k, w = textW(lab) / 2;
    const anchor = x(i) + w > W - 1 ? 'end' : x(i) - w < P.l - 6 ? 'start' : '';          // at the edges: the name beside its point, not cut off
    if (anchor === 'start' && x(i) - w < 0) continue;
    g += `<text class="bch-x" x="${f(anchor === 'end' ? W - 1 : x(i))}" y="${H - 5}"${anchor ? ` style="text-anchor:${anchor}"` : ''}>${esc(lab)}</text>`;
  }
  const pf = fl.findIndex(v => v === 'plan' || v === 'mixed');
  if (pf > 0) { const xp = c.kind === 'bar' ? x(pf) - band / 2 : x(pf - 1); g += `<line class="bch-today" x1="${f(xp)}" x2="${f(xp)}" y1="${P.t}" y2="${H - P.b}"/>`; }
  if (c.kind === 'bar') {
    const k = c.series.length, bw = G.gw / k;
    c.series.forEach((s, j) => (s.values || []).forEach((v, i) => {
      if (v == null) return;
      const top = Math.min(y(v), y(0)), h = Math.max(1, Math.abs(y(v) - y(0)));
      g += `<rect class="as-ch-bar${fl[i] === 'plan' || fl[i] === 'mixed' ? ' plan' : fl[i] === 'open' ? ' run' : ''}" x="${f(x(i) - G.gw / 2 + bw * j + (k > 1 ? 0.5 : 0))}" y="${f(top)}" width="${f(Math.max(1, bw - (k > 1 ? 1 : 0)))}" height="${f(h)}" rx="${bw > 6 ? 1.5 : 0}" fill="${col[j]}"/>`;
    }));
  } else {
    c.series.forEach((s, j) => {
      const seg = {'': '', run: '', plan: ''}, v = s.values || [];
      for (let i = 1; i < n; i++) if (v[i] != null && v[i - 1] != null) {
        const st = fl[i] === 'plan' || fl[i] === 'mixed' ? 'plan' : fl[i] === 'open' ? 'run' : '';
        seg[st] += `M${f(x(i - 1))} ${f(y(v[i - 1]))}L${f(x(i))} ${f(y(v[i]))}`;
      }
      for (const st of ['', 'run', 'plan']) if (seg[st]) g += `<path class="as-ch-line${st ? ' ' + st : ''}" d="${seg[st]}" stroke="${col[j]}"/>`;
      v.forEach((w, i) => { if (w != null && (v[i - 1] == null) && (v[i + 1] == null)) g += `<circle class="as-ch-pt" cx="${f(x(i))}" cy="${f(y(w))}" r="2.5" fill="${col[j]}"/>`; });          // a value on its own
    });
  }
  g += `<g class="as-ch-hover"></g><rect class="as-ch-hit" x="${P.l}" y="0" width="${iw}" height="${H - P.b + 4}"/>`;
  return `<svg class="as-ch-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(c.title)}">${g}</svg>`;
}
function asChBars(c, W, col) {
  // what something is made of: one bar per part, the largest first, its amount beside it
  const s = c.series[0], v = s.values || [], n = c.x.length, row = 24, H = n * row + 4, f = x => x.toFixed(1);
  const amt = v.map(x => x == null ? '–' : F0(x) + ' €'), aw = Math.max(...amt.map(a => textW(a))) * 1.12 + 12;          // (figures of equal width: a little wider than measured)
  const lw = Math.min(W * 0.42, Math.max(...c.x.map(l => textW(l, 12))) + 10), bx = lw, bmax = Math.max(20, W - lw - aw), top = Math.max(...v.map(x => Math.abs(x || 0)), 1e-9);
  c._g = {W, H, row, lw, n};
  let g = '';
  const fit = (l, w) => { if (textW(l, 12) <= w) return l; let a = l; while (a.length > 2 && textW(a + '…', 12) > w) a = a.slice(0, -1); return a + '…'; };
  c.x.forEach((l, i) => {
    const yy = 2 + i * row, w = Math.max(1, Math.abs(v[i] || 0) / top * bmax);
    g += `<text class="as-ch-lab" x="0" y="${f(yy + row / 2 + 4)}">${esc(fit(String(l), lw - 8))}</text>`
      + `<rect class="as-ch-bar${c.open ? ' run' : ''}" x="${f(bx)}" y="${f(yy + 5)}" width="${f(w)}" height="${row - 10}" rx="2" fill="${col[i]}"/>`
      + `<text class="as-ch-amt" x="${f(bx + w + 6)}" y="${f(yy + row / 2 + 4)}">${esc(amt[i])}</text>`;
  });
  g += `<g class="as-ch-hover"></g><rect class="as-ch-hit" x="0" y="0" width="${W}" height="${H}"/>`;
  return `<svg class="as-ch-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(c.title)}">${g}</svg>`;
}
function asChFrom(el) {
  const box = el.closest('.as-chart'); if (!box) return null;
  const [mi, pj] = box.dataset.c.split('-').map(Number), c = ((AS.msgs[mi] || {}).parts || [])[pj];
  return c && c.k === 'chart' ? {box, c, key: box.dataset.c} : null;
}
function asChAt(svg, e) {
  // the column (and the series) under the pointer
  const h = asChFrom(svg); if (!h || !h.c._g) return null;
  const c = h.c, G = c._g, r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * G.W / r.width, py = (e.clientY - r.top) * G.H / r.height;
  if (c.kind === 'hbar') { const i = Math.floor((py - 2) / G.row); return i >= 0 && i < G.n ? Object.assign(h, {i, s: 0}) : null; }
  const i = Math.max(0, Math.min(G.n - 1, c.kind === 'bar' ? Math.floor((px - G.P.l) / G.band) : G.n > 1 ? Math.round((px - G.P.l) * (G.n - 1) / G.iw) : 0));
  let s = 0;
  if (c.kind === 'bar') s = Math.max(0, Math.min(c.series.length - 1, Math.floor((px - (G.x(i) - G.gw / 2)) / (G.gw / c.series.length))));
  else { let best = Infinity; c.series.forEach((x, k) => { const v = (x.values || [])[i]; if (v != null && Math.abs(G.y(v) - py) < best) { best = Math.abs(G.y(v) - py); s = k; } }); }
  return Object.assign(h, {i, s});
}
function asChTip(h, touch) {
  const {box, c, i, s} = h, tip = $('.as-ch-tip', box), hv = $('.as-ch-hover', box), G = c._g, col = asChColors(c), f = v => v.toFixed(1);
  if (!tip || !hv || !G) return;
  const go = (c.link || {}).route ? `<div class="as-ch-go">${esc(t(touch ? 'ki_ch_tippen' : 'ki_ch_klick', asChPage(c)))}</div>` : '';
  let left;
  if (c.kind === 'hbar') {
    const v = c.series[0].values[i], same = c.series[0].values.filter(x => x != null && (x < 0) === (v < 0)).reduce((a, x) => a + Math.abs(x), 0);
    tip.innerHTML = `<div class="bch-tip-h">${esc(c.x[i])}</div><div class="on"><i style="background:${col[i]}"></i><span>${esc(c.series[0].name)}</span><b>${F0(v)} €</b></div>`
      + (same ? `<div><i></i><span>${t('anteil')}</span><b>${(Math.abs(v) / same * 100).toLocaleString(LOCALE, {maximumFractionDigits: 1})} %</b></div>` : '') + go;
    hv.innerHTML = `<rect class="bch-sel" x="0" y="${f(2 + i * G.row)}" width="${G.W}" height="${G.row}" rx="4"/>`;
    tip.style.top = Math.min(G.H - 10, (i + 1) * G.row + 4) * box.querySelector('.as-ch-svg').getBoundingClientRect().height / G.H + 'px'; left = true;
  } else {
    const fl = (c.flags || [])[i], pill = fl === 'plan' ? t('plan') : fl === 'mixed' ? t('ist_plan') : fl === 'open' ? t(c.step === 'year' ? 'ki_ch_laufendes_jahr' : 'laufender_monat') : '';
    tip.innerHTML = `<div class="bch-tip-h">${esc(asChX(c, i, true))}${pill ? ` <span class="pill neutral">${esc(pill)}</span>` : ''}</div>`
      + c.series.map((x, k) => `<div class="${k === s && c.series.length > 1 ? 'on' : ''}"><i style="background:${col[k]}"></i><span>${esc(x.name)}</span><b>${(x.values || [])[i] == null ? '–' : F0(x.values[i]) + ' €'}</b></div>`).join('') + go;
    const xi = G.x(i);
    hv.innerHTML = c.kind === 'bar' ? `<rect class="bch-sel" x="${f(xi - G.band / 2)}" y="${G.P.t}" width="${f(G.band)}" height="${G.H - G.P.t - G.P.b}"/>`
      : `<line class="bch-cross" x1="${f(xi)}" x2="${f(xi)}" y1="${G.P.t}" y2="${G.H - G.P.b}"/>` + c.series.map((x, k) => (x.values || [])[i] == null ? '' : `<circle class="as-ch-dot" cx="${f(xi)}" cy="${f(G.y(x.values[i]))}" r="${k === s ? 4 : 3}" stroke="${col[k]}"/>`).join('');
    left = xi > G.W * 0.55; tip.style.top = '';
  }
  const svg = $('.as-ch-svg', box), sc = svg.getBoundingClientRect().width / G.W;
  tip.classList.remove('hidden');
  if (c.kind === 'hbar') { tip.style.left = Math.max(0, G.lw * sc - 8) + 'px'; tip.style.right = 'auto'; }
  else if (left) { tip.style.right = (G.W - G.x(i) + 10) * sc + 'px'; tip.style.left = 'auto'; }
  else { tip.style.left = (G.x(i) + 10) * sc + 'px'; tip.style.right = 'auto'; }
}
function asChHide(box) { const tip = box && $('.as-ch-tip', box), hv = box && $('.as-ch-hover', box); if (tip) tip.classList.add('hidden'); if (hv) hv.innerHTML = ''; }
function asChKeep() {
  // the panel was drawn anew (the answer goes on): what was under the pointer stays shown
  const h = AS.sel || AS.hover; if (!h) return;
  const box = $(`#as-body .as-chart[data-c="${h.key}"]`), x = box && asChFrom(box);
  if (x && x.c._g && h.i < x.c._g.n) asChTip(Object.assign(x, {i: h.i, s: h.s}), !!AS.sel);
}
async function asChGo(c, i, s) {
  // a figure of the chart on its page: the page, area and view it belongs to, the row and column marked (i < 0: the page only)
  const L = c.link || {}; if (!/^#[\w/-]+$/.test(L.route || '')) return;
  const ser = c.series[s] || {}, fl = (c.flags || [])[i], mark = i < 0 ? '' : c.kind === 'hbar' ? (ser.marks || [])[i] : ser.mark;
  const col = i < 0 || c.kind === 'hbar' ? (c.kind === 'hbar' && c.period && c.period[0] === c.period[1] ? c.period[0] : '') : String(c.x[i]);
  const ev = {action: 'open', route: L.route, area: L.area || '', view: c.step === 'year' ? 'years' : c.step === 'month' ? 'months' : '', detail: L.detail,
    plan: fl === 'plan' || fl === 'mixed' ? true : undefined, mark: mark ? {text: mark, column: col} : null};
  AS.hover = AS.sel = null;
  if (matchMedia('(max-width: 900px)').matches && S.tab !== 'assistant') asShow(false);          // the panel covers the page there: it steps aside
  else if (matchMedia('(max-width: 900px)').matches) { AS.open = false; try { LS.set('kontor.assist', ''); } catch (e) {} }
  await asOpen(ev);
}
const asText = m => (m.parts || []).filter(p => p.k === 'text').map(p => p.text).join('\n\n').trim();
function asMsg(m, i) {
  const links = m.role === 'user' ? null : asLinks();
  if (m.role === 'user') return `<div class="as-msg me">${(m.refs || []).length || (m.files || []).length ? `<div class="as-refs">${(m.refs || []).map((r, j) => asRefChip(r, `data-m="${i}" data-r="${j}"`, false)).join('')}${(m.files || []).map(f => asFileChip(String(f.name || ''))).join('')}</div>` : ''}${m.text ? `<div class="as-b">${esc(m.text)}</div>` : ''}</div>`;          // as typed or pasted (lines and spaces kept: tables, code); what it refers to before it
  let h = '';
  const parts = m.parts || [];
  parts.forEach((p, j) => {
    if (p.k === 'text') h += `<div class="as-t">${asMd(p.text, links)}</div>`;
    else if (p.k === 'think' || p.k === 'tool') {          // thoughts and the steps between them: one entry (the first of a run draws it)
      if (j && (parts[j - 1].k === 'think' || parts[j - 1].k === 'tool')) return;
      let e = j; while (e < parts.length && (parts[e].k === 'think' || parts[e].k === 'tool')) e++;
      h += asSteps(parts.slice(j, e), i, j, m.state === 'run' && e === parts.length);
    }
    else if (p.k === 'entry') h += asEntry(p, (m.parts || []).some(x => x.k === 'batch' && x.state === 'ask' && (x.ids || []).includes(p.id)));
    else if (p.k === 'batch') h += asBatch(p, m);
    else if (p.k === 'web') h += asWebCard(p, i, j);
    else if (p.k === 'note') h += `<div class="banner info small">${esc(t(p.key || ''))}</div>`;
    else if (p.k === 'memory') h += asMemPart(p);
    else if (p.k === 'basis') h += asBasisPart(p);
    else if (p.k === 'chart') h += asChart(p, i, j);
    else if (p.k === 'err') h += `<div class="banner err small">${esc(p.text)}</div>`;
  });
  // while it runs: the thoughts' own line says "Thinking …" (and opens), the answer's text shows itself growing -- no second line then
  const end = parts[parts.length - 1], busy = end && (end.k === 'text' || ((end.k === 'think' || end.k === 'tool') && (() => { let b = parts.length; while (b && (parts[b - 1].k === 'think' || parts[b - 1].k === 'tool')) b--; return parts.slice(b).some(p => p.k === 'think'); })()));
  if (m.state === 'run' && !(m.parts || []).some(p => (p.k === 'batch' || p.k === 'web') && p.state === 'ask') && (m.status === 'loading' || !busy)) h += `<div class="as-run"><span class="spin"></span>${t(m.status === 'loading' ? 'ki_laedt_modell' : 'ki_denkt')}</div>`;          // the card of changes waiting for the click: nothing is being thought
  else if (m.state === 'stopped') h += `<div class="as-meta">${t('ki_gestoppt')}</div>`;
  else if (m.meta && m.meta.seconds != null) {
    const mm = m.meta, bits = [mm.cut ? t('ki_abgeschnitten') : '', mm.thought != null ? tn('ki_nachgedacht', mm.thought, asN(mm.thought)) : '',
      mm.reads != null ? tn('ki_abfragen', mm.reads, mm.reads) : '', mm.tps ? t('ki_tempo', asN(mm.tps)) : '', mm.limit ? t('ki_denkgrenze') : ''].filter(Boolean);
    h += `<div class="as-meta" data-ex="assistant.steps" title="${esc(t('ki_meta_tip'))}">${bits.map(esc).join(' · ')}</div>`;
  }
  return `<div class="as-msg">${h}</div>`;
}
// Thoughts and the steps between them (what was read, opened, proposed) as one entry: folded, its line names how many steps there
// were -- and while it is the newest thing of an answer, "Thinking …" with the step under way (becomes "Thoughts" once done).
// Steps without thoughts: one line.
function asSteps(run, i, j, now) {
  const tools = run.filter(p => p.k === 'tool'), last = run[run.length - 1];
  const step = p => `<div class="as-tool ${esc(p.kind || '')}">${esc(p.label || '')}</div>`;
  if (!run.some(p => p.k === 'think')) return `<div class="as-tool ${esc((tools[tools.length - 1] || {}).kind || '')}" data-ex="assistant.steps">${tools.map(p => esc(p.label || '')).join(' · ')}</div>`;
  const sub = now && last.k === 'tool' ? esc(last.label || '') : tools.length ? esc(tn('ki_schritte', tools.length, tools.length)) : '';
  return `<details class="as-think${now ? ' now' : ''}" data-ex="assistant.steps" data-m="${i}" data-p="${j}"${run[0].open ? ' open' : ''}><summary>${now ? `<span class="spin"></span>${t('ki_denkt')}` : t('ki_gedanken')}${sub ? `<span class="as-think-s"> · ${sub}</span>` : ''}</summary>`
    + `<div>${run.map(p => p.k === 'tool' ? step(p) : `<p>${esc(p.text).replace(/\n/g, '<br>')}</p>`).join('')}</div></details>`;
}
function asHead() {
  const hd = $('#as-head'); if (!hd) return;
  const page = S.tab === 'assistant', sv = (AS.st || {}).server || {}, st = sv.state || 'stopped';
  const effTip = t('h_ki_denken') + (sv.tps ? ' ' + t('ki_denken_zeit', asN(2000 / sv.tps)) : '');          // the limited one's time on this Mac (from its measured speed)
  hd.innerHTML = `<b>${t('ki_assistent')}</b><span class="as-st ${esc(st)}" title="${esc(t(`ki_z_${st}`))}"></span>
    <span class="as-hb"><select id="as-eff" title="${esc(effTip)}" aria-label="${esc(t('ki_denken'))}">${AS_EFFORTS.map(k => `<option value="${k}" ${asEffort() === k ? 'selected' : ''}>${t(`ki_denken_${k}`)}</option>`).join('')}</select>
    <button class="icon as-hist-btn${AS.list ? ' on' : ''}" title="${esc(t('ki_verlaeufe'))}" aria-label="${esc(t('ki_verlaeufe'))}" aria-pressed="${AS.list}">${ICON.history}</button>
    <button class="icon as-new" title="${esc(t('ki_neu'))}" aria-label="${esc(t('ki_neu'))}">${ICON.compose}</button>
    <button class="icon as-big" title="${esc(t(page ? 'ki_neben_seite' : 'ki_gross'))}" aria-label="${esc(t(page ? 'ki_neben_seite' : 'ki_gross'))}">${ICON.expand}</button>
    ${page ? '' : `<button class="icon as-close" title="${esc(t('ki_schliessen'))}" aria-label="${esc(t('ki_schliessen'))}">✕</button>`}</span>`;
}
function asDraw() {
  $('#assist').innerHTML = `<div class="as-head" id="as-head"></div><div class="as-body" id="as-body"></div>
    <form class="as-form" id="as-form"><div class="as-refs hidden" id="as-refs"></div><div class="as-field" id="as-field"><button type="button" id="as-add" class="as-add" title="${esc(t('ki_anhang'))}" aria-label="${esc(t('ki_anhang'))}">${AS_PLUS}</button>
    <div class="as-ta"><textarea id="as-in" rows="1" maxlength="${(AS.st || {}).question_limit || 9000}" placeholder="${esc(t('ki_frage_ph'))}" aria-label="${esc(t('ki_frage_ph'))}"></textarea><div class="as-ghost" id="as-ghost" aria-hidden="true"></div></div>
    <div class="as-btns" id="as-btns"><button type="button" id="as-x" class="as-x secondary hidden" title="${esc(t('ki_diktat_verwerfen'))}" aria-label="${esc(t('ki_diktat_verwerfen'))}">${AS_CROSS}</button>
    ${(AS.st || {}).dictation ? `<button type="button" id="as-mic" class="as-mic secondary"></button>` : ''}<button type="submit" id="as-go" class="as-go"></button></div></div>
    <input type="file" id="as-file" multiple hidden accept="${AS_ACCEPT}"></form>`;
  asHead(); asMsgs(true); asMicDraw(); asRefsDraw();
  const body = $('#as-body');
  if (window.ResizeObserver) { let w = body.clientWidth;          // another width (the panel became a page, the window changed): the charts drawn to it
    if (AS.ro) AS.ro.disconnect();
    AS.ro = new ResizeObserver(onResizeFrame(() => { const nw = body.clientWidth; if (Math.abs(nw - w) < 24 || PRINT.on || document.body.classList.contains('print-one')) return;          /* printing a chart alone: drawn as it is */ w = nw; if (!AS.list && AS.msgs.some(m => (m.parts || []).some(p => p.k === 'chart'))) asMsgs(); }));
    AS.ro.observe(body); }
  const ta = $('#as-in'), mic = $('#as-mic'); if (mic) mic.addEventListener('click', asMic);
  $('#as-add').addEventListener('click', asAdd); $('#as-x').addEventListener('click', asCancel);
  ta.addEventListener('scroll', () => { const g = $('#as-ghost'); if (g) g.scrollTop = ta.scrollTop; });
  $('#as-file').addEventListener('change', e => { const f = [...(e.target.files || [])]; e.target.value = ''; if (f.length) asFiles(f); });
  asFit(ta); ta.addEventListener('input', () => { asFit(ta); if (!ta.value) AS.pasted = false; });
  ta.addEventListener('paste', e => { const c = e.clipboardData; if (!c) return;
    // a picture or a document from the clipboard (a screenshot, a copied PDF): given like a file through "+" -- a screenshot is
    // named by when it was pasted (the clipboard calls every picture "image.png")
    const got = [...(c.items || [])].filter(it => it.kind === 'file').map(it => it.getAsFile()).filter(Boolean), files = got.length ? got : [...(c.files || [])];
    if (files.length) { e.preventDefault(); const d = new Date(), p2 = n => String(n).padStart(2, '0'), stamp = `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}.${p2(d.getMinutes())}.${p2(d.getSeconds())}`;
      asFiles(files.map(f => /^image\.\w+$/i.test(f.name || '') || !f.name ? new File([f], `${t('ki_bild_eingefuegt')} ${stamp}.${(f.type.split('/')[1] || 'png').replace('jpeg', 'jpg')}`, {type: f.type}) : f)); return; }
    if ((c.getData('text') || '').trim().length >= 40) AS.pasted = true; });          // pasted text in the question: notes from it say so
  ta.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('#as-form').requestSubmit(); } else if (e.key === 'Escape' && AS.busy) { e.stopPropagation(); asStop(); } });
  $('#as-form').addEventListener('submit', e => { e.preventDefault(); if (REC.on || REC.starting) { asMicStop(true, true); return; } if (REC.busy) { REC.go = true; return; }          // dictating: ended, written down, then sent
    if (AS.busy) { asStop(); return; } const v = ta.value; ta.value = ''; asFit(ta); asSend(v); });
  // a text file dropped onto the panel (a table, a script, notes): its text goes into the question, read in the browser -- it is sent
  // with the question to the model on this Mac like anything typed, and stored nowhere
  const box = $('#assist');
  if (!box._drop) {
    box._drop = true;
    box.addEventListener('dragover', e => { if ([...(e.dataTransfer || {}).types || []].includes('Files')) { e.preventDefault(); box.classList.add('drop'); } });
    box.addEventListener('dragleave', e => { if (!box.contains(e.relatedTarget)) box.classList.remove('drop'); });
    box.addEventListener('drop', e => { box.classList.remove('drop'); if (!e.dataTransfer || !e.dataTransfer.files.length) return; e.preventDefault(); asFiles([...e.dataTransfer.files]); });
  }
}
// the question field grows with its text up to 160 px -- a scroll bar only once there is more than fits
function asFit(ta) {
  const size = () => {
    ta.style.height = 'auto';
    const h = ta.scrollHeight + ta.offsetHeight - ta.clientHeight;          // text and padding, and the border
    ta.style.height = Math.min(160, h) + 'px'; ta.style.overflowY = h > 160 ? 'auto' : 'hidden';
    return h;
  };
  if (!ta.getClientRects().length) { ta.style.height = ''; return; }          // not on screen: nothing to measure
  const f = ta.closest('.as-field'), h = size();
  if (!f) return;
  // more than one line: the text takes the whole width of the field, + and the buttons go into a row below it (as in other chats) --
  // back into one row only once the text fits there again (measured, so that it does not switch to and fro)
  const cs = getComputedStyle(ta), pad = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
  if (!f.classList.contains('tall')) {
    AS.taW = ta.clientWidth - pad;
    if (h > parseFloat(cs.lineHeight) * 1.5 + parseFloat(cs.paddingTop) * 2) { f.classList.add('tall'); size(); }
  } else if (!ta.value.includes('\n') && textW(ta.value, parseFloat(cs.fontSize)) < (AS.taW || 0) - 16) { f.classList.remove('tall'); size(); }
}
// Dictating: the microphone is recorded in the browser (16 kHz, mono, up to ten minutes) and written down by the speech model on
// this Mac -- the recording goes to Kontor and nowhere else, and nothing of it is kept. A click on the microphone starts; while it
// runs, the same button ends it and takes the text, ✕ (or Escape) throws it away. While speaking, the field shows what is said so
// far (in pieces of about twenty seconds, each ended in a pause), in italics; at the end the whole recording is written down once
// more, with all its words around each sentence -- that text is the one that stays.
// The click starts at once: the microphone opens and is kept from then on, while the speech model loads beside it if it does not
// run yet (a few seconds). The button turns red and its time starts only once dictating truly runs -- the model is ready and the
// microphone truly hears; until then it turns (what is said meanwhile is written down too).
const REC = {on: false, busy: false, starting: false, cap: false, flow: false, heard: false, direct: false, zeros: null, blocks: 0, zeroBlocks: 0, gen: 0, asked: false, drop: false, go: false, ctx: null, stream: null, node: null, pcm: [], m: 0, rate: 0, sum: 0, cnt: 0, pos: 0, next: 0, t0: 0, timer: null, live: null};
const REC_MAX = 600;          // seconds: then it ends by itself and the text is taken
// the microphone with the filters for speech (echo, noise, level): they keep out what plays on the Mac and the hum around it
const REC_AUDIO = {channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true};
// ... and without them (Einstellungen -> KI-Assistent -> Diktieren -> Mikrofonfilter: aus): it hears at once (measured on a MacBook,
// in Kontor's Mac app: 0.1 s each time, also after a pause), far more quietly -- Kontor levels such a recording itself before it is
// written down (assistant.py, _speech) -- no filter of the system then, not even its level: what the Mac plays can get into the text.
const REC_DIRECT = {channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false};
const REC_DIRECT_WAIT = 600;  // ms its first sound is waited for at most (a microphone that is muted: red anyway)
const asMicDirect = () => ((AS.st || {}).settings || {}).speech_filter === false;
// how long red waits: for the first sound at most, and from it on (without the filters nothing fades in: red with the first sound)
const asMicWait = direct => direct ? [REC_DIRECT_WAIT, 0] : [asMicCap(), REC_SETTLE];
// A microphone opened after a pause hears nothing at first: macOS takes about two seconds to start it with its filters (measured
// on a MacBook, in Kontor's Mac app: 1.9 s each time), and until then only silence (zeros) arrives -- within a few seconds after a
// recording it is still running and hears at once (0.1 s). So red waits for the first sound (a room's hum is enough) and a moment
// more, while the filters fade in. Where the filters turn a quiet room into pure silence, the first sound says nothing: there (and
// before it is known) red comes after a fixed wait, by which the microphone runs.
const REC_SETTLE = 150;       // ms from the first sound until red
const REC_SOUND = 4000;       // ms the first sound is waited for at most where a quiet room is known to be heard
const REC_QUIET = 2200;       // ... and where it is pure silence, or not known yet
try { const z = LS.get('kontor.mic.zeros'); if (z === '0' || z === '1') REC.zeros = z === '1'; } catch (e) {}
const asMicCap = () => REC.zeros === false ? REC_SOUND : REC_QUIET;
// what a recording shows of this microphone: did pure silence arrive between the sounds (in a few of its pieces at least)?
function asMicLearn() {
  if (REC.direct || !REC.heard || REC.blocks < 24) return;          // (two seconds and more: enough to tell; only of the microphone with its filters)
  REC.zeros = REC.zeroBlocks >= Math.max(2, REC.blocks * 0.03);
  try { LS.set('kontor.mic.zeros', REC.zeros ? '1' : '0'); } catch (e) {}
}
const MIC_SVG = '<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><rect x="5.6" y="1.4" width="4.8" height="8.2" rx="2.4" fill="currentColor"/><path d="M3.2 7.6a4.8 4.8 0 0 0 9.6 0M8 12.4v2.2" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';
const AS_PLUS = '<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';
const AS_CROSS = '<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
const AS_ACCEPT = '.txt,.csv,.tsv,.md,.json,.xml,.html,.htm,.yaml,.yml,.toml,.log,.ini,.cfg,.conf,.sql,.py,.js,.ts,.sh,.swift,.pdf,.png,.jpg,.jpeg,.heic,.gif,.xlsx,.xlsm';          // only what can be read: the rest greyed out in the picker
const AS_RECEIPT = /\.(pdf|png|jpe?g|heic|gif)$/i, AS_TABLE = /\.(xlsx|xlsm)$/i, AS_FILES_MAX = 6, AS_FILE_BYTES = 20 * 1024 * 1024;          // receipts for the assistant (assistant.RECEIPT_TYPES, ATTACH_BYTES)
// the microphone button follows the speech model: there as soon as it is loaded, gone when it is deleted -- in the panel as it
// stands (what is typed and the conversation stay), not only after reloading the page
function asMicSync() {
  const box = $('#as-btns'); if (!box) return;
  const want = !!(AS.st || {}).dictation, mic = $('#as-mic');
  if (want && !mic) {
    const b = document.createElement('button'); b.type = 'button'; b.id = 'as-mic'; b.className = 'as-mic secondary';
    b.addEventListener('click', asMic); box.insertBefore(b, $('#as-go')); asMicDraw();
  } else if (!want && mic) { asMicStop(false); mic.remove(); }
}
function asMicDraw() {
  // while dictating: ✕ throws it away, the microphone (its time in it) ends it and takes the text, sending ends it and sends its
  // text; + goes, so the field keeps its width -- a button's content is drawn anew only when the state changes (a click on content
  // redrawn under the pointer would get lost)
  // (while it starts, the button keeps its focus: not disabled, a click then does nothing)
  const b = $('#as-mic'), mode = REC.busy ? 'busy' : REC.starting ? 'start' : REC.on ? 'rec' : '', dict = REC.on || REC.busy || REC.starting;
  if (b) {
    b.classList.toggle('rec', REC.on); b.classList.toggle('busy', REC.busy); b.classList.toggle('start', REC.starting); b.disabled = REC.busy;
    if (b.dataset.mode !== mode || !b.firstChild) { b.dataset.mode = mode; b.innerHTML = REC.busy || REC.starting ? '<span class="spin"></span>' : REC.on ? '<span class="as-rec-t"></span>' : MIC_SVG; }
    if (REC.on) { const sec = Math.floor((Date.now() - REC.t0) / 1000); $('.as-rec-t', b).textContent = Math.floor(sec / 60) + ':' + String(sec % 60).padStart(2, '0'); }
    b.title = t(REC.busy ? 'ki_diktat_schreibt' : REC.starting ? 'ki_diktat_startet' : REC.on ? 'ki_diktat_stopp' : 'ki_diktieren'); b.setAttribute('aria-label', b.title);
  }
  const f = $('#as-field'); if (f) f.classList.toggle('dict', dict);
  const x = $('#as-x'); if (x) x.classList.toggle('hidden', !dict);
  const go = $('#as-go'); if (go && !AS.busy) { go.title = t(dict ? 'ki_diktat_senden' : 'ki_senden'); go.setAttribute('aria-label', go.title); }
}
function asAdd() { if (!REC.on && !REC.busy && !REC.starting) { const f = $('#as-file'); if (f) f.click(); } }          // a file into the question (text, CSV, code)
function asCancel() {
  if (REC.on || REC.starting) asMicStop(false);
  else if (REC.busy) { REC.drop = true; asDictPut(''); }          // the text still on its way: not taken
}
// The microphone may be used without asking each time only as the user sets it -- a page cannot give itself that right. Safari:
// "Allow" per website lasts. Safari's web app in the Dock: macOS keeps only the app's own permission; the page's grant lives
// while the app runs and ends 10 minutes after the last recording (WebKit), so it asks again -- nothing there makes that last.
// Kontor's own Mac app gives it to this page itself: macOS asks once, for the app.
// Under Einstellungen -> KI-Assistent, with the speech model: what holds, where to allow it, a button that asks once.
function asMicNote(state, where, asked) {
  const how = {ios: t('ki_mikro_weg_ios'), app: t('ki_mikro_weg_app'), shell: t('ki_mikro_weg_app'), safari: t('ki_mikro_weg_safari', location.hostname), browser: t('ki_mikro_weg_browser')}[where];
  if (state === 'denied') return {pill: 'warn', label: t('ki_mikro_gesperrt'), text: how};
  if (where === 'shell') return state === 'granted' ? {pill: 'ok', label: t('ki_mikro_erlaubt'), text: t('ki_mikro_dauerhaft')} : {ask: true, text: t('ki_mikro_app_einmal')};
  if (state === 'granted' && where === 'app') return {pill: 'ok', label: t('ki_mikro_erlaubt'), text: t('ki_mikro_app_fragt')};
  if (state === 'granted' && !asked) return {pill: 'ok', label: t('ki_mikro_erlaubt'), text: t('ki_mikro_dauerhaft')};    // before anything asked on this page: for good
  return {ask: state !== 'granted', text: (state === 'granted' ? t('ki_mikro_sitzung') + ' ' : '') + how};
}
async function asMicPerm() {
  const box = $('#as-mic-perm'); if (!box) return;
  let st = null, state = '';
  if (SHELL) state = (await shellPost({mic: 'state'})) || '';          // the Mac app: macOS's permission for it
  else { try { st = await navigator.permissions.query({name: 'microphone'}); } catch (e) {} state = st ? st.state : ''; }
  const ua = navigator.userAgent, safari = /Safari/.test(ua) && !/Chrome|Chromium|CriOS|Edg|Firefox/.test(ua);
  const n = asMicNote(state, SHELL ? 'shell' : IS_IOS ? 'ios' : APP_MODE ? 'app' : safari ? 'safari' : 'browser', REC.asked);
  box.className = 'as-item';
  box.innerHTML = `<span><b>${t('ki_mikrofon')}</b><br><span class="muted small">${esc(n.text)}</span></span>
    <span class="as-act">${n.pill ? `<span class="pill ${n.pill}">${n.label}</span>` : n.ask ? `<button class="small secondary" id="as-mic-ask">${t('ki_mikro_freigeben')}</button>` : ''}</span>`;
  const b = $('#as-mic-ask', box);
  if (b) b.addEventListener('click', async () => {
    REC.asked = true;
    if (SHELL) await shellPost({mic: 'ask'});
    else { try { const m = await navigator.mediaDevices.getUserMedia({audio: true}); m.getTracks().forEach(x => x.stop()); } catch (e) {} }
    asMicPerm();
  });
  if (st && !st.onchange) st.onchange = () => asMicPerm();
}
async function asMic() {
  if (REC.busy || REC.starting) return;          // (a second click while it starts would open the microphone twice)
  if (REC.on) { asMicStop(true); return; }
  const ta = $('#as-in'); if (!ta) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { toast(t('ki_mikro_fehlt'), 6000); return; }
  const gen = ++REC.gen, AC = window.AudioContext || window.webkitAudioContext, direct = asMicDirect();
  let ctx = null;
  try { ctx = new AC(); if (ctx.state === 'suspended') ctx.resume().catch(() => {}); } catch (e) { ctx = null; }          // still in the click: Safari starts sound only from one
  const c0 = Date.now(), took = [0, 0, 0, 0, 0];          // how long the start took (into Kontor's log with the text: where a slow start comes from)
  const ready = api('/api/assistant/listen', {}).then(() => { took[1] = Date.now() - c0; return ''; }, e => (e && e.message) || '?');          // the speech model, loaded beside the microphone
  const at = ta.selectionStart == null ? ta.value.length : ta.selectionStart, to = ta.selectionEnd == null ? at : ta.selectionEnd;
  REC.live = {gen: (REC.live ? REC.live.gen : 0) + 1, busy: false, sent: 0, seg: 0, done: [], cur: '', before: ta.value.slice(0, at), after: ta.value.slice(to)};
  Object.assign(REC, {starting: true, asked: true, direct, flow: false, heard: false, heardAt: 0, blocks: 0, zeroBlocks: 0, t1: 0, took: null, pcm: [], m: 0});
  ta.readOnly = true;          // from now on the field shows what is said (typing would be written over)
  asDictPut(''); asMicDraw();
  const drop = st => { st.getTracks().forEach(x => x.stop()); if (ctx) ctx.close().catch(() => {}); };
  let stream = null;
  try { stream = await navigator.mediaDevices.getUserMedia({audio: direct ? REC_DIRECT : REC_AUDIO}); }
  catch (e) { if (ctx) ctx.close().catch(() => {}); if (gen === REC.gen) { asMicStop(false); toast(t('ki_mikro_verweigert'), 7000); } return; }
  if (gen !== REC.gen) { drop(stream); return; }          // ended while the browser asked
  if (!asMicMay()) { drop(stream); asMicStop(false); return; }          // locked or closed meanwhile: nothing is recorded
  let t1 = 0;
  try {
    REC.stream = stream; REC.ctx = ctx || new AC();
    if (REC.ctx.state === 'suspended') REC.ctx.resume().catch(() => {});
    const src = REC.ctx.createMediaStreamSource(stream);
    REC.node = REC.ctx.createScriptProcessor(4096, 1, 1);
    Object.assign(REC, {rate: REC.ctx.sampleRate, sum: 0, cnt: 0, pos: 0, next: REC.ctx.sampleRate / 16000, cap: true});
    REC.node.onaudioprocess = e => {
      if (!REC.cap) return;
      const d = e.inputBuffer.getChannelData(0);
      const some = d.some(x => x > 1e-6 || x < -1e-6); REC.flow = true;          // (anything at all, far below what an ear hears -- not rounding noise)
      if (REC.heard) { REC.blocks++; if (!some) REC.zeroBlocks++; }          // (pure silence between sounds: see asMicLearn)
      else if (some) { REC.heard = true; REC.heardAt = Date.now(); }          // the first sound: the microphone hears
      asPcm(d); if (REC.m / 16000 >= REC_MAX) asMicStop(true);
    };
    src.connect(REC.node); REC.node.connect(REC.ctx.destination);          // (it only runs while connected; it puts out silence)
    t1 = REC.t1 = Date.now(); took[0] = t1 - c0;
  } catch (e) { if (!REC.ctx) drop(stream); asMicStop(false); return; }          // whatever fails after the microphone was opened: it is let go again
  // red only once it truly runs: the speech model ready, the microphone hearing (its first sound and a moment more -- or the wait over)
  const err = await ready, [most, settle] = asMicWait(direct);
  while (gen === REC.gen && !err && !(REC.heard ? Date.now() - REC.heardAt >= settle : Date.now() - t1 >= most)) await new Promise(r => setTimeout(r, 20));
  if (gen !== REC.gen) return;          // ended meanwhile (✕, Escape, sent, the panel closed, locked)
  if (err) { asMicStop(false); toast(err, 7000); return; }          // the model does not start: said now, not after speaking
  REC.starting = false; REC.on = true; REC.t0 = Date.now(); asMicDraw(); REC.timer = setInterval(() => { asMicDraw(); asLive(); }, 500);
  took[3] = REC.t0 - c0; REC.took = took;          // (took[2], the first sound: when the recording ends)
}
// the microphone's samples as 16 kHz, 16 bit, as they come (each output sample the mean of the input samples it covers) -- ten
// minutes are 19 MB, not the 115 MB of the browser's own samples
function asPcm(d) {
  const R = REC, step = R.rate / 16000, out = new Int16Array(Math.ceil(d.length / step) + 2); let k = 0;
  for (let i = 0; i < d.length; i++) {
    R.sum += d[i]; R.cnt++; R.pos++;
    if (R.pos >= R.next) { out[k++] = Math.max(-32768, Math.min(32767, Math.round(R.sum / R.cnt * 32767))); R.sum = 0; R.cnt = 0; R.next += step; }
  }
  if (k) { R.pcm.push(out.slice(0, k)); R.m += k; }
}
// the samples from..to of the recording (16 kHz) in one piece
function asPcmPart(from, to) {
  const out = new Int16Array(Math.max(0, to - from)); let o = 0, at = 0;
  for (const c of REC.pcm) {
    const a = Math.max(from - at, 0), b = Math.min(to - at, c.length);
    if (b > a) { out.set(c.subarray(a, b), o); o += b - a; }
    at += c.length; if (at >= to) break;
  }
  return out;
}
function asWav(pcm) {
  // a WAV file: mono, 16 bit, 16 kHz
  const buf = new ArrayBuffer(44 + pcm.length * 2), v = new DataView(buf);
  const str = (at, s) => { for (let i = 0; i < s.length; i++) v.setUint8(at + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); v.setUint32(4, 36 + pcm.length * 2, true); str(8, 'WAVE'); str(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, 16000, true); v.setUint32(28, 32000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, 'data'); v.setUint32(40, pcm.length * 2, true);
  for (let i = 0; i < pcm.length; i++) v.setInt16(44 + i * 2, pcm[i], true);
  return new Uint8Array(buf);
}
// the quietest third of a second between two points of the recording: where a piece of the live text ends (in a pause, not in a word)
function asQuiet(from, to) {
  const p = asPcmPart(from, to), w = 480, e = [];
  for (let i = 0; i + w <= p.length; i += w) { let s = 0; for (let j = i; j < i + w; j++) s += p[j] * p[j]; e.push(s); }
  let best = -1, low = Infinity;
  for (let i = 0; i + 10 <= e.length; i++) { let s = 0; for (let j = i; j < i + 10; j++) s += e[j]; if (s < low) { low = s; best = i; } }
  return best < 0 ? to : from + (best + 5) * w;
}
// the dictated text where the cursor stood when recording began, with a space between it and what stands around it ('' puts
// the field back as it was) -- while it is spoken, in italics and paler (a layer over the field shows it so)
function asDictPut(text) {
  const ta = $('#as-in'), L = REC.live; if (!ta || !L) return;
  const ins = text ? (L.before && !/\s$/.test(L.before) ? ' ' : '') + text + (L.after && !/^\s/.test(L.after) ? ' ' : '') : '';
  ta.value = (L.before + ins + L.after).slice(0, +ta.maxLength > 0 ? +ta.maxLength : undefined);
  ta.selectionStart = ta.selectionEnd = Math.min(ta.value.length, (L.before + ins).length);
  const g = $('#as-ghost'); if (g) { g.innerHTML = esc(L.before) + (ins ? `<i class="as-live">${esc(ins)}</i>` : '') + esc(L.after) + '​'; }
  ta.dispatchEvent(new Event('input'));
  if (g) g.scrollTop = ta.scrollTop;
}
const asB64 = u8 => { let bin = ''; for (let i = 0; i < u8.length; i += 0x8000) bin += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(bin); };
// While speaking: every second and a half what was said since the last piece ended, written down (one at a time); a piece that has
// grown past twenty seconds ends in its quietest moment of the last few seconds and its text stays -- so each request stays short,
// however long it is spoken
function asLive() {
  const L = REC.live; if (!REC.on || !L || L.busy || !REC.ctx) return;
  const m = REC.m, k = 16000;
  if (m - L.seg < k * 0.8 || m - L.sent < k * 1.5) return;
  const end = m - L.seg > k * 24 ? asQuiet(L.seg + k * 16, m - k * 0.3) : m, close = end < m, from = L.seg, gen = L.gen;
  L.busy = true; L.sent = m;
  api('/api/assistant/transcribe', Object.assign({audio: asB64(asWav(asPcmPart(from, end))), live: true}, REC.direct ? {direct: true} : {}))
    .then(r => {
      if (!REC.on || !REC.live || REC.live.gen !== gen) return;
      const text = (r.text || '').trim();
      if (close) { if (text) L.done.push(text); L.seg = end; L.cur = ''; } else L.cur = text;
      asDictPut(L.done.concat(L.cur ? [L.cur] : []).join(' '));
    })
    .catch(() => {})          // (the end says what went wrong)
    .finally(() => { L.busy = false; });
}
// recording only while the question field is on screen: signed in, and the panel open or the assistant's own page shown
const asMicMay = () => !!$('#as-in') && !$('#login:not(.hidden)') && (AS.open || S.tab === 'assistant');
async function asMicStop(send, go) {
  if (!REC.on && !REC.starting) return;
  REC.gen++;          // a start still on its way ends here
  clearInterval(REC.timer); REC.on = REC.starting = REC.cap = false;
  if (REC.live) REC.live.gen++;          // a text still on its way from the speech model: no longer shown
  const n = REC.m;
  try { if (REC.node) REC.node.disconnect(); if (REC.stream) REC.stream.getTracks().forEach(x => x.stop()); if (REC.ctx) REC.ctx.close().catch(() => {}); } catch (e) {}
  REC.ctx = REC.node = null; asMicLearn();
  const pcm = send && n >= 16000 * 0.4 ? asPcmPart(0, n) : null; REC.pcm = []; REC.m = 0;
  const free = () => { const ta = $('#as-in'); if (ta) ta.readOnly = false; };
  if (!pcm) { asDictPut(''); free(); asMicDraw(); return; }          // thrown away, or too short to hold a word: the field as it was
  REC.busy = true; REC.drop = false; REC.go = !!go; asMicDraw();
  let send_ = false;
  try {
    if (REC.took) { REC.took[2] = (REC.heard ? REC.heardAt : Date.now()) - REC.t1; REC.took[4] = REC.blocks ? Math.round(100 * REC.zeroBlocks / REC.blocks) : 0; }          // the first sound after the microphone opened (none: until the end); pure silence in percent
    const r = await api('/api/assistant/transcribe', Object.assign({audio: asB64(asWav(pcm))}, REC.took ? {start: REC.took} : {}, REC.direct ? {direct: true} : {})), text = (r.text || '').trim();          // all of it once more: the text that stays
    REC.busy = false;
    if (REC.drop) asDictPut('');          // thrown away meanwhile (✕)
    else if (!text) { toast(t('ki_diktat_nichts'), 4000); asDictPut(''); }
    else { asDictPut(text); send_ = REC.go; const ta = $('#as-in'); if (ta && !send_) ta.focus(); }
  } catch (e) { if (!REC.drop) toast(e.message, 7000); }          // (what was shown while speaking stays)
  free(); REC.busy = false; REC.drop = false; REC.go = false; asMicDraw();
  const ta = $('#as-in');
  if (send_ && ta && !AS.busy) { const v = ta.value; ta.value = ''; asFit(ta); asSend(v); }          // ended with "send": the question goes as it stands now
}
async function asFiles(files) {
  const ta = $('#as-in'); if (!ta) return;
  const room = (AS.st || {}).question_limit || 9000;
  let given = false;
  for (const f of files.slice(0, AS_FILES_MAX)) {
    // an Excel table, a PDF or a picture: goes to Kontor with the question and is read there (a table or the pages of a document as a
    // grid; a receipt by macOS's text recognition, filed only with the click on its card) -- nothing is stored, no right needed to give it
    if (AS_TABLE.test(f.name || '') || AS_RECEIPT.test(f.name || '') || ['application/pdf', 'image/png', 'image/jpeg', 'image/heic', 'image/gif'].includes(f.type || '')) {
      if (f.size > AS_FILE_BYTES) toast(t('ki_beleg_zu_gross', f.name, AS_FILE_BYTES / 1048576), 5000);
      else if ((AS.files || []).length >= AS_FILES_MAX) toast(t('ki_beleg_max', AS_FILES_MAX), 5000);
      else { (AS.files = AS.files || []).push(f); given = true; }
      continue;
    }
    let text = '';
    try { text = f.size <= 4e6 ? await f.text() : ''; } catch (e) {}
    if (!text || /[\u0000-\u0008\u000e-\u001f]/.test(text.slice(0, 4000))) { toast(t('ki_datei_kein_text', f.name), 5000); continue; }          // too large, or not text (a PDF, a picture, a spreadsheet file)
    const block = f.name + ':\n```\n' + text.replace(/\r\n?/g, '\n').trimEnd() + '\n```\n';
    if (ta.value.length + block.length > room) { toast(t('ki_datei_zu_lang', f.name), 5000); continue; }
    ta.value += (ta.value && !ta.value.endsWith('\n') ? '\n' : '') + block;
  }
  if (given) asRefsDraw();
  ta.dispatchEvent(new Event('input')); ta.focus();
}
const asFileB64 = f => new Promise((ok, no) => { const rd = new FileReader(); rd.onload = () => ok(String(rd.result).split(',')[1] || ''); rd.onerror = () => no(rd.error); rd.readAsDataURL(f); });
const asFileChip = (name, i) => `<span class="as-ref as-file"><span class="as-ref-go" title="${esc(name)}"><span class="as-ref-pg">${esc(((name.match(/\.(\w+)$/) || [])[1] || '').toUpperCase())}</span><span class="as-ref-l">${esc(name)}</span></span>`
  + (i != null ? `<button type="button" class="as-ref-x" data-f="${i}" title="${esc(t('ki_beleg_weg'))}" aria-label="${esc(t('ki_beleg_weg'))}">${AS_CROSS}</button>` : '') + '</span>';
// What is open (the same list as on the overview), on an empty conversation: what the assistant can do about it starts with one click as a
// question (its changes still wait for the click on their card), the rest opens its page. Loaded in the background, drawn when there.
const AS_ACT = {categorize: ['categorize', 'transactions'], bookings: ['figures'], receipts: ['transactions'], unexplained: ['figures']};
function asOpenDraw(a) {
  const L = AS.open_items; if (!L || !L.length) return '';
  const r = (a.settings || {}).rights || {}, can = act => a.ready && AS_ACT[act] && AS_ACT[act].every(k => r[k]);
  return `<div class="as-todo"><div class="as-todo-h">${t('ov_offen')}</div>${L.map(([k, x, href, act], i) => `<div class="as-todo-i ${esc(k)}"><i class="ov-todo-d"></i><span>${esc(x)}</span>
    ${can(act) ? `<button class="small secondary as-do" data-i="${i}" type="button">${t('ki_erledigen')}</button>` : `<a class="small as-todo-go" href="${esc(href)}">${t('ki_oeffnen')}</a>`}</div>`).join('')}</div>`;
}
async function asOpenLoad() {
  const D = B(); if (!D || !S.STATUS || AS.open_busy) return;
  AS.open_busy = true;
  try { const L = await openItems(D), was = JSON.stringify(AS.open_items || null); AS.open_items = L; if (JSON.stringify(L) !== was && !AS.msgs.length && !AS.list) asMsgs(); }
  catch (e) { /* the list stays as it was */ }
  finally { AS.open_busy = false; }
}
function asMsgs(bottom) {
  const b = $('#as-body'); if (!b) return;
  const near = bottom || b.scrollHeight - b.scrollTop - b.clientHeight < 80, a = AS.st || {};
  AS.cw = Math.max(240, b.clientWidth - 32);          // charts drawn to the width there is (1 unit = 1 px: their text as on the pages)
  if (AS.list) { b.innerHTML = asHistDraw(); if (bottom) b.scrollTop = 0; asGo(); return; }
  if (!AS.msgs.length) {
    b.innerHTML = (!a.ready ? `<div class="as-empty"><div class="muted">${t('ki_einrichten')}</div>${a.local ? `<a class="more" href="#settings/assistant">${t('ki_zu_einstellungen')}</a>` : `<div class="muted small">${t('ki_nur_am_mac')}</div>`}</div>`
      : `<div class="as-empty">${[1, 2, 3].filter(i => i < 3 || (((a.settings || {}).rights || {}).page && !AS_HIDDEN.includes(S.tab))).map(i => `<button class="as-sug" type="button">${t(`ki_bsp_${i}`)}</button>`).join('')}</div>`)
      + asOpenDraw(a);
    asOpenLoad();
  } else {
    // an unfolded box of thoughts keeps where it was scrolled while the answer streams in (drawn anew with every word) -- read to its
    // end, it follows the new text
    const kept = new Map($$('.as-think[open] > div', b).map(x => [x.parentElement.dataset.m + '/' + x.parentElement.dataset.p, {top: x.scrollTop, end: x.scrollHeight - x.scrollTop - x.clientHeight < 12}]));
    b.innerHTML = AS.msgs.map(asMsg).join(''); spinKeep(b); asChKeep();
    $$('.as-think[open] > div', b).forEach(x => { const k = kept.get(x.parentElement.dataset.m + '/' + x.parentElement.dataset.p); if (k) x.scrollTop = k.end ? x.scrollHeight : k.top; });
  }
  if (near) b.scrollTop = b.scrollHeight;
  asGo();
}
function asGo() { const go = $('#as-go'); if (go) { go.classList.toggle('stop', AS.busy); go.title = t(AS.busy ? 'ki_stopp' : REC.on || REC.busy || REC.starting ? 'ki_diktat_senden' : 'ki_senden'); go.setAttribute('aria-label', go.title); go.textContent = AS.busy ? '■' : '↑'; } }
const asDrawn = () => SCROLL.key === S.tab + '/' + S.sub && !$('#main .loading');          // the page the address names is the one drawn (not still the one before)
function asPage() {
  // the page on screen for the assistant: its text only with the right to read the page, never settings, log or setup
  const r = (((AS.st || {}).settings || {}).rights) || {};
  let text = '';
  if (r.page && !AS_HIDDEN.includes(S.tab) && asDrawn()) {
    text = ($('#main').innerText || '').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').slice(0, 9000);
    const d = $('#drawer'); if (d.classList.contains('open')) text += '\n\n[' + t('ki_seitenfenster') + ']\n' + (d.innerText || '').slice(0, 2500);
  }
  const ti = $('#page-title').firstChild;
  return {route: location.hash || '#overview', title: (ti && ti.textContent) || '', area: S.area || '', text};
}
const asRefPre = refs => (refs || []).map(r => `[${r.label}]\n${r.text}\n`).join('');          // what a question referred to, for the conversation so far
const refSend = r => ({label: r.label, page: r.page, text: r.text, go: r.go || null, ex: r.ex || []});          // what goes to Kontor (not what is for the clipboard)
async function asSend(text) {
  const refs = (AS.refs || []).slice(0, REF_MAX).map(refSend), files = (AS.files || []).slice(0, AS_FILES_MAX);
  text = (text || '').trim(); if (!text && !files.length && refs.length) text = t('ki_ref_frage');          // a file alone: no question, it is looked at for itself
  if ((!text && !files.length) || AS.busy) return;
  if (AS.list) { AS.list = false; asHead(); }
  const hist = AS.msgs.map(x => ({role: x.role, text: x.role === 'user' ? asRefPre(x.refs) + (x.files || []).map(f => `[${f.name}]\n`).join('') + x.text : asText(x)})).filter(x => x.text).slice(-12);
  const m = {role: 'assistant', parts: [], state: 'run', status: ''};
  AS.msgs.push(Object.assign({role: 'user', text}, refs.length ? {refs} : {}, files.length ? {files: files.map(f => ({name: f.name}))} : {}), m);
  AS.job = null;          // (an answer that is over while Kontor still notes what was said: its loop no longer speaks for the panel)
  AS.busy = true; AS.refs = []; AS.files = []; asRefsDraw(); asMsgs(true);
  try {
    const web = AS.msgs.some(x => (x.parts || []).some(p => p.k === 'web' && asWebFetched(p)));          // web text in it: no changes (Kontor knows it; told again after a restart)
    const receipt_text = AS.msgs.slice(0, -2).some(x => (x.files || []).length > 0);          // ... and a file's text (given with an earlier question): a note from an answer waits for the click
    const ids = [];          // the receipts first, each on its own (in memory at Kontor until the question that names them)
    for (const f of files) ids.push((await api('/api/assistant/attach', {name: f.name, content: await asFileB64(f)})).id);
    const r = await api('/api/assistant/ask', Object.assign({question: text, conversation: AS.conv, history: hist, page: asPage(), effort: asEffort(), refs, web, receipt_text}, AS.pasted ? {pasted: true} : {}, ids.length ? {files: ids} : {})); AS.pasted = false;
    AS.job = r.job; AS.conv = r.conversation; asPoll(m, r.job);
  } catch (e) { m.parts.push({k: 'err', text: e.message}); m.state = 'error'; AS.busy = false; asMsgs(); }
}
function asMemPart(p) {
  // a note Kontor kept from what you said (or forgot, or offers to keep): one quiet line under the answer, with a way back
  const old = (p.replaces || []).map(x => `<div class="as-m-old">${esc(t('ki_g_ersetzt', x))}</div>`).join('');
  const undo = `<button type="button" class="ghost small as-m-undo" data-id="${esc(p.id)}">${t('ki_e_zurueck')}</button>`;
  if (p.state === 'ask') return `<div class="as-mem-p ask" data-ex="assistant.notes"><span class="as-m-k">${t('ki_g_merken_frage')}</span><span class="as-m-t">${esc(p.text)}</span><span class="as-m-b"><button type="button" class="small as-m-yes" data-id="${esc(p.id)}">${t('ki_g_merken')}</button><button type="button" class="small secondary as-m-no" data-id="${esc(p.id)}">${t('ki_g_nicht_merken')}</button></span>${old}</div>`;
  if (p.state === 'forgotten') return `<div class="as-mem-p" data-ex="assistant.notes"><span class="as-m-k">${t('ki_g_vergessen_p')}</span>${p.text ? `<span class="as-m-t">${esc(p.text)}</span>${undo}` : ''}</div>`;
  if (p.state === 'undone' || p.state === 'declined' || !p.text) return `<div class="as-mem-p off" data-ex="assistant.notes"><span class="as-m-k">${t('ki_g_nicht_gemerkt')}</span></div>`;
  return `<div class="as-mem-p" data-ex="assistant.notes"><span class="as-m-k">${t(p.state === 'restored' ? 'ki_g_wieder' : 'ki_g_gemerkt')}</span><span class="as-m-t">${esc(p.text)}</span>${p.pasted ? `<span class="tag">${t('ki_g_eingefuegt')}</span>` : ''}${p.state === 'remembered' ? undo : ''}${old}</div>`;
}
function asBasisPart(p) {
  // the notes the answer rests on (Kontor finds them in its words): one quiet line, the day of each in its tooltip
  const ns = (p.notes || []).filter(n => n && n.text);
  return ns.length ? `<div class="as-basis" data-ex="assistant.notes"><span class="as-m-k">${t('ki_g_beruht')}</span>${ns.map(n => `<span class="as-m-t" title="${esc(n.day ? FD(n.day) : '')}">${esc(n.text)}</span>`).join('<span class="as-m-sep">·</span>')}</div>` : '';
}
async function asPoll(m, job) {
  let fails = 0, gone = false, n = 0;
  const late = () => AS.job !== job && m.state !== 'run';          // the answer is there and the next question is asked: what Kontor still notes of this one arrives here
  while (AS.job === job || late()) {
    let r;
    try { r = await api(`/api/assistant/poll?job=${job}&after=${n}`); fails = 0; }
    catch (e) { if (e.status === 401 || e.status === 403 || ++fails > 6) { m.parts.push({k: 'err', text: e.message}); m.state = 'error'; break; } await new Promise(x => setTimeout(x, 1000)); continue; }
    for (const ev of r.events || []) { n = Math.max(n, ev.n || 0); asEvent(m, ev, job); }
    if ((r.events || []).length) asMsgs();
    if (r.gone) { gone = true; break; }
    if (r.done) break;
  }
  (m.parts || []).forEach(p => { if (p.k === 'web' && (p.state === 'ask' || p.state === 'run')) asWebState(p, {state: p.state === 'ask' ? 'declined' : 'stopped'}); });          // the answer is gone (Kontor restarted, no connection): nothing more is fetched
  if (m.state === 'run') m.state = gone ? 'stopped' : 'done';
  if (AS.job === job) { AS.job = null; AS.busy = false; }
  asMsgs(); asLoad();
}
function asEvent(m, ev, job) {
  const last = m.parts[m.parts.length - 1];
  if (ev.type === 'status') m.status = ev.state;
  else if (ev.type === 'delta') { if (last && last.k === 'text') last.text += ev.text; else if ((ev.text || '').trim()) m.parts.push({k: 'text', text: ev.text}); }
  else if (ev.type === 'think') { if (last && last.k === 'think') last.text += ev.text; else m.parts.push({k: 'think', text: ev.text || ''}); }
  else if (ev.type === 'tool') m.parts.push({k: 'tool', label: ev.label, kind: ev.kind});
  else if (ev.type === 'ui') asUi(ev);
  else if (ev.type === 'entry') m.parts.push(Object.assign({}, ev, {k: 'entry'}));
  else if (ev.type === 'chart') m.parts.push(Object.assign({}, ev, {k: 'chart'}));
  else if (ev.type === 'entry_state') { const p = m.parts.find(x => x.k === 'entry' && x.id === ev.id); if (p) { p.state = ev.state; p.text = ev.text || ''; if (ev.fixed) p.fixed = true; } if (ev.state === 'done') asChanged(); }
  else if (ev.type === 'batch') m.parts.push({k: 'batch', id: ev.id, state: 'ask', ids: ev.ids || []});
  else if (ev.type === 'web') m.parts.push(Object.assign({}, ev, {k: 'web', items: (ev.items || []).map(it => Object.assign({}, it))}));
  else if (ev.type === 'web_state') { const p = m.parts.find(x => x.k === 'web' && x.id === ev.id); if (p) asWebState(p, ev); }
  else if (ev.type === 'web_item') { const p = m.parts.find(x => x.k === 'web' && x.id === ev.id), it = p && (p.items || []).find(x => x.id === ev.item); if (it) Object.assign(it, {state: ev.state, count: ev.count, text: ev.text || '', links: ev.links || []}); }
  else if (ev.type === 'notice') m.parts.push({k: 'note', key: ev.key});
  else if (ev.type === 'memory') m.parts.push(Object.assign({}, ev, {k: 'memory'}));
  else if (ev.type === 'basis') m.parts.push({k: 'basis', notes: ev.notes || []});
  else if (ev.type === 'batch_state') { const p = m.parts.find(x => x.k === 'batch' && x.id === ev.id); if (p) Object.assign(p, {state: ev.state, done: ev.done, failed: ev.failed, left: ev.left}); }
  else if (ev.type === 'reset') { while (m.parts.length && m.parts[m.parts.length - 1].k === 'text') m.parts.pop(); }          // what was shown was a tool call written as text, not an answer
  else if (ev.type === 'done') { m.state = 'done'; m.meta = ev; if (AS.job === job) AS.busy = false; }          // the answer is there: the next question may come (Kontor may still note what was said -- that shows under the answer)
  else if (ev.type === 'stopped') m.state = 'stopped';
  else if (ev.type === 'error') { m.state = 'error'; m.parts.push({k: 'err', text: ev.text || ''}); }
  if (ev.type === 'stopped' || ev.type === 'error') m.parts.forEach(p => { if (p.k === 'entry' && p.state === 'queued') p.state = 'declined'; else if (p.k === 'web' && (p.state === 'ask' || p.state === 'run')) asWebState(p, {state: p.state === 'ask' ? 'declined' : 'stopped'}); });          // never decided: nothing was made or fetched
}
// a value was entered (or taken back): the figures on the page follow
function asChanged() { setTimeout(async () => { try { await loadAll(); softRoute(); pollStatus().catch(() => {}); } catch (e) {} }, 300); }
// The assistant marks something on the page -- a row of a table, one figure (row and column), a card, a control -- found by the
// text the page shows. Marked for a few seconds and scrolled into view; nothing is clicked or changed.
const asNorm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
function asLabel(el) { const c = el.cloneNode(true); c.querySelectorAll('.hq, .cnt, .cf-abbr, .tag, .pill, .caret, .disc, svg, small, select, input, textarea').forEach(x => x.remove()); return asNorm(c.textContent); }
function asFind(text, column) {
  const want = asNorm(text), main = $('#main'); if (!want || !main) return null;
  const sc = s => !s ? 0 : s === want ? 3 : s.startsWith(want) ? 2 : s.includes(want) && want.length > 2 ? 1 : 0;
  const seen = el => el.getClientRects().length > 0;
  let best = null;
  const offer = (score, rank, o) => { if (score && (!best || score * 10 + rank > best.v)) best = Object.assign({v: score * 10 + rank}, o); };
  for (const tbl of $$('table', main)) {            // rows: the names may stand in a table of their own beside the figures (cash flow, planning)
    const twin = tbl.classList.contains('cf-names') ? $('table.cf-tbl:not(.cf-names)', tbl.closest('.cf-pair') || main) : null;
    for (const tr of tbl.rows) {
      if (!seen(tr) || tr.parentElement.tagName === 'THEAD' || !tr.cells.length || tr.cells[0].tagName === 'TH' && tr.rowIndex === 0) continue;
      const cell = [...tr.cells].find(c => asLabel(c)); if (!cell || cell.cellIndex > 1) continue;
      offer(sc(asLabel(cell)), 3, {what: 'row', label: asLabel(cell), row: tr, vals: twin ? twin.rows[tr.rowIndex] : tr, head: (twin || tbl).rows[0], name: cell});
    }
  }
  for (const h of $$('.card b, .card .l, .card .t, .ov-head b, h2, h3, legend, .module .t', main)) {          // cards and sections by their title
    if (seen(h)) offer(sc(asLabel(h)), 2, {what: 'card', label: asLabel(h), el: h.closest('.card, .module, fieldset') || h});
  }
  for (const el of [...$$('button, a, label, summary, .seg button', main), ...$$('#nav a, #sync-btn, #lock-btn, #assist-btn')]) {       // controls and menu entries
    if (seen(el)) offer(Math.max(sc(asLabel(el)), sc(asNorm(el.getAttribute('aria-label'))), sc(asNorm(el.title))), 1, {what: 'control', label: asLabel(el) || asNorm(el.title), el});
  }
  if (!best) return null;
  const exact = best.v >= 30;
  if (best.what !== 'row') return {what: best.what, label: best.label, els: [best.el], column: '', exact};
  let cell = null, col = '';
  if (column && best.head) {          // one figure: the column by its heading (a month as the tables write it, a year)
    const c = String(column).trim(), cand = [asNorm(c)].concat(/^\d{4}-\d{2}$/.test(c) ? [asNorm(ML(c)), asNorm(MLL(c))] : []);
    const hit = [...best.head.cells].find(h => cand.includes(asLabel(h))) || [...best.head.cells].find(h => cand.some(x => asLabel(h).split(' ').includes(x)));
    if (hit && best.vals && best.vals.cells[hit.cellIndex]) { cell = best.vals.cells[hit.cellIndex]; col = hit.textContent.replace(/\s+/g, ' ').trim(); }
  }
  return {what: cell ? 'figure' : 'row', label: best.label, els: cell ? [cell, best.name] : [...new Set([best.row, best.vals].filter(Boolean))], column: col, scroll: cell || best.row, exact};
}
async function asMark(mark) {
  let hit = asFind(mark.text, mark.column);
  const want = asNorm(mark.text), D = B(), isRow = hit && (hit.what === 'row' || hit.what === 'figure');
  // a row of that very name the tables have but do not show (inside a closed group): it is what is meant, before a card or button of the same name
  const hidden = !isRow && D && (S.tab === 'balance' ? D.balance.rows.some(r => !r.group && asNorm(r.name) === want)
    : (S.tab === 'cashflow' || S.tab === 'planning') && D.cashflow.sections.some(x => x.rows.some(z => [z.row, z.row.split(' / ').pop()].concat((z.details || []).map(d => (d.category || '').split(' / ').pop())).some(n => asNorm(n) === want))));
  const vague = !hit || hidden || !hit.exact && !isRow;          // nothing, or only something that sounds alike
  if (vague && (S.tab === 'cashflow' || S.tab === 'planning') && cfLevel() < 3) {          // the table opened all the way, then looked for again
    S[S.tab === 'planning' ? 'planEbene' : 'cfEbene'] = 3; S.cfTog = {}; await route(); hit = asFind(mark.text, mark.column);
  } else if (vague && S.tab === 'balance' && B() && B().balance.rows.some(r => r.group && !(S.posOpen || {})[r.role])) {          // an account: the positions opened
    S.posOpen = S.posOpen || {}; B().balance.rows.forEach(r => { if (r.group) S.posOpen[r.role] = true; }); await route(); hit = asFind(mark.text, mark.column);
  }
  $$('.as-mark').forEach(x => x.classList.remove('as-mark'));
  clearTimeout(AS.markT);
  if (!hit) return {found: false};
  hit.els.forEach(el => el.classList.add('as-mark'));
  (hit.scroll || hit.els[0]).scrollIntoView({block: 'center', inline: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
  AS.markT = setTimeout(() => $$('.as-mark').forEach(x => x.classList.remove('as-mark')), 12000);
  return {found: true, what: hit.what, label: hit.label, column: hit.column};
}
async function asDrawnWait() {          // until the page asked for has been drawn (a slow connection: up to ten seconds)
  let last = -1, same = 0;
  for (let i = 0; i < 70 && same < 2; i++) { await new Promise(x => setTimeout(x, 140)); const n = $('#main').innerHTML.length; same = n === last && asDrawn() ? same + 1 : 0; last = n; }
}
async function asOpen(ev) {
  // a page opened as the assistant asked (or a click on its chart): its area, view, year and depth -- and what was named marked there
  if (S.tab === 'assistant' && !matchMedia('(max-width: 900px)').matches) { AS.open = true; try { LS.set('kontor.assist', '1'); } catch (e) {} }
  if (!/^#[\w/-]+$/.test(ev.route || '')) return null;
  if (ev.area && S.DATA && (S.DATA.areas || {})[ev.area]) { S.area = ev.area; S.collapsed = {}; bereichSeg(); }
  if (ev.view === 'months' || ev.view === 'years') S.mode = ev.view;
  if (ev.plan === true || ev.plan === false) S.plan = ev.plan;
  if (/^\d{4}$/.test(ev.year || '')) {             // the year asked for: the tax page's year, the period of the cash flow's charts
    if (ev.route === '#tax') { S.steuerJahr = ev.year; if (ev.area) S.steuerEnt = ev.area; }
    if (ev.route === '#cashflow') { S.cfZeit = ev.year; S.cfBrZoom = S.cfWbZoom = null; }
  }
  if ([0, 1, 2, 3].includes(ev.detail) && (ev.route === '#cashflow' || ev.route === '#planning')) { S[ev.route === '#planning' ? 'planEbene' : 'cfEbene'] = ev.detail; S.cfTog = {}; }
  if (location.hash === ev.route) await route(); else go(ev.route);
  if (!ev.mark) return null;
  await asDrawnWait();
  return asMark(ev.mark);
}
async function asUi(ev) {
  // the assistant opens a page, shows transactions or marks something -- then it is told how the page looks now (and what it found)
  const job = AS.job;
  let result = null;
  try {
    if (S.tab === 'assistant') { AS.open = true; try { LS.set('kontor.assist', '1'); } catch (e) {} }
    if (ev.action === 'open') {
      result = await asOpen(ev);
    } else if (ev.action === 'mark' && ev.mark) {
      result = await asMark(ev.mark);
    } else if (ev.action === 'transactions') {
      const f = ev.filter || {};
      const kats = Array.isArray(f.categories) && f.categories.length ? f.categories.filter(c => typeof c === 'string').slice(0, 40) : null;
      Object.assign(S.uf, {entity: f.entity || '', year: f.year || '', account: f.account || '', q: f.q || '', ohne_beleg: !!f.without_receipt, uncategorized_flag: !!f.uncategorized, direction: {out: 'aus', in: 'ein'}[f.direction] || '',
        kats, date_from: f.from || '', date_to: f.to || '', title: '', est: false, ext: false, mitOhne: false, katsLabel: kats ? String(f.label || '') : '', rChart: false, ids: null, cfRows: null});
      S.sel.clear();
      if (S.tab === 'transactions') await route(); else go('#transactions');
    }
    if (!result) await asDrawnWait();
  } catch (e) {}
  api('/api/assistant/page', {job, id: ev.id, page: asPage(), result}).catch(() => {});
}
// ---------------------------------------------------------------- Ask the assistant about something on the page (right click)
// What is clicked becomes a reference: a figure (row and column), a row (its name), a column (its heading), a chart, a card or a
// selected text. It stands small above the question and goes with it -- what it is, as the page shows it, like typed in by the
// user. In the chat it stands before the question; a click on it opens that place again (page, area, view) and marks it.
// Never on settings, log or setup; only while the assistant is switched on.
const REF_MAX = 6;
const REF_CHARTS = '#main #bch, #main .lc, #main .cf-card, #main .ov-card, #main .im-chart, #drawer .h-chart, #assist .as-chart';
const refOne = s => String(s || '').replace(/\s+/g, ' ').trim();
const refCut = (s, n) => s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s;
const refTxt = (el, n) => (el ? el.innerText || el.textContent || '' : '').split('\n').map(refOne).filter(l => /[\p{L}\p{N}]/u.test(l)).join(' ').slice(0, n);          // a chart's or card's text on one line (labels and figures in turn)
// a figure in full (its cents too, drawn smaller); a field: what it holds or shows (the chosen entry, not every one of the list)
const refVal = el => { const f = el && (el.matches('select, input, textarea') ? el : $('select, input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"]), textarea', el));
  return refOne(f ? (f.tagName === 'SELECT' ? (f.selectedOptions[0] || {}).textContent : f.value || f.placeholder) : el && (el.innerText || el.textContent)); };
function refLabel(el) {          // a name as the page shows it -- the same parts left out as asLabel(), so the place is found again by it
  if (!el) return '';
  if (el.tagName === 'DETAILS' && $(':scope > summary', el)) el = $(':scope > summary', el);          // folded: its title line, not all inside
  // left out: help marks, counts, tags, the grey line below a name (path, kind), fields and the row's own buttons (✓ in the plan)
  const c = el.cloneNode(true); c.querySelectorAll('.hq, .cnt, .cf-abbr, .tag, .pill, .caret, .disc, svg, small, .small, select, input, textarea, .lc-mode, .alpha-tag, .edit').forEach(x => x.remove());
  return refOne(c.textContent).replace(/\s*›$/, '');
}
function refChartTitle(box) {
  let s = refLabel($('.lc-title, .bch-title, .bch-head > b, .ov-head b, .as-ch-t b, h3, h2', box));
  const sl = !s && $('.lc-head select, .bch-head select', box); if (sl && sl.selectedOptions[0]) s = refOne(sl.selectedOptions[0].textContent);
  if (!s && box.id === 'bch') s = [t('bilanz'), refOne(($('#bch-range', box) || {}).textContent || '')].filter(Boolean).join(' · ');          // the balance sheet's own chart: named by its range
  return s;
}
function refHeading(el) {          // a table without a card of its own: the heading above it
  for (let x = el; x && x.id !== 'main' && x.id !== 'drawer'; x = x.parentElement) {
    for (let s = x.previousElementSibling; s; s = s.previousElementSibling) if (/^H[23]$/.test(s.tagName)) return refLabel(s);
  }
  return '';
}
function refTitle(el) {          // the card or section something stands in, by its title
  const dr = el.closest('#drawer'); if (dr) return refLabel($(':scope > h2', dr));
  const box = el.closest('.card, .co-card, .module, fieldset'); if (!box) return refHeading(el);
  return refChartTitle(box) || refLabel($(':scope legend, :scope .t, :scope > details > summary', box)) || refHeading(box);
}
function refGo(extra) {          // where it was: page, area, view -- as asOpen() opens it again
  const g = {route: location.hash || '#overview', area: S.area || '', view: S.mode, plan: !!S.plan};
  if (S.tab === 'cashflow' && /^\d{4}$/.test(S.cfZeit || '')) g.year = S.cfZeit;
  if (S.tab === 'tax' && /^\d{4}$/.test(String(S.steuerJahr || ''))) g.year = String(S.steuerJahr);
  if (S.tab === 'cashflow' || S.tab === 'planning') g.detail = cfLevel();
  return Object.assign(g, extra);
}
function refHead(where) {          // the first lines of what the model reads: page, area, section
  const ti = $('#page-title').firstChild, ab = $('#bereich-seg:not(.hidden) button.on');
  return [`${t('ref_seite')}: ${refOne(ti && ti.textContent)}${ab ? ' · ' + t('ref_bereich') + ': ' + refOne(ab.textContent) : ''}`].concat(where ? [`${t('ref_abschnitt')}: ${where}`] : []);
}
function refMake(label, lines, where, go) {
  const ti = $('#page-title').firstChild;
  return {label: refCut(label, 64), page: refOne(ti && ti.textContent), text: refHead(where).concat(lines).join('\n').slice(0, 1500), go};
}
const refSeen = el => el && el.getClientRects().length > 0;
const refOver = (a, b) => { const r = a.getBoundingClientRect(), s = b.getBoundingClientRect(), m = (r.left + r.right) / 2; return m >= s.left - 1 && m <= s.right + 1; };
const refNum = s => s.replace(/−/g, '-');          // a figure for the clipboard: a minus Excel and Numbers read
function refPath(tr, names) {          // a row's place: the rows above it it belongs to (cash flow by depth, balance sheet by group)
  const rows = [...names.rows], i = rows.indexOf(tr), out = [];
  if (tr.dataset.depth != null) {
    let d = +tr.dataset.depth;
    for (let j = i - 1; j >= 0 && d > 0; j--) { const r = rows[j]; if (r.dataset.depth != null && +r.dataset.depth < d) { d = +r.dataset.depth; const c = [...r.cells].find(x => refLabel(x)); if (c) out.unshift(refLabel(c)); } }
  } else if (!tr.classList.contains('group') && !tr.classList.contains('total')) {          // (net worth: a total, in no position)
    const g = rows.slice(0, i).reverse().find(r => r.classList.contains('group')); const c = g && [...g.cells].find(x => refLabel(x)); if (c) out.push(refLabel(c));
  }
  return out;
}
function refCell(cell) {
  // a table: its names may stand in a table of their own beside the figures (cash flow, planning)
  const tbl = cell.closest('table'), pair = tbl.closest('.cf-pair');
  const names = pair ? $('table.cf-names', pair) || tbl : tbl, vals = pair ? $('table.cf-tbl:not(.cf-names)', pair) || tbl : tbl;
  const head = vals.tHead && vals.tHead.rows.length ? vals.tHead.rows[vals.tHead.rows.length - 1] : vals.rows[0];
  const tr = cell.parentElement, where = refTitle(tbl);
  // a column's heading for a cell: by its place in the row where heading and rows have the same cells (a column scrolled under the
  // fixed names stays its own), else by where it stands; controls and fillers are no column
  const usable = h => h && refLabel(h) && !h.classList.contains('snap-pad') && !h.classList.contains('cf-ph') && !h.querySelector('button, select, input');
  const headOf = c => { if (!head) return null; const h = head.cells.length === c.parentElement.cells.length ? head.cells[c.cellIndex] : [...head.cells].find(x => refOver(c, x)); return usable(h) ? h : null; };
  const colName = (h, v) => { const k = (v || h).classList, tag = k.contains('plan') ? t('plan') : h.title === t('ist_plan') ? t('ist_plan') : k.contains('part') ? t('ref_laufend')
      : /^\d{4}-\d{2}$/.test(h.dataset.key || '') ? t('ref_abgeschlossen') : '';          // a month column: closed (actual), running or planned -- always said
    return refLabel(h) + (tag ? ` (${tag})` : ''); };          // a plan value, a sum with plan in it, the running month: said
  const nameOf = row => { const r = names.rows[row.rowIndex]; const c = r && [...r.cells].find(x => refLabel(x)); return c && c.cellIndex <= 1 ? c : null; };
  const pairsOf = (vrow, name) => head ? [...vrow.cells].map(v => { if (v === name || v.classList.contains('cf-ph') || v.classList.contains('snap-pad')) return null; const h = headOf(v); return h ? [colName(h, v), refVal(v), refLabel(h)] : null; }).filter(p => p && p[1]) : [];          // (the plain heading: for the clipboard)
  const newest = (ps, n) => ps.length > n ? {ps: ps.slice(-n), cut: [t('ref_gekuerzt', n, ps.length)]} : {ps, cut: []};          // the latest columns (on the right), said when some are left out
  const markOf = c => { const m = c && [...c.querySelectorAll('.tag, .pill')].filter(x => x.getClientRects().length).map(x => refOne(x.textContent)).filter(Boolean); return m && m.length ? [`${t('ref_kennzeichen')}: ${m.join(' · ')}`] : []; };
  if (tr === head || cell.closest('thead')) {          // a heading: the whole column
    const col = refLabel(cell); if (!col) return null;
    const at = head && head.cells.length ? cell.cellIndex : -1;
    const rows = [...vals.tBodies].flatMap(b => [...b.rows]).filter(refSeen).map(r => { const n = nameOf(r), v = at >= 0 && r.cells.length === head.cells.length ? r.cells[at] : [...r.cells].find(c => refOver(c, cell)); return n && v && v !== n ? [refLabel(n), refVal(v)] : null; }).filter(Boolean);
    const cn = usable(cell) ? colName(cell, null) : col;
    return Object.assign(refMake(t('ki_ref_spalte', col), [`${t('ref_spalte')}: ${cn}`, `${t('ref_werte')}:`].concat(rows.slice(0, 40).map(([n, v]) => `${n}: ${v}`)), where, refGo({col})),
      {copy: [['', col]].concat(rows).map(([n, v]) => n + '\t' + refNum(v)).join('\n'), copyKey: 'spalte_kopieren'});
  }
  const name = nameOf(tr); if (!name) return null;
  const row = refLabel(name), vrow = vals.rows[tr.rowIndex] || tr, path = refPath(names.rows[tr.rowIndex] || tr, names), pairs = pairsOf(vrow, name);
  const pathLine = path.length ? [`${t('ref_pfad')}: ${path.concat([row]).join(' › ')}`] : [];
  const ntr = names.rows[tr.rowIndex] || tr, depth = ntr.dataset.depth != null && (S.tab === 'cashflow' || S.tab === 'planning') ? {detail: Math.min(3, Math.max(cfLevel(), +ntr.dataset.depth))} : {};          // opened again deep enough to show the row
  if (tbl === names && names !== vals || cell.cellIndex <= name.cellIndex) {          // the name: the whole row
    const nw = newest(pairs, 30);
    return Object.assign(refMake(t('ki_ref_zeile', row), [`${t('ref_zeile')}: ${row}`].concat(pathLine, markOf(name), nw.cut, [`${t('ref_werte')}:`], nw.ps.map(([h, v]) => `${h}: ${v}`)), where, refGo(Object.assign({mark: {text: row, column: ''}}, depth))),
      {copy: ['\t' + pairs.map(p => p[2]).join('\t'), row + '\t' + pairs.map(p => refNum(p[1])).join('\t')].join('\n'), copyKey: 'zeile_kopieren'});
  }
  const h = headOf(cell), col = h ? colName(h, cell) : '', val = refVal(cell);          // one figure: its row and column (a narrow table: the whole row too, as a transaction)
  const why = cell.matches('td.plan[data-tip]') ? [`${t('ref_berechnung')}: ${cell.dataset.tip.split('\n').filter(l => l !== t('pw_doppelklick')).join(' · ')}`] : [];          // a plan figure: how it came about, as its tooltip says
  return Object.assign(refMake(row + (h ? ' · ' + refLabel(h) : '') + (val ? ': ' + val : ''), [`${t('ref_zeile')}: ${row}`].concat(pathLine, markOf(name), col ? [`${t('ref_spalte')}: ${col}`] : [], [`${t('ref_wert')}: ${val || '–'}`], why,
    pairs.length && pairs.length <= 10 ? [`${t('ref_ganze_zeile')}: ` + pairs.map(([hh, v]) => `${hh}: ${v}`).join(' · ')] : []), where, refGo(Object.assign({mark: {text: row, column: h ? refLabel(h) : ''}}, depth))),
    val ? {copy: refNum(val), copyKey: 'wert_kopieren'} : {});
}
function refChat(box) {          // a chart in the chat: its figures, and the page it belongs to
  const h = asChFrom(box), c = h && h.c; if (!c) return null;
  const lines = [`${t('ref_grafik')}: ${c.title}`, asChSub(c)].concat((c.series || []).slice(0, 6).map(s => `${s.name || ''}: ` + (c.x || []).slice(-24).map((x, i, a) => {
    const k = (c.x || []).length - a.length + i; return `${asChX(c, k)} ${(s.values || [])[k] == null ? '–' : FN((s.values || [])[k])}`; }).join('; ')));
  const L = c.link || {}, go = /^#[\w/-]+$/.test(L.route || '') ? {route: L.route, area: L.area || '', view: c.step === 'year' ? 'years' : c.step === 'month' ? 'months' : '', detail: L.detail} : null;
  const pt = refPoint(box); if (pt) lines.splice(2, 0, `${t('ref_punkt')}: ${pt.text}`);
  return {label: refCut(t('ki_ref_grafik', c.title) + (pt ? ' · ' + pt.head : ''), 64), page: t('ki_assistent'), text: lines.filter(Boolean).join('\n').slice(0, 1500), go, ex: ['assistant.chart']};
}
function refPoint(chart) {          // the point of a chart under the pointer: what its hover box shows (a month, a bar, a slice)
  const own = CF.tipFor && chart.contains(CF.tipFor);          // the cash flow's hover box is one for the page: only when it shows something of this chart
  const tip = [...$$('.bch-tip, .as-ch-tip', chart), own ? $('#cf-tip') : null].find(x => x && !x.classList.contains('hidden') && refSeen(x) && refOne(x.textContent));
  if (!tip) return null;
  return {head: refLabel($('.bch-tip-h, .cf-tip-h, b', tip)) || refCut(refOne(tip.textContent), 30), text: refTxt(tip, 600)};
}
// A figure in a chart or card (not in a table): its row -- named by that row's hover box, or by the text beside it -- and its value;
// found again by the same name (or value) and marked itself, not only its card.
const refIsNum = s => !!s && s.length <= 24 && /\d/.test(s) && !/\p{L}{3,}/u.test(s);          // +48.660 · 62.533 € · ±0,0 % · 420T €
function refTip(el) {          // what the hover box of a row of a chart says: its name (first line) and its figures
  const k = el ? el.dataset.cftip ?? el.dataset.reftip : null, h = k != null ? CF.tips[+k] : null; if (!h) return null;          // reftip: a hover box only for a right click (the ring's middle says "back" when hovered)
  const d = document.createElement('div'); d.innerHTML = h;
  return {head: refLabel($('.cf-tip-h', d)), text: refTipLines(d, []).join(' · ').slice(0, 600)};
}
// a hover box (not on the page, so without layout) as lines -- each name with its figure ("Betrag: 17.400 €"), a row's change in
// brackets after it -- instead of its texts run together
const refWords = el => refOne([...el.childNodes].map(n => n.textContent).join(' '));          // a figure and what stands beside it (1.450 € ±0 %), not run together
function refTipLines(el, out) {
  const inline = x => /^(SPAN|B|EM|I|SMALL)$/.test(x.tagName);
  for (const c of el.children) {
    const kids = [...c.children];
    if (c.classList.contains('cf-tip-kv')) { for (let i = 0; i + 1 < kids.length; i += 2) out.push(`${refOne(kids[i].textContent)}: ${refWords(kids[i + 1])}`); continue; }
    if (kids.length && !kids.every(inline)) { refTipLines(c, out); continue; }
    const name = kids.find(x => x.tagName === 'SPAN'), val = kids.find(x => x.tagName === 'B'), more = kids.find(x => x.tagName === 'EM');
    if (name && val) { out.push(`${refOne(name.textContent)}: ${refWords(val)}` + (more && refOne(more.textContent) ? ` (${refOne(more.textContent)})` : '')); continue; }
    const s = refOne(c.textContent); if (s) out.push(s);
  }
  return out;
}
// a figure as written on the page -- 17.400 · −2,3 % · 420T € · 1,2 Mio. -- as a number (its sign apart: expenses are shown positive in
// places) with how exactly it is shown, so a short figure is found again among the exact ones of its hover box
function refQty(s) {
  s = String(s || '').replace(/\u2212/g, '-').replace(/[\s\u00a0€]/g, '').replace(/^±/, '');
  const pct = /%$/.test(s); s = s.replace(/%$/, '');
  const m = s.match(/^[+-]?([\d.,']+)(T|Tsd\.?|k|M|Mio\.?|Mrd\.?|B)?$/i); if (!m) return null;
  const f = !m[2] ? 1 : /^(t|tsd|k)/i.test(m[2]) ? 1e3 : /^(mrd|b)/i.test(m[2]) ? 1e9 : 1e6;
  const n = m[1].split(GRP).join('').replace(DEC, '.'), v = parseFloat(n); if (!isFinite(v)) return null;
  const dec = n.includes('.') ? n.length - n.indexOf('.') - 1 : 0;
  return {v: Math.abs(v * f), pct, tol: Math.pow(10, -dec) * f / 2 + 0.005};
}
const refSameQty = (a, b) => a.pct === b.pct && Math.abs(a.v - b.v) <= Math.max(a.tol, b.tol);
const refLeaves = box => [...box.querySelectorAll('*')].filter(el => el.children.length === 0 || [...el.children].every(c => /^(i|small|tspan)$/i.test(c.tagName)));
// a label of an axis or a grid line: a scale, no figure of the chart
const REF_AXIS = '[class*="tick"], [class*="axis"], [class*="grid-l"], .bch-y, .bch-x, .ov-cap';
const refAxis = el => !!(el && el.matches && (el.matches(REF_AXIS) || (/^tspan$/i.test(el.tagName) && el.parentElement && el.parentElement.matches(REF_AXIS))));          // the label itself (not a box around the chart)
function refFig(tg, card) {
  let hit = tg.closest('[data-cftip], [data-reftip]'), tip = hit && card.contains(hit) ? refTip(hit) : null;
  let val = [tg, tg.parentElement].find(el => el && el !== card && card.contains(el) && !refAxis(el) && !el.closest('button, .seg, select, label.chk') && refIsNum(refOne(el.textContent))) || null;          // a control (6 M, 1 J): no figure
  if (!tip && val && val.classList.contains('cf-val-l')) {          // the label of a bar cut at the scale: its month is the hit area at the same place
    const b = val.getBoundingClientRect(), mx = (b.left + b.right) / 2, svg = val.closest('svg');
    hit = svg ? [...svg.querySelectorAll('[data-cftip]')].find(x => { const r = x.getBoundingClientRect(); return mx >= r.left && mx <= r.right; }) || null : null;
    tip = hit ? refTip(hit) : null;
  }
  const svg = hit && hit.closest('svg');
  if (!val && hit && svg) {          // a row of a drawn chart (its hit area over the texts): its own figure first, else the figure in the same band
    const r = hit.getBoundingClientRect();
    val = [...hit.querySelectorAll('text')].find(x => !refAxis(x) && refIsNum(refOne(x.textContent))) || [...svg.querySelectorAll('text')].find(x => { const b = x.getBoundingClientRect(), my = (b.top + b.bottom) / 2, mx = (b.left + b.right) / 2;
      return my >= r.top && my <= r.bottom && mx >= r.left && mx <= r.right && !refAxis(x) && refIsNum(refOne(x.textContent)); }) || null;          // inside its area (not an axis)
  }
  if (!tip && !val) return null;
  const value = val ? refOne(val.textContent) : '', title = refChartTitle(card) || refTitle(card), more = [];
  let label = tip && tip.head;
  if (val && val.classList.contains('cf-heat-v')) {          // the average (or the change) at the end of a row of the monthly strips: that row's, named by its column
    let n = val.previousElementSibling; while (n && !n.classList.contains('cf-heat-n')) n = n.previousElementSibling;
    const col = $('.cf-heat-avg', card); label = [n ? refLabel(n) : '', col ? col.title : ''].filter(Boolean).join(' · ');
  }
  if (val && val.classList.contains('cf-val-l')) more.push(t('ref_balken_gesamt'));          // the label of a bar cut at the scale
  const head = $('.ov-head, .lc-head, .bch-head', card), hc = head && head.cloneNode(true);
  if (hc) hc.querySelectorAll('button, .seg, select, label.chk, .hq').forEach(x => x.remove());          // its figures and period, not its controls
  const headTxt = hc ? refCut(refOne(hc.textContent), 300) : '';
  if (headTxt && headTxt !== title) more.push(`${t('ref_karte')}: ${headTxt}`);          // the card's own figures and period (62.533 € Okt 26 · 12 Monate +15.860 €)
  if (!label && val) {          // the text beside it: in its row, else (a figure in a card's head) the card's name
    const row = val.closest('[data-cftip]') || (val.closest('.ov-head, .lc-head, .bch-head, .lc-row2') ? null : val.parentElement);
    label = (row && row !== card && refLeaves(row).map(x => refLabel(x)).find(x => x && !refIsNum(x))) || title;
  }
  // which of the hover box's figures it is (Betrag, Anteil, Veränderung ...): named beside it, so a share or a change is not taken for an amount
  // -- each part of a label on its own (17.400 ±0 %: the amount, then its change), also when it is short (420T €) or signed
  // otherwise (expenses shown positive); a change in brackets behind a line names that line ("Okt 26: 420.000 € (+2,3 %)")
  const tipKv = tip ? tip.text.split(' · ').flatMap(l => { const i = l.indexOf(': '); if (i < 1) return []; const k = l.slice(0, i), rest = l.slice(i + 2), br = rest.match(/\(([^()]*)\)\s*$/);
    return [[k, refQty(rest.replace(/\s*\([^()]*\)\s*$/, ''))]].concat(br ? [[t('ref_veraenderung_zu', k), refQty(br[1])]] : []); }).filter(([, q]) => q) : [];
  const parts = val ? [...val.childNodes].map(c => refOne(c.textContent)).filter(Boolean) : [];
  const named = (parts.length > 1 ? parts : [value]).map(v => { const q = refQty(v), k = q && tipKv.find(([, x]) => refSameQty(q, x)); return k ? `${v} (${k[0]})` : v; }).join(' ');
  return Object.assign(refMake(label && value ? `${label}: ${value}` : title && label && label !== title ? `${title} · ${label}` : label || value, [`${t('ref_zeile')}: ${label || '–'}`].concat(value ? [`${t('ref_wert')}: ${named}`] : [], tip ? [`${t('ref_punkt')}: ${tip.text}`] : [], more),
    title, refGo({mark: title && !card.closest('#drawer') ? {text: title, column: ''} : null, fig: {tip: tip ? tip.head : '', label: label || '', value}})), value ? {copy: refNum(value), copyKey: 'wert_kopieren'} : {});
}
function refMarkFig(fig) {          // the figure itself, in its marked card (or anywhere on the page): marked, with its hover box
  const card = $('#main .as-mark') && $('#main .as-mark').matches('.card, .module, fieldset') ? $('#main .as-mark') : $('#main');
  let el = fig.tip ? [...card.querySelectorAll('[data-cftip]')].find(x => refSeen(x) && asNorm((refTip(x) || {}).head) === asNorm(fig.tip)) : null;
  if (!el && fig.value) {
    const all = refLeaves(card).filter(x => refSeen(x) && refOne(x.textContent) === fig.value);
    el = all.find(x => !fig.label || asNorm(((x.closest('[data-cftip]') || x.parentElement || x).textContent)).includes(asNorm(fig.label))) || all[0] || null;
  }
  if (!el) return false;
  $$('.as-mark, .as-mark-svg').forEach(x => x.classList.remove('as-mark', 'as-mark-svg')); clearTimeout(AS.markT);
  el.classList.add(el instanceof SVGElement ? 'as-mark-svg' : 'as-mark');
  el.scrollIntoView({block: 'center', inline: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
  if (el.dataset.cftip != null) setTimeout(() => cfShowTip(el), 400);
  AS.markT = setTimeout(() => $$('.as-mark, .as-mark-svg').forEach(x => x.classList.remove('as-mark', 'as-mark-svg')), 12000);
  return true;
}
// which places a right click is in -- the keys of Kontor's description of its pages (docs/ui, data-ex): the innermost first, the page
// last; the assistant is given what they show (what each figure there is)
function refPlaces(el) {
  const out = [];
  for (let x = el; x && x !== document.body; x = x.parentElement) { const k = x.dataset && x.dataset.ex; if (k && !out.includes(k)) out.push(k); }
  if (S.tab && !out.includes(S.tab)) out.push(S.tab);
  return out.slice(0, 8);
}
function refAt(e) {          // what the right click is on, as a reference (also without the assistant: for copying)
  const r = refFind(e);
  if (!r) return r;
  if (!r.ex) r.ex = refPlaces(e.target);
  const per = refPeriod(e.target); if (per) r.text = (r.text + '\n' + per).slice(0, 1500);
  return r;
}
// the period a chart below the cash flow table shows (chosen above them) and the months it is compared with -- not on the screen
// beside each figure, so said with it
function refPeriod(el) {
  const D = S.tab === 'cashflow' && el.closest('#main .cf-card') ? B() : null; if (!D) return '';
  const [cur, prev] = cfMonths(D, S.cfZeit); if (!cur || !cur.length) return '';
  return `${t('ref_zeitraum')}: ${cfSpanLabel(cur)} (${spanText(cur.length)})` + (prev && prev.length ? ` · ${t('ref_vergleich')}: ${cfSpanLabel(prev)}` : '');
}
function refFind(e) {
  const tg = e.target, chat = tg.closest('#assist .as-chart');
  if (chat) return refChat(chat);
  const main = $('#main'), dr = $('#drawer');
  if (AS_HIDDEN.includes(S.tab) || !(main.contains(tg) || dr.classList.contains('open') && dr.contains(tg))) return null;
  // a text the user selected before the click, and the click is on it: that text (several cells, a column dragged over). Never the
  // word Safari and the Mac app select under the pointer with the right click itself (REFSEL: what was selected before it), and never
  // a selection inside one cell or one label -- that is the cell or the figure, with its row, column and what the place shows
  const sel = getSelection(), st = sel && !sel.isCollapsed && REFSEL.text && sel.toString() === REFSEL.text ? sel.toString().trim() : '';
  if (st && sel.rangeCount) {
    const r = sel.getRangeAt(0), on = [...r.getClientRects()].some(x => e.clientX >= x.left - 4 && e.clientX <= x.right + 4 && e.clientY >= x.top - 4 && e.clientY <= x.bottom + 4);
    const box = r.commonAncestorContainer.nodeType === 1 ? r.commonAncestorContainer : r.commonAncestorContainer.parentElement;
    if ((on || r.intersectsNode(tg)) && (main.contains(box) || dr.contains(box)) && !box.closest('td, th, text, .kpi, .lc-val, .ov-fig, li')) {
      const where = refTitle(box);
      return Object.assign(refMake(`„${refCut(refOne(st), 40)}“`, [`${t('ref_auswahl')}:`, st.slice(0, 1200)], where, refGo(where && !box.closest('#drawer') ? {mark: {text: where, column: ''}} : {})), {copy: st});
    }
  }
  const cell = tg.closest('td, th');
  if (cell && cell.closest('table')) { const r = refCell(cell); if (r) return r; }
  const whole = tg.closest(REF_CHARTS), part = whole && tg.closest('.cf-duo-p, .cf-duo-h'), chart = part && whole.contains(part) ? part : whole;          // a card of two charts: the one clicked, by its own title
  if (chart) {          // a chart: the figure or row under the pointer; else the point (what its hover box shows) and what the chart shows
    const f = !chart.closest('#assist') && refFig(tg, chart); if (f) return f;
    const ti = refChartTitle(chart) || refTitle(chart), pt = refPoint(chart);
    return refMake(t('ki_ref_grafik', ti || t('ref_grafik')) + (pt ? ' · ' + pt.head : ''), [`${t('ref_grafik')}: ${ti}`].concat(pt ? [`${t('ref_punkt')}: ${pt.text}`] : [], [`${t('ref_inhalt')}: ${refTxt(chart, 1000)}`]),
      '', refGo(ti && !chart.closest('#drawer') ? {mark: {text: ti, column: ''}} : {}));
  }
  const mf = tg.closest('#drawer #h-grid label'), mi = mf && $('input', mf);
  if (mi) {          // one month's balance in an account's history: that month and its value -- typed in (your own) or Kontor's (grey)
    const acct = refLabel($('#drawer > h2')), mon = refOne(mf.firstChild ? mf.firstChild.textContent : ''), v = mi.value.trim() || mi.placeholder || '';
    const src = mi.value.trim() ? t('ref_eigener_stand') : v ? (mf.title || t('ref_von_kontor')) : t('unbekannt');
    return refMake(`${acct} · ${mon}: ${v || t('unbekannt')}`, [`${t('ref_zeile')}: ${acct}`, `${t('ref_spalte')}: ${mon}`, `${t('ref_wert')}: ${v || t('unbekannt')} (${src})`], acct, refGo({}));
  }
  const box = tg.closest('.k, .kpi, li, .item, .ov-todo-i, .lc-val, .card, .co-card, #drawer');
  if (!box) return null;
  const inCard = tg.closest('.card, .co-card, #drawer'), f = inCard && refFig(tg, inCard); if (f) return f;          // a figure in a card
  const where = refTitle(box), what = box.matches('.card, .co-card, #drawer') ? where : refLabel(box);
  if (!what) return null;
  const fields = [...box.querySelectorAll('#h-grid label')].map(l => { const i = $('input', l); if (!i) return ''; const v = i.value.trim() || i.placeholder || '';          // a month's balance: typed in, or what Kontor has (grey)
    return v ? `${refOne(l.firstChild ? l.firstChild.textContent : '')}: ${v}${i.value.trim() ? '' : ' (' + t('ref_von_kontor') + ')'}` : ''; }).filter(Boolean);
  return refMake(what, [refTxt(box, fields.length ? 400 : 1200)].concat(fields.length ? [`${t('ref_werte')}:`].concat(fields.slice(-36)) : []), where && where !== what ? where : '', refGo(where && !box.closest('#drawer') ? {mark: {text: where, column: ''}} : {}));
}
function asAskAbout(ref) {
  AS.refs = (AS.refs || []).filter(r => r.label !== ref.label || r.page !== ref.page).concat([ref]).slice(-REF_MAX);
  if (S.tab !== 'assistant' && !AS.open) asShow(true); else asLayout();
  asRefsDraw(); const ta = $('#as-in'); if (ta) ta.focus();
}
// A quick explanation: asked at once (without thinking, read-only, not in the chat), answered in a small box at the pointer --
// "in the chat" takes it there (the reference with what was explained) for a question of one's own.
const QK = {job: null, box: null};
function asQuickClose() {
  if (QK.job) { const j = QK.job; QK.job = null; if (j !== 'asking') api('/api/assistant/stop', {}).catch(() => {}); }
  if (QK.box) { QK.box.remove(); QK.box = null; }
  document.removeEventListener('pointerdown', asQuickAway, true); document.removeEventListener('keydown', asQuickKey, true);
}
const asQuickAway = e => { if (QK.box && !QK.box.contains(e.target)) asQuickClose(); };
const asQuickKey = e => { if (e.key === 'Escape') asQuickClose(); };
async function asQuick(ref, x, y) {
  asQuickClose();
  const box = QK.box = document.createElement('div'); box.className = 'as-pop'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', t('ki_kurz'));
  box.innerHTML = `<div class="as-pop-h"><span class="as-ref"><span class="as-ref-go"><span class="as-ref-pg">${esc(ref.page)}</span><span class="as-ref-l">${esc(ref.label)}</span></span></span><button type="button" class="icon as-pop-x" title="${esc(t('ki_schliessen'))}" aria-label="${esc(t('ki_schliessen'))}">${AS_CROSS}</button></div>`
    + `<div class="as-pop-b" aria-live="polite"><div class="as-run"><span class="spin"></span>${esc(t('ki_denkt'))}</div></div>`
    + `<div class="as-pop-f"><button type="button" class="ghost small as-pop-chat">${esc(t('ki_im_chat_weiter'))}</button></div>`;
  document.body.appendChild(box);
  const place = () => { const r = box.getBoundingClientRect(); box.style.left = Math.max(8, Math.min(x, innerWidth - r.width - 8)) + 'px'; box.style.top = Math.max(8, Math.min(y + 4, innerHeight - r.height - 8)) + 'px'; };
  place();
  document.addEventListener('pointerdown', asQuickAway, true); document.addEventListener('keydown', asQuickKey, true);
  let text = '';
  const body = () => $('.as-pop-b', box), show = (h) => { if (QK.box === box) { body().innerHTML = h; place(); } };
  $('.as-pop-x', box).addEventListener('click', asQuickClose);
  $('.as-pop-chat', box).addEventListener('click', () => {
    const said = text.trim(); asQuickClose();
    asAskAbout(said ? Object.assign({}, ref, {text: (ref.text + '\n' + t('ki_kurz_erklaert') + ': ' + said).slice(0, 1500)}) : ref);
  });
  try {
    QK.job = 'asking';
    const r = await api('/api/assistant/ask', {question: t('ki_kurz_frage'), quick: true, page: asPage(), refs: [refSend(ref)]});
    if (QK.box !== box) { api('/api/assistant/stop', {}).catch(() => {}); return; }          // closed meanwhile: not answered for nobody
    QK.job = r.job;
    let n = 0, cut = false;
    while (QK.job === r.job) {
      const p = await api(`/api/assistant/poll?job=${r.job}&after=${n}`);
      for (const ev of p.events || []) {
        n = Math.max(n, ev.n || 0);
        if (ev.type === 'delta') text += ev.text || '';
        else if (ev.type === 'reset') text = '';
        else if (ev.type === 'status' && ev.state === 'loading' && !text) show(`<div class="as-run"><span class="spin"></span>${esc(t('ki_laedt_modell'))}</div>`);
        else if (ev.type === 'error') throw new Error(ev.text || '');
        else if (ev.type === 'done') cut = !!ev.cut;
      }
      if (cut && text.trim() && !/[.!?…]\s*$/.test(text)) text = text.trimEnd() + ' …';          // the short limit reached in the middle of a sentence
      if (text.trim()) show(`<div class="as-t">${asMd(text)}</div>`);
      if (p.done || p.gone) break;
    }
    if (QK.box === box && !text.trim()) show(`<div class="muted small">${esc(t('ki_gestoppt'))}</div>`);
  } catch (e) { show(`<div class="banner err small">${esc(e.message)}</div>`); }
  if (QK.box === box) QK.job = null;
}
const asRefChip = (r, attrs, x) => `<span class="as-ref"><button type="button" class="as-ref-go" ${attrs} title="${esc(r.go ? t('ki_ref_springen') + '\n\n' + r.text : r.text)}">`
  + `${r.page ? `<span class="as-ref-pg">${esc(r.page)}</span>` : ''}<span class="as-ref-l">${esc(r.label)}</span></button>`
  + (x ? `<button type="button" class="as-ref-x" ${attrs} title="${esc(t('ki_ref_weg'))}" aria-label="${esc(t('ki_ref_weg'))}">${AS_CROSS}</button>` : '') + '</span>';
function asRefsDraw() {
  const box = $('#as-refs'); if (!box) return;
  const refs = AS.refs || [], files = AS.files || [];
  box.innerHTML = refs.map((r, i) => asRefChip(r, `data-r="${i}"`, true)).join('') + files.map((f, i) => asFileChip(f.name, i)).join(''); box.classList.toggle('hidden', !refs.length && !files.length);
}
function refMarkCol(col) {          // a column by its heading: the heading and its figures marked
  const want = asNorm(col);
  for (const tbl of $$('#main table')) {
    const head = tbl.tHead && tbl.tHead.rows.length ? tbl.tHead.rows[tbl.tHead.rows.length - 1] : tbl.rows[0];
    const h = head && [...head.cells].find(c => refSeen(c) && asNorm(refLabel(c)) === want); if (!h) continue;
    $$('.as-mark').forEach(x => x.classList.remove('as-mark')); clearTimeout(AS.markT);
    h.classList.add('as-mark'); [...tbl.tBodies].flatMap(b => [...b.rows]).forEach(r => { const c = [...r.cells].find(x => refOver(x, h)); if (c) c.classList.add('as-mark'); });
    h.scrollIntoView({block: 'nearest', inline: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
    AS.markT = setTimeout(() => $$('.as-mark').forEach(x => x.classList.remove('as-mark')), 12000);
    return true;
  }
  return false;
}
async function asRefOpen(r) {
  const g = r && r.go; if (!g || !/^#[\w/-]+$/.test(g.route || '')) return;
  if (matchMedia('(max-width: 900px)').matches && S.tab !== 'assistant') asShow(false);          // the panel covers the page there: it steps aside
  else if (matchMedia('(max-width: 900px)').matches) { AS.open = false; try { LS.set('kontor.assist', ''); } catch (e) {} }
  const res = await asOpen(Object.assign({}, g, {mark: g.mark && g.mark.text ? g.mark : null, fig: undefined}));
  let found = !g.mark || !!(res && res.found);
  if (g.col) { await asDrawnWait(); found = refMarkCol(g.col); }
  if (g.fig && (g.fig.tip || g.fig.value)) { await asDrawnWait(); found = refMarkFig(g.fig) || found; }
  if (!found) toast(t('ki_ref_nicht_gefunden'), 4000);
}
function asStop() { api('/api/assistant/stop', {}).catch(() => {}); }
async function asNew() { if (AS.busy) asStop(); AS.job = null; AS.busy = false; AS.msgs = []; AS.conv = ''; AS.list = false; AS.hover = AS.sel = null; asHead(); asMsgs(true); try { await api('/api/assistant/reset', {}); } catch (e) {} }
// Saved conversations (Verläufe): kept by Kontor, encrypted, while the setting is on -- opened again here, and they go on where they stood
async function asHist(open) {
  AS.list = !!open; AS.hover = AS.sel = null;
  if (open) { AS.chats = null; AS.histN = 100; asHead(); asMsgs(true);
    try { const r = await api('/api/assistant/chats'); AS.chats = r.chats || []; AS.save = r.save !== false; } catch (e) { AS.chats = []; toast(e.message, 5000); } }
  asHead(); asMsgs(true);
}
function asHistDraw() {
  const L = AS.chats;
  if (L == null) return `<div class="as-run"><span class="spin"></span>${t('wird_geladen')}</div>`;
  const when = s => (s || '').slice(0, 10) === isoToday() ? s.slice(11, 16) : FD(s);
  const item = c => `<div class="as-hi${c.id === AS.conv ? ' on' : ''}"><button type="button" class="as-hi-open" data-id="${esc(c.id)}"><span class="as-hi-t">${esc(c.title || '…')}</span>`
    + `<span class="as-hi-m">${esc(when(c.updated))} · ${t(c.questions === 1 ? 'ki_verlauf_frage1' : 'ki_verlauf_fragen', c.questions)}</span></button>`
    + `<button type="button" class="icon as-hi-del" data-id="${esc(c.id)}" title="${esc(t('ki_verlauf_loeschen'))}" aria-label="${esc(t('ki_verlauf_loeschen'))}">${ICON.trash}</button></div>`;
  return `<div class="as-hist" data-ex="assistant.history"><div class="as-hist-h"><b>${t('ki_verlaeufe')}</b>${L.length ? `<button type="button" class="ghost small as-hi-all">${t('ki_verlaeufe_alle_loeschen')}</button>` : ''}</div>`
    + (AS.save ? '' : `<div class="muted small as-hist-off">${t('ki_verlaeufe_aus')}</div>`)
    + (L.length ? L.slice(0, AS.histN || 100).map(item).join('') : `<div class="as-empty muted small">${t('ki_verlaeufe_leer')}</div>`)
    + (L.length > (AS.histN || 100) ? `<button type="button" class="ghost small as-hi-more">${esc(t('ki_verlaeufe_mehr', asN(L.length - (AS.histN || 100))))}</button>` : '') + `</div>`;
}
async function asOpenChat(id) {
  try {
    const r = await api('/api/assistant/chat?id=' + encodeURIComponent(id));
    if (AS.busy) asStop();
    Object.assign(AS, {job: null, busy: false, conv: r.id, list: false, hover: null, sel: null, msgs: (r.turns || []).map(m => m.role === 'user' ? Object.assign({role: 'user', text: String(m.text || '')}, Array.isArray(m.refs) && m.refs.length ? {refs: m.refs} : {}, Array.isArray(m.files) && m.files.length ? {files: m.files} : {}) : Object.assign({}, m, {parts: m.parts || []}))});          // a question with files: their names (a file alone has no text)
    asHead(); asMsgs(true);
  } catch (e) { toast(e.message, 5000); asHist(true); }
}
async function asDelChats(id) {
  const all = !id, c = (AS.chats || []).find(x => x.id === id);
  if (!confirm(all ? t('ki_verlaeufe_alle_frage') : t('ki_verlauf_frage', (c && c.title) || ''))) return;
  try {
    await api('/api/assistant/chats/delete', all ? {all: true} : {id});
    if (AS.conv && (all ? (AS.chats || []).some(x => x.id === AS.conv) : id === AS.conv)) { if (AS.busy) asStop(); Object.assign(AS, {job: null, busy: false, msgs: [], conv: ''}); }
  } catch (e) { toast(e.message, 6000); }
  if (AS.list) asHist(true);
}
$('#assist-btn').addEventListener('click', () => { if (S.tab !== 'assistant') asShow(!AS.open); });
$('#assist').addEventListener('click', async e => {
  const b = e.target.closest('button, a'); if (!b) return;
  if (b.classList.contains('as-ref-x')) { if (b.dataset.f != null) (AS.files || []).splice(+b.dataset.f, 1); else (AS.refs || []).splice(+b.dataset.r, 1); asRefsDraw(); const ta = $('#as-in'); if (ta) ta.focus(); }
  else if (b.classList.contains('as-ref-go')) asRefOpen(b.dataset.m != null ? ((AS.msgs[+b.dataset.m] || {}).refs || [])[+b.dataset.r] : (AS.refs || [])[+b.dataset.r]);
  else if (b.classList.contains('as-close')) asShow(false);
  else if (b.classList.contains('as-new')) asNew();
  else if (b.classList.contains('as-hist-btn')) asHist(!AS.list);
  else if (b.classList.contains('as-hi-open')) asOpenChat(b.dataset.id);
  else if (b.classList.contains('as-hi-del')) asDelChats(b.dataset.id);
  else if (b.classList.contains('as-hi-all')) asDelChats('');
  else if (b.classList.contains('as-hi-more')) { AS.histN = (AS.histN || 100) + 100; asMsgs(); }
  else if (b.classList.contains('as-ch-open')) { const h = asChFrom(b); if (h) asChGo(h.c, -1, 0); }
  else if (b.classList.contains('as-big')) { if (S.tab === 'assistant') { AS.open = true; try { LS.set('kontor.assist', '1'); } catch (x) {} go(AS.prev || '#overview'); } else go('#assistant'); }
  else if (b.classList.contains('as-sug')) asSend(b.textContent);
  else if (b.classList.contains('as-do')) { const it = (AS.open_items || [])[+b.dataset.i]; if (it) asSend(t(`ki_do_${it[3]}`)); }
  else if (b.classList.contains('as-copy')) { try { await navigator.clipboard.writeText(b.parentNode.querySelector('pre').textContent); b.textContent = t('ki_kopiert'); setTimeout(() => { b.textContent = t('ki_kopieren'); }, 1500); } catch (x) {} }
  else if (b.classList.contains('as-b-yes') || b.classList.contains('as-b-no')) {
    b.parentNode.querySelectorAll('button').forEach(x => { x.disabled = true; });
    const card = AS.msgs.flatMap(m => (m.parts || []).filter(y => y.k === 'batch' && y.id === b.dataset.id).map(y => [m, y]))[0];
    const ids = card ? card[0].parts.filter(y => y.k === 'entry' && (card[1].ids || []).includes(y.id) && !y.off).map(y => y.id) : [];
    try { await api('/api/assistant/confirm', {job: AS.job, id: b.dataset.id, ok: b.classList.contains('as-b-yes'), ids}); }
    catch (x) { toast(x.message, 5000); if (card && !AS.job) { card[1].state = 'declined'; card[0].parts.forEach(y => { if (y.k === 'entry' && y.state === 'queued') y.state = 'declined'; }); } asMsgs(); }
  } else if (b.classList.contains('as-w-yes') || b.classList.contains('as-w-no')) {
    b.parentNode.querySelectorAll('button').forEach(x => { x.disabled = true; });
    const card = AS.msgs.flatMap(m => m.parts || []).find(y => y.k === 'web' && y.id === b.dataset.id);
    try { await api('/api/assistant/confirm', {job: AS.job, id: b.dataset.id, ok: b.classList.contains('as-w-yes'), ids: card ? asWebItems(card).filter(it => !it.off).map(it => it.id) : undefined}); }
    catch (x) { toast(x.message, 5000); if (card && !AS.job) asWebState(card, {state: 'declined'}); asMsgs(); }
  } else if (b.classList.contains('as-m-undo') || b.classList.contains('as-m-yes') || b.classList.contains('as-m-no')) {          // a note under an answer: taken back or brought back, kept or not
    b.disabled = true;
    const p = AS.msgs.flatMap(m => m.parts || []).find(y => y.k === 'memory' && y.id === b.dataset.id);
    try {
      const r = b.classList.contains('as-m-undo') ? await api('/api/assistant/memory/undo', {id: b.dataset.id}) : await api('/api/assistant/memory/offer', {id: b.dataset.id, ok: b.classList.contains('as-m-yes')});
      if (p) { p.state = r.state; if (r.id) p.id = r.id; if (r.state === 'undone' || r.state === 'declined') p.text = ''; }
      asMsgs();
    } catch (x) { toast(x.message, 6000); b.disabled = false; }
  } else if (b.classList.contains('as-undo')) {
    b.disabled = true;
    try { const r = await api('/api/assistant/undo', {id: b.dataset.id}); const p = AS.msgs.flatMap(m => m.parts || []).find(y => y.k === 'entry' && y.id === b.dataset.id); if (p) { p.state = 'undone'; p.text = r.note || ''; } asMsgs(); asChanged(); }
    catch (x) { toast(x.message, 6000); b.disabled = false; }
  }
});
$('#assist').addEventListener('change', e => {
  if (e.target.id === 'as-eff') { AS.effort = e.target.value; try { LS.set('kontor.effort', AS.effort); } catch (x) { /* kept in memory only */ } }
  else if (e.target.classList.contains('as-w-tick')) { const p = AS.msgs.flatMap(m => m.parts || []).find(y => y.k === 'web' && y.id === e.target.dataset.id), it = p && asWebItems(p).find(y => y.id === e.target.dataset.item); if (it) { it.off = !e.target.checked; asMsgs(); } }          // left out: not fetched
  else if (e.target.classList.contains('as-pick')) { const p = AS.msgs.flatMap(m => m.parts || []).find(y => y.k === 'entry' && y.id === e.target.dataset.id); if (p) { p.off = !e.target.checked; asMsgs(); } }          // left out: not carried out
});
// the charts in the chat: values under the pointer, a click to the page (a touch: shown first, the second tap goes)
$('#assist').addEventListener('pointerdown', e => {
  AS.ptr = e.pointerType;
  if (AS.sel && !(e.target.closest && e.target.closest('.as-ch-svg'))) { asChHide($(`#as-body .as-chart[data-c="${AS.sel.key}"]`)); AS.sel = null; }
});
$('#assist').addEventListener('pointermove', e => {
  const svg = e.target.closest && e.target.closest('.as-ch-svg'); if (!svg || e.pointerType === 'touch') return;
  const h = asChAt(svg, e);
  if (!h) { AS.hover = null; if (!AS.sel) asChHide(svg.closest('.as-chart')); return; }
  AS.sel = null; AS.hover = {key: h.key, i: h.i, s: h.s}; asChTip(h, false);
});
$('#assist').addEventListener('pointerout', e => {
  const svg = e.target.closest && e.target.closest('.as-ch-svg'); if (!svg || (e.relatedTarget && svg.contains(e.relatedTarget)) || AS.sel) return;
  AS.hover = null; asChHide(svg.closest('.as-chart'));
});
$('#assist').addEventListener('click', e => {
  const svg = e.target.closest && e.target.closest('.as-ch-svg'); if (!svg) return;
  const h = asChAt(svg, e); if (!h) return;
  if (AS.ptr === 'touch' || !matchMedia('(hover: hover)').matches) {
    const s = AS.sel; if (!s || s.key !== h.key || s.i !== h.i || s.s !== h.s) { AS.sel = {key: h.key, i: h.i, s: h.s}; asChTip(h, true); return; }
  }
  asChGo(h.c, h.i, h.s);
});
// thoughts folded or unfolded at once on the click -- also while the answer still streams in: the entry is drawn anew with every
// word, so the browser's own toggle (it comes a moment later) would land on an entry no longer there
$('#assist').addEventListener('click', e => {
  const sm = e.target.closest && e.target.closest('details.as-think > summary'); if (!sm) return;
  const d = sm.parentElement, p = ((AS.msgs[+d.dataset.m] || {}).parts || [])[+d.dataset.p]; if (!p) return;
  e.preventDefault(); p.open = !d.open; d.open = p.open;
});
$('#assist').addEventListener('toggle', e => {
  const d = e.target; if (!d.classList) return;
  if (d.classList.contains('as-e-more')) { const y = AS.msgs.flatMap(m => m.parts || []).find(x => x.k === 'entry' && x.id === d.dataset.id); if (y) y.more = d.open; return; }          // all bookings of a card: stay unfolded
  const p = ((AS.msgs[+d.dataset.m] || {}).parts || [])[+d.dataset.p]; if (!p) return;
  if (d.classList.contains('as-think')) p.open = d.open;
  else if (d.classList.contains('as-w-d')) { const it = asWebItems(p).find(x => String(x.id || '') === d.dataset.i); if (it) it.open = d.open; }          // a request's address and what is sent: stays open while the answer goes on
}, true);
window.addEventListener('resize', () => { if (S.tab === 'assistant') asLayout(); });
function vAssistent() {
  // the conversation as a page: the panel itself fills the page (one conversation, wherever it is shown)
  return asOn() ? '<div class="as-space"></div>'
    : `<div class="note">${t('ki_einrichten')} ${(AS.st || {}).local === false ? t('ki_nur_am_mac') : `<a href="#settings/assistant">${t('ki_zu_einstellungen')}</a>`}</div>`;
}
// Einstellungen -> Assistent (only at the Mac): load and update llama.cpp and models, choose, start, stop, what it may do
async function vEinstellungenAssistent() {
  const a = await asLoad() || {}, st = a.settings || {}, r = st.rights || {};
  if (!a.local) return `<div class="note" data-ex="settings.assistant">${t('ki_nur_am_mac')}</div>`;
  const rt = a.runtime || {}, sv = a.server || {}, pf = a.platform || {}, load = a.load && a.load.state === 'running' ? a.load : null, models = a.models || [];
  const busy = load || a.updating ? 'disabled' : '';
  const ears = new Set((a.speech || []).map(m => m.id)), finds = new Set((a.embed || []).map(m => m.id)), part = l => l ? (l.kind === 'model' && ears.has(l.id) ? 'speech' : l.kind === 'model' && finds.has(l.id) ? 'embed' : l.kind) : '';
  const prog = k => part(load) === k ? `<div class="prog-wrap" id="as-prog"><div class="prog"><i style="width:${load.total ? Math.round(100 * load.done / load.total) : 0}%"></i></div><span class="prog-l">${esc(asLoadText(load))}</span><button class="secondary small" id="as-cancel">${t('ki_abbrechen')}</button></div>` : '';
  const err = k => !load && a.load && a.load.state === 'error' && part(a.load) === k ? `<div class="banner err small">${esc(a.load.text || '')}</div>` : '';
  const fitTag = m => m.fit === 'big' ? `<span class="tag warn" title="${esc(t('ki_zu_gross_tip'))}">${t('ki_zu_gross')}</span>` : m.fit === 'tight' ? `<span class="tag warn" title="${esc(t('ki_knapp_tip'))}">${t('ki_knapp')}</span>` : '';
  const mrow = m => `<div class="as-item${m.id === st.model ? ' on' : ''}${m.fit === 'big' && !m.installed ? ' dim' : ''}"><label class="chk"><input type="radio" name="as-model" value="${esc(m.id)}" ${m.id === st.model ? 'checked' : ''} ${m.installed ? '' : 'disabled'}>
      <span><b>${esc(m.name)}</b>${m.note ? ` <span class="muted">${t(`ki_note_${m.note}`)}</span>` : ''}${m.id === a.recommended ? ` <span class="pill info">${t('ki_empfohlen')}</span>` : ''}${fitTag(m)}<br><span class="muted small">${esc(m.installed && !m.custom ? m.file : m.repo + (m.file ? ' · ' + m.file : ''))} · ${m.installed ? asGB(m.size) : t('ki_gb_ca', m.gb)}${m.ram ? ' · ' + t('ki_ab_ram', m.ram) : ''}</span></span></label>
    <span class="as-act">${m.newer ? `<span class="pill info">${t('ki_neuere_datei')}</span>` : m.installed ? `<span class="pill ok">${t('ki_geladen')}</span>` : ''}
      ${!m.installed || m.newer ? `<button class="small${m.installed || m.id !== a.recommended ? ' secondary' : ''} as-dl" data-id="${esc(m.id)}" data-name="${esc(m.name)}" data-fit="${m.fit || ''}" ${busy}>${t(m.installed ? 'ki_aktualisieren' : 'ki_laden')}</button>` : ''}
      ${m.installed ? `<button class="small secondary as-del" data-id="${esc(m.id)}" data-name="${esc(m.name)}" ${busy}>${t('ki_loeschen')}</button>` : ''}</span></div>`;
  const state = sv.state || 'stopped', opt = (v, l, cur) => `<option value="${v}" ${String(cur) === String(v) ? 'selected' : ''}>${l}</option>`;
  const use = sv.rss ? t('ki_verbrauch', asRAM(sv.rss), asN(sv.cpu || 0)) + (sv.tps ? ' · ' + t('ki_tempo', asN(sv.tps)) : '') : '';
  // under the internet's checkbox, while it is allowed: the Tavily key, what goes without asking (sources, websites)
  const wt = st.web_trusted || {};
  const webKey = r.internet ? `<div class="form as-web-key"><label for="as-tavily">${t('ki_tavily')}${hq('ki_tavily')}</label><div class="row tight">${(a.web || {}).tavily
    ? `<span class="muted small">${t('ki_tavily_da', a.web.tavily_used || 0, a.web.tavily_limit || 950, a.web.tavily_days || 31)}</span><button class="small secondary" id="as-tavily-del">${t('ki_entfernen')}</button>`
    : `<input type="password" id="as-tavily" placeholder="tvly-…" autocomplete="off" spellcheck="false"><button class="small secondary" id="as-tavily-save">${t('ki_tavily_sichern')}</button>${a.web
      ? `<span class="muted small">${t('ki_tavily_frei', a.web.tavily_used || 0, a.web.tavily_limit || 200, a.web.tavily_days || 31)}</span>` : ''}`}</div>
    <span class="as-wk-l">${t('ki_vertraut')}${hq('ki_vertraut')}</span><div class="as-trust">${((a.web || {}).sources || []).map(x => `<label class="chk"><input type="checkbox" class="as-trust-src" value="${esc(x.id)}" ${(wt.sources || []).includes(x.id) ? 'checked' : ''}> <span>${esc(x.label)}</span></label>`).join('')}</div>
    <label for="as-websites">${t('ki_websites')}${hq('ki_websites')}</label><input type="text" id="as-websites" value="${esc((wt.hosts || []).join(', '))}" placeholder="${esc(t('ki_websites_ph'))}" autocomplete="off" spellcheck="false" autocapitalize="off" inputmode="url"></div>` : '';
  return `<div data-ex="settings.assistant"><div class="row tight">${swCtl('as-enabled', st.enabled, t('ki_verwenden'))}${hq('assistent')}</div>
  <div data-ex="settings.assistant.program"><h2>${t('ki_programm')}${hq('ki_programm')}<span class="x">llama.cpp</span></h2>
  <div class="as-list"><div class="as-item"><span><b>llama.cpp</b><br><span class="muted small">${rt.installed ? esc(rt.tag || rt.version || '') + (rt.date ? ' · ' + esc(FDT(rt.date)) : '') : t('ki_nicht_installiert')}</span></span>
    <span class="as-act">${rt.newer ? `<span class="pill info">${t('ki_neuer', esc(rt.latest))}</span>` : ''}
      ${!rt.installed || rt.newer ? `<button class="small" id="as-rt-install" ${busy}>${t(rt.installed ? 'ki_aktualisieren' : 'ki_installieren')}</button>` : ''}
      ${rt.installed ? `<button class="small secondary" id="as-rt-remove" ${busy}>${t('ki_entfernen')}</button>` : ''}</span></div></div>
  ${prog('runtime')}${err('runtime')}
  </div><div data-ex="settings.assistant.models"><h2>${t('ki_modelle')}${hq('ki_modelle')}</h2>
  <div class="as-list">${models.map(mrow).join('')}
    <div class="as-item"><span class="as-own"><b>${t('ki_eigenes_modell')}</b>${hq('ki_eigenes')}<input type="text" id="as-repo" placeholder="unsloth/Qwen3.6-35B-A3B-GGUF" autocomplete="off" spellcheck="false"></span>
      <span class="as-act"><button class="small secondary" id="as-files" title="${esc(t('ki_dateien_zeigen_tip'))}" disabled>${t('ki_dateien_zeigen')}</button></span></div><div id="as-filelist"></div></div>
  ${prog('model')}${err('model')}
  </div><div data-ex="settings.assistant.dictation"><h2>${t('ki_diktat')}${hq('ki_diktat')}</h2>
  <div class="as-list">${(a.speech || []).map(m => `<div class="as-item${m.id === a.speech_in_use ? ' on' : ''}"><label class="chk"><input type="radio" name="as-speech" value="${esc(m.id)}" ${m.id === a.speech_in_use ? 'checked' : ''} ${m.installed ? '' : 'disabled'}>
      <span><b>${esc(m.name)}</b> <span class="muted">${t(`ki_note_${m.note}`)}</span><br><span class="muted small">${esc(m.installed ? m.file : m.repo)} · ${m.installed ? asGB(m.size) : t('ki_gb_ca', m.gb)}</span></span></label>
    <span class="as-act">${m.newer ? `<span class="pill info">${t('ki_neuere_datei')}</span>` : m.installed ? `<span class="pill ok">${t('ki_geladen')}</span>` : ''}
      ${!m.installed || m.newer ? `<button class="small secondary as-dl" data-id="${esc(m.id)}" data-name="${esc(m.name)}" data-fit="" ${busy}>${t(m.installed ? 'ki_aktualisieren' : 'ki_laden')}</button>` : ''}
      ${m.installed ? `<button class="small secondary as-del" data-id="${esc(m.id)}" data-name="${esc(m.name)}" ${busy}>${t('ki_loeschen')}</button>` : ''}</span></div>`).join('')}
    ${a.dictation ? `<div class="as-item"><span><b>${t('ki_sp_start')}</b>${hq('ki_sp_start')}</span><span class="as-act"><select id="as-speech-start" aria-label="${esc(t('ki_sp_start'))}">${opt('', t(a.speech_early_auto ? 'ki_sp_auto_early' : 'ki_sp_auto_click'), st.speech_start || '')}${opt('early', t('ki_sp_early'), st.speech_start || '')}${opt('click', t('ki_sp_click'), st.speech_start || '')}</select></span></div>
    <div class="as-item"><span><b>${t('ki_mikrofilter')}</b>${hq('ki_mikrofilter')}</span><span class="as-act"><select id="as-speech-filter" aria-label="${esc(t('ki_mikrofilter'))}">${opt('1', t('ki_mikrofilter_an'), st.speech_filter === false ? '0' : '1')}${opt('0', t('ki_mikrofilter_aus'), st.speech_filter === false ? '0' : '1')}</select></span></div>
    <div id="as-mic-perm"></div>` : ''}</div>
  ${prog('speech')}${err('speech')}
  </div><div data-ex="settings.assistant.meaning"><h2>${t('ki_bedeutung')}${hq('ki_bedeutung')}</h2>
  <div class="as-list">${(a.embed || []).map(m => `<div class="as-item${m.installed ? ' on' : ''}"><span><b>${esc(m.name)}</b> <span class="muted">${t(`ki_note_${m.note}`)}</span><br><span class="muted small">${esc(m.installed ? m.file : m.repo)} · ${m.installed ? asGB(m.size) : t('ki_gb_ca', m.gb)}</span></span>
    <span class="as-act">${m.newer ? `<span class="pill info">${t('ki_neuere_datei')}</span>` : m.installed ? `<span class="pill ok">${t('ki_geladen')}</span>` : ''}
      ${!m.installed || m.newer ? `<button class="small secondary as-dl" data-id="${esc(m.id)}" data-name="${esc(m.name)}" data-fit="" ${busy}>${t(m.installed ? 'ki_aktualisieren' : 'ki_laden')}</button>` : ''}
      ${m.installed ? `<button class="small secondary as-del" data-id="${esc(m.id)}" data-name="${esc(m.name)}" ${busy}>${t('ki_loeschen')}</button>` : ''}</span></div>`).join('')}</div>
  ${a.embed_state === 'error' && a.embed_error ? `<div class="banner err small">${esc(a.embed_error)}</div>` : ''}${prog('embed')}${err('embed')}
  </div><div data-ex="settings.assistant.updates"><h2>${t('ki_aktualisierung')}${hq('ki_auto_suchen')}</h2>
  <div class="form">
    <label>${t('ki_auto_suchen')}</label><label class="chk"><select id="as-check-mode">${[['daily', t('taeglich')], ['weekly', t('woechentlich')], ['monthly', t('monatlich')], ['aus', t('nie')]].map(([v, l]) => opt(v, l, st.check_mode)).join('')}</select></label>
    <label>${t('ki_zuletzt_gesucht')}</label><div class="row tight"><span class="muted small">${a.checked ? esc(FDT(a.checked)) : t('ki_noch_nie')}</span><button class="secondary small" id="as-check" ${busy}>${t('ki_nach_neuem_suchen')}</button>${((a.newer || {}).items || []).length ? `<button class="small" id="as-update-all" ${busy}>${t('ki_alles_aktualisieren')}</button>` : ''}</div>
    ${a.check_error ? `<div class="full banner err small">${esc(a.check_error)}</div>` : ''}
  </div>
  <h2>${t('ki_ablage')}${hq('ki_ablage')}</h2>
  <div class="row tight as-folder">${a.folder ? `<span class="mono small">${esc(a.folder)}</span><button class="small secondary" id="as-reveal" ${a.folder_exists ? '' : 'disabled'}>${t('im_finder_zeigen')}</button>` : ''}<span class="muted small">${t('ki_platz', asGB(a.disk_free || 0), asRAM(pf.ram || 0))}</span></div>
  </div><div data-ex="settings.assistant.operation"><h2>${t('ki_betrieb')}</h2>
  <div class="form">
    <label>${t('ki_zustand')}</label><div class="row tight as-run-row"><span class="pill ${state === 'ready' ? 'ok' : state === 'error' ? 'err' : state === 'starting' ? 'info' : 'neutral'}" id="as-state">${t(`ki_z_${state}`)}</span>
      ${state === 'ready' ? `<span class="tag${sv.sealed === 'strict' ? '' : ' warn'}" title="${esc(t(sv.sealed === 'strict' ? 'ki_abgeschirmt_tip' : sv.sealed ? 'ki_abgeschirmt_einfach_tip' : 'ki_nicht_abgeschirmt_tip'))}">${t(sv.sealed === 'strict' ? 'ki_abgeschirmt' : sv.sealed ? 'ki_abgeschirmt_einfach' : 'ki_nicht_abgeschirmt')}</span>` : ''}<span class="muted small" id="as-use">${esc(use)}</span>
      ${state === 'ready' || state === 'starting' ? `<button class="small secondary" id="as-stop">${t('ki_stoppen')}</button>` : `<button class="small secondary" id="as-start" ${st.enabled && a.ready ? '' : 'disabled'}>${t('ki_starten')}</button>`}</div>
    ${state === 'error' && sv.error ? `<div class="full banner err small">${esc(sv.error)}</div>` : ''}
    <label>${t('ki_kontext')}${hq('ki_kontext')}</label><label class="chk"><select id="as-context">${opt(0, t('ki_kontext_auto', a.context_auto_value / 1024), st.context_auto ? 0 : st.context)}${[16384, 32768, 65536, 131072].map(k => opt(k, t('ki_kontext_n', k / 1024), st.context_auto ? 0 : st.context)).join('')}</select></label>
    <label>${t('ki_leerlauf')}${hq('ki_leerlauf')}</label><label class="chk"><select id="as-idle">${[5, 10, 30, 60, 0].map(k => opt(k, k ? t('ki_leerlauf_n', k) : t('ki_leerlauf_nie'), st.idle_minutes)).join('')}</select></label>
    <label for="as-save">${t('ki_speichern')}${hq('ki_speichern')}</label><div class="row tight as-save-row"><label class="chk"><input type="checkbox" id="as-save" ${st.save_chats !== false ? 'checked' : ''} aria-label="${esc(t('ki_speichern'))}"></label>
      ${a.chats ? `<span class="small ${a.chats_many ? 'as-chats-many' : 'muted'}" id="as-chats-n"${a.chats_many ? ` title="${esc(t('ki_verlaeufe_viele'))}"` : ''}>${esc(tn('ki_verlaeufe_n', a.chats, asN(a.chats), (b => b < 1e6 ? Math.max(1, Math.round(b / 1e3)).toLocaleString(LOCALE) + ' KB' : asGB(b))(a.chats_bytes || 0)))}</span>` : ''}
      ${a.chats_old ? `<button class="small secondary" id="as-chats-old">${esc(t('ki_verlaeufe_alt_loeschen', asN(a.chats_old)))}</button>` : ''}
      <button class="small secondary" id="as-chats-del" ${a.chats ? '' : 'disabled'}>${t('ki_verlaeufe_alle_loeschen')}</button></div>
    ${pf.can_seal ? `<label>${t('ki_abschirmung')}${hq('ki_abschirmung')}</label><label class="chk"><select id="as-sandbox">${['strict', 'basic', 'off'].map(k => opt(k, t(`ki_sb_${k}`), st.sandbox)).join('')}</select></label>` : ''}
  </div>
  </div><div data-ex="settings.assistant.memory"><h2>${t('ki_gedaechtnis')}${hq('ki_gedaechtnis')}</h2>
  <div class="row tight">${swCtl('as-mem', st.memory !== false, t('ki_g_verwenden'))}<span class="muted small" id="as-mem-n"></span></div>
  <div class="as-mem"><div class="as-mem-bar"><input type="text" id="as-mem-new" maxlength="600" placeholder="${esc(t('ki_g_neu'))}" aria-label="${esc(t('ki_g_merken'))}" autocomplete="off" value="${esc(AS.memNew || '')}"><button class="small" id="as-mem-add" ${AS.memNew ? '' : 'disabled'}>${t('ki_g_merken')}</button></div>
    <div class="as-mem-bar"><input type="search" id="as-mem-q" placeholder="${esc(t('ki_g_suchen'))}" aria-label="${esc(t('ki_g_suchen'))}" value="${esc(AS.memQ || '')}"></div>
    <div id="as-mem-warn"></div>
    <div class="as-list" id="as-mem-list"><div class="as-item muted small"><span>${t('ki_laedt_kurz')}</span></div></div>
    <div class="row tight"><button class="small secondary" id="as-mem-all" disabled>${t('ki_g_alles_vergessen')}</button></div></div>
  </div><div data-ex="settings.assistant.rights"><h2>${t('ki_rechte')}</h2>
  <div class="as-rights">${[['ki_rg_lesen', ['read']], ['ki_rg_zeigen', ['navigate']], ['ki_rg_aendern', ['enter_values', 'categorize', 'book', 'rules', 'receipts']], ['ki_rg_zugang', ['remote']], ['ki_rg_internet', ['internet']]].map(([g, ks]) =>
    `<div class="as-rg"><div class="as-rg-h">${t(g)}${g === 'ki_rg_aendern' ? hq('ki_eintragen') : g === 'ki_rg_internet' ? hq('ki_internet') : ''}</div>${ks.map(k => `<label class="chk"><input type="checkbox" class="as-right" data-r="${k}" ${(k === 'read' ? r.figures && r.transactions && r.page : r[k]) ? 'checked' : ''}> <span>${t(`ki_r_${k}`)}</span></label>${k === 'internet' ? webKey : ''}`).join('')}</div>`).join('')}</div>
  <div class="note">${t('ki_nie')}${more('assistant-rights')}</div>
  </div><details class="as-log" id="as-log" data-ex="settings.assistant.changes"><summary>${t('ki_aenderungen')}</summary><div id="as-log-list" class="muted small">${t('ki_laedt_kurz')}</div></details></div>`;
}
// Einstellungen -> KI-Assistent -> Gedächtnis: what it was told to remember -- look, add, change, pin, forget (only at the Mac)
async function asMemLoad(body, more) {
  // body: a change (add, edit, pin, delete, forget_all) -- the list comes back with it; more: the next piece of a long list, appended
  if (!$('#as-mem-list')) return null;
  const had = ((AS.mem || {}).items || []).length, q = AS.memQ || '', n = Math.min(200, Math.max(50, more ? 100 : had));
  let r;
  try { r = body ? await api('/api/assistant/memory', Object.assign({q, limit: n}, body)) : await api(`/api/assistant/memory?q=${encodeURIComponent(q)}&limit=${n}${more ? '&offset=' + had : ''}`); }
  catch (e) { toast(e.message, 6000); return null; }
  if (more && AS.mem && q === (AS.memQ || '')) r.items = AS.mem.items.concat(r.items.filter(x => !AS.mem.items.some(y => y.id === x.id)));
  AS.mem = r; asMemDraw(); return r;
}
function asMemDraw() {
  const r = AS.mem, box = $('#as-mem-list'); if (!r || !box) return;
  const n = $('#as-mem-n'); if (n) n.textContent = r.notes ? tn('ki_g_n', r.notes, asN(r.notes)) + (r.pinned ? ' · ' + t('ki_g_angeheftet_n', asN(r.pinned)) : '') + (r.meaning && r.meaning.done < r.meaning.total ? ' · ' + t('ki_g_bedeutung_n', asN(r.meaning.done), asN(r.meaning.total)) : '') : '';
  const all = $('#as-mem-all'); if (all) all.disabled = !r.notes;
  const warn = $('#as-mem-warn'); if (warn) warn.innerHTML = (r.pinned_out ? `<div class="banner small">${esc(tn('ki_g_zu_viel', r.pinned_out, asN(r.pinned_out)))}</div>` : '') + (r.broken ? `<div class="banner err small">${esc(tn('ki_g_defekt', r.broken, asN(r.broken)))}</div>` : '');
  const some = r.profile < r.notes;          // not everything goes with every question: the notes that do say so
  const row = x => AS.memEdit === x.id
    ? `<div class="as-item as-mem-it edit" data-id="${esc(x.id)}"><textarea class="as-mem-ta" maxlength="${r.text_max}" rows="${Math.min(6, Math.max(2, Math.ceil(x.text.length / 80)))}" aria-label="${esc(t('ki_g_aendern'))}">${esc(AS.memDraft != null ? AS.memDraft : x.text)}</textarea><span class="as-act"><button class="small as-mem-ok">${t('ki_g_sichern')}</button><button class="small secondary as-mem-no">${t('ki_abbrechen')}</button></span></div>`
    : `<div class="as-item as-mem-it" data-id="${esc(x.id)}"><span class="as-mem-t">${esc(x.text)}<br><span class="muted small">${esc(FD(x.created))} · ${t(`ki_g_h_${x.how}`)}${some && x.profile ? ` · <span title="${esc(t('ki_g_steckbrief_tip'))}">${t('ki_g_steckbrief')}</span>` : ''}</span></span>
      <span class="as-act"><button type="button" class="icon as-mem-pin${x.pinned ? ' on' : ''}" aria-pressed="${x.pinned ? 'true' : 'false'}" title="${esc(t(x.pinned ? 'ki_g_loesen' : 'ki_g_anheften'))}" aria-label="${esc(t(x.pinned ? 'ki_g_loesen' : 'ki_g_anheften'))}">${ICON.pin}</button><button type="button" class="icon as-mem-edit" title="${esc(t('ki_g_aendern'))}" aria-label="${esc(t('ki_g_aendern'))}">${ICON.pencil}</button><button type="button" class="icon as-mem-del" title="${esc(t('ki_g_vergessen'))}" aria-label="${esc(t('ki_g_vergessen'))}">${ICON.trash}</button></span></div>`;
  box.innerHTML = r.items.length ? r.items.map(row).join('') + (r.total > r.items.length ? `<div class="as-item"><button type="button" class="ghost small" id="as-mem-more">${esc(t('ki_g_mehr', asN(r.total - r.items.length)))}</button></div>` : '')
    : `<div class="as-item muted small"><span>${t(AS.memQ ? 'ki_g_kein_treffer' : 'ki_g_leer')}</span></div>`;
  const ta = $('.as-mem-ta', box); if (ta) { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); } else if (AS.memEdit) { AS.memEdit = ''; AS.memDraft = null; }      // (the note being changed is no longer in the list)
}
async function asChangesLoad() {
  // the log of changes: what the assistant changed after the user's click, the latest first
  const el = $('#as-log-list'); if (!el) return;
  let r; try { r = await api('/api/assistant/changes'); } catch (x) { el.textContent = x.message; return; }
  const kind = k => asKind(k) || k || '';
  const list = r.changes || [];
  const mem = c => `<tr><td class="nowrap">${esc(FDT(c.time))}</td><td><b>${esc(t(`ki_a_g_${c.what}`))}</b>${c.title ? ' · ' + esc(c.title) : ''}${(c.what === 'forget_all' || c.what === 'backup') && c.count ? ' · ' + esc(tn('ki_g_n', c.count, asN(c.count))) : ''}${(c.rows || []).map(x => `<div class="muted small">${esc(t('ki_a_g_vorher', x.text || ''))}</div>`).join('')}</td><td>${c.by ? t(`ki_a_g_by_${c.by}`) : '–'}</td><td class="nowrap">${t('ki_e_done')}</td></tr>`;
  // each change as the card showed it (before and after, each booking), folded
  const num = (c, v) => v == null ? t('ki_e_leer') : c.kind === 'params' ? (+v).toLocaleString(LOCALE, {maximumFractionDigits: 2}) : fmt.format(v);
  const row = (c, r) => 'old_text' in r || 'new_text' in r ? `<tr><td>${esc(r.label || '')}</td><td class="muted">${esc(r.old_text || '–')}</td><td><b>${esc(r.new_text || '–')}</b></td></tr>`
    : c.kind === 'book' || c.kind === 'hold' ? `<tr><td class="nowrap">${esc(FD(r.label || ''))}</td><td>${[r.account, r.counterparty].filter(Boolean).map(esc).join(' · ')}<div class="muted">${esc(r.text || '')}</div></td><td class="num">${r.new == null ? '' : fmt.format(r.new)}</td></tr>`
    : `<tr><td>${esc(/^\d{4}-\d{2}$/.test(r.label || '') ? MLL(r.label) : r.label || '')}</td><td class="num muted">${r.old != null ? num(c, r.old) : r.shown != null ? num(c, r.shown) : '–'}</td><td class="num"><b>${num(c, r.new)}</b></td></tr>`;
  const rows = c => (c.rows || []).length ? `<details class="as-log-rows"><summary class="muted small">${tn('ki_a_zeilen', c.rows.length, c.rows.length)}</summary><table class="as-e-t"><tbody>${c.rows.map(r => row(c, r)).join('')}</tbody></table></details>` : '';
  el.classList.toggle('muted', !list.length);
  el.innerHTML = !list.length ? t('ki_aenderungen_keine') : `<div class="as-tw"><table><thead><tr><th>${t('ki_a_zeit')}</th><th>${t('ki_a_was')}</th><th>${t('ki_a_grund')}</th><th>${t('ki_a_stand')}</th></tr></thead><tbody>${list.map(c => c.kind === 'memory' ? mem(c) : `<tr>
    <td class="nowrap">${esc(FDT(c.time))}</td><td><b>${esc(kind(c.kind))}</b> · ${esc(c.title || '')}${c.category ? ' → ' + esc(c.category.replace(/ \/ /g, ' › ')) : ''}${c.sub ? `<div class="muted small">${esc(c.sub)}</div>` : ''}${c.count && c.kind !== 'web' ? `<div class="muted small">${tn(c.kind === 'book' || c.kind === 'hold' ? 'ki_e_buchungen' : 'ki_a_umsaetze', c.count, c.count)}${c.sum != null ? ' · ' + fmt.format(c.sum) : ''}</div>` : ''}${c.kind !== 'web' ? rows(c) : ''}</td><td>${esc(c.reason || '–')}</td>
    <td class="nowrap">${c.kind === 'web' ? (c.state === 'failed' ? t('ki_a_fehlgeschlagen') : c.what === 'read' ? t('ki_a_abgerufen') : tn('ki_w_done_n', c.count || 0, c.count || 0)) : t(c.state === 'undone' ? 'ki_e_undone' : 'ki_e_done')}${c.final ? ' · ' + t('ki_a_endgueltig') : ''}${[c.note, c.state === 'undone' ? c.undo_note : ''].filter(Boolean).map(x => `<div class="muted small">${esc(x)}</div>`).join('')}</td></tr>`).join('')}</tbody></table></div>`;
}
const asRate = b => b >= 1e6 ? (b / 1e6).toLocaleString(LOCALE, {maximumFractionDigits: b >= 1e7 ? 0 : 1}) + ' MB/s' : Math.max(1, Math.round(b / 1e3)).toLocaleString(LOCALE) + ' KB/s';
const asLeft = l => { const s = (l.total - l.done) / l.rate; return s >= 90 ? t('ki_dl_rest_min', asN(s / 60)) : t('ki_dl_rest_s', asN(Math.max(1, s))); };
const asLoadText = l => (l.total ? t('ki_laedt', l.label || '', asGB(l.done), asGB(l.total)) : t('ki_laedt_start', l.label || ''))
  + (l.rate > 0 ? ' · ' + asRate(l.rate) + (l.total > l.done ? ' · ' + asLeft(l) : '') : '');
// a download of the assistant (its program or a model) goes on while you work elsewhere in Kontor: a line at the bottom left
// (spinner, what, how far; the details on hover, a click leads to it), watched every second and a half until it is over
const asLoading = () => { const l = (AS.st || {}).load; return l && (l.state === 'running' || (AS.st || {}).updating) ? l : null; };
const asLoadShort = l => t(l.kind === 'runtime' ? 'ki_sm_programm' : 'ki_sm_modell') + (l.total ? ' · ' + Math.floor(100 * l.done / l.total) + ' %' : '');
let AS_WATCH = null;
function asWatch() {
  if (AS_WATCH || !asLoading()) return;
  const tick = async () => {
    const was = asLoading();
    try { AS.st = await api('/api/assistant/status'); } catch (e) { /* the next try */ }
    statusMini();
    const l = (AS.st || {}).load;
    if (asLoading()) { AS_WATCH = setTimeout(tick, 1500); return; }
    AS_WATCH = null;
    if (was && l && !(S.tab === 'settings' && S.sub === 'assistant')) {          // over while you were elsewhere: said once (the page there shows it)
      if (l.state === 'done') toast(t('ki_dl_fertig', l.label || ''), 5000);
      else if (l.state === 'error') toast(l.text || t('fehler_3'), 8000);
      asChrome();
    }
  };
  AS_WATCH = setTimeout(tick, 1500);
}
function bindAssistent(main) {
  const post = async (path, body, quiet) => { try { const r = await api(path, body || {}); if (r && r.settings) AS.st = r; asChrome(); if (!quiet) await route(); return r; } catch (e) { toast(e.message, 7000); await route(); return null; } };
  const set = body => post('/api/assistant/settings', body);
  const on = (sel, ev, fn) => $$(sel, main).forEach(el => el.addEventListener(ev, e => fn(el, e)));
  on('#as-enabled', 'change', el => set({enabled: el.checked}));
  on('input[name="as-model"]', 'change', el => set({model: el.value}));
  on('input[name="as-speech"]', 'change', el => set({speech: el.value}));
  on('#as-speech-start', 'change', el => set({speech_start: el.value}));
  on('#as-speech-filter', 'change', el => set({speech_filter: el.value === '1'}));
  on('#as-context', 'change', el => set({context: +el.value}));
  on('#as-idle', 'change', el => set({idle_minutes: +el.value}));
  on('#as-save', 'change', el => set({save_chats: el.checked}));
  // the memory: its switch, a new note, the search, the list (drawn anew in place: the page keeps its position). What is being
  // typed -- a new note, a change of one -- is kept in AS, so that drawing the list or the page anew does not lose it.
  on('#as-mem', 'change', el => post('/api/assistant/settings', {memory: el.checked}, true));
  const memEnd = () => { AS.memEdit = ''; AS.memDraft = null; };
  const memSave = (it, x) => { const v = $('.as-mem-ta', it).value.trim(); if (v === x.text) { memEnd(); asMemDraw(); } else asMemLoad({action: 'edit', id: x.id, text: v}).then(r => { if (r) { memEnd(); asMemDraw(); } }); };
  const memAdd = async () => { const el = $('#as-mem-new', main), v = el ? el.value.trim() : ''; if (!v) return; const r = await asMemLoad({action: 'add', text: v}); if (r) { AS.memNew = ''; const now = $('#as-mem-new'); if (now) now.value = ''; const btn = $('#as-mem-add'); if (btn) btn.disabled = true; if (r.known) toast(t('ki_g_bekannt'), 4000); } };
  on('#as-mem-new', 'input', el => { AS.memNew = el.value; $('#as-mem-add', main).disabled = !el.value.trim(); });
  on('#as-mem-new', 'keydown', (el, e) => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); memAdd(); } });
  on('#as-mem-add', 'click', memAdd);
  on('#as-mem-q', 'input', el => { clearTimeout(AS.memT); AS.memT = setTimeout(() => { AS.memQ = el.value.trim(); AS.mem = null; memEnd(); asMemLoad(); }, 200); });
  on('#as-mem-all', 'click', () => { const n = (AS.mem || {}).notes || 0; if (n && confirm(tn('ki_g_alles_frage', n, asN(n)))) { memEnd(); asMemLoad({action: 'forget_all'}); } });
  on('#as-mem-list', 'click', (box, e) => {
    const b = e.target.closest('button'), it = b && b.closest('.as-mem-it'), id = it && it.dataset.id, x = id && ((AS.mem || {}).items || []).find(y => y.id === id);
    if (b && b.id === 'as-mem-more') { asMemLoad(null, true); return; }
    if (!x) return;
    if (b.classList.contains('as-mem-pin')) asMemLoad({action: 'pin', id, pinned: !x.pinned});
    else if (b.classList.contains('as-mem-edit')) { AS.memEdit = id; AS.memDraft = null; asMemDraw(); }
    else if (b.classList.contains('as-mem-no')) { memEnd(); asMemDraw(); }
    else if (b.classList.contains('as-mem-ok')) memSave(it, x);
    else if (b.classList.contains('as-mem-del') && confirm(t('ki_g_frage', x.text))) { if (AS.memEdit === id) memEnd(); asMemLoad({action: 'delete', id}); }
  });
  on('#as-mem-list', 'input', (box, e) => { if (e.target.classList.contains('as-mem-ta')) AS.memDraft = e.target.value; });
  on('#as-mem-list', 'keydown', (box, e) => { if (!e.target.classList.contains('as-mem-ta')) return;
    const it = e.target.closest('.as-mem-it'), x = it && ((AS.mem || {}).items || []).find(y => y.id === it.dataset.id);
    if (e.key === 'Escape') { memEnd(); asMemDraw(); } else if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && x) { e.preventDefault(); memSave(it, x); } });
  if (AS.mem) asMemDraw();          // (the page drawn anew: the list as it was, at once -- then fresh)
  asMemLoad();
  on('#as-chats-old', 'click', async () => {          // not continued for a year: gone, after a question
    if (!confirm(tn('ki_verlaeufe_alt_frage', a.chats_old, asN(a.chats_old)))) return;
    try {
      await api('/api/assistant/chats/delete', {older_days: 365});
      const left = new Set(((await api('/api/assistant/chats')).chats || []).map(c => c.id));          // the one on screen deleted: the panel starts anew
      if (AS.conv && !left.has(AS.conv) && !AS.busy) Object.assign(AS, {job: null, msgs: [], conv: ''});
      AS.chats = null; if (AS.list) asHist(true); else if ($('#as-body')) asMsgs(true);
    } catch (e) { toast(e.message, 5000); }
    await asLoad(); route();
  });
  on('#as-chats-del', 'click', async () => { try { AS.chats = (await api('/api/assistant/chats')).chats || []; } catch (e) { AS.chats = []; } await asDelChats(''); await asLoad(); route(); });
  on('#as-sandbox', 'change', el => { const cur = AS.st.settings.sandbox;          // weaker rules: only after a question
    if (['strict', 'basic', 'off'].indexOf(el.value) > ['strict', 'basic', 'off'].indexOf(cur) && !confirm(t(`ki_sb_${el.value}_frage`))) { el.value = cur; return; } set({sandbox: el.value}); });
  on('.as-right', 'change', el => set({rights: {[el.dataset.r]: el.checked}}));
  on('#as-log', 'toggle', el => { if (el.open) asChangesLoad(); });
  const key = () => { const el = $('#as-tavily', main), v = el ? el.value.trim() : ''; if (v) post('/api/assistant/web', {tavily_key: v}); };
  on('#as-tavily-save', 'click', key); on('#as-tavily', 'keydown', (el, e) => { if (e.key === 'Enter') { e.preventDefault(); key(); } });
  on('#as-tavily-del', 'click', () => { if (confirm(t('ki_tavily_frage'))) post('/api/assistant/web', {tavily_key: ''}); });
  on('.as-trust-src', 'change', () => set({web_trusted: {sources: $$('.as-trust-src', main).filter(x => x.checked).map(x => x.value)}}));
  on('#as-websites', 'change', el => set({web_trusted: {hosts: el.value}}));
  on('#as-websites', 'keydown', (el, e) => { if (e.key === 'Enter') { e.preventDefault(); el.blur(); } });          // (saved as it loses the focus)
  on('#as-rt-install', 'click', () => post('/api/assistant/runtime/install'));
  on('#as-rt-remove', 'click', () => { if (confirm(t('ki_programm_entfernen_frage'))) post('/api/assistant/runtime/remove'); });
  on('#as-check', 'click', async el => { el.classList.add('busy'); el.disabled = true; await post('/api/assistant/check'); });
  on('#as-update-all', 'click', el => { el.disabled = true; post('/api/assistant/update-all'); });
  on('#as-check-mode', 'change', el => set({check_mode: el.value}));
  on('.as-dl', 'click', el => { if (el.dataset.fit !== 'big' || confirm(t('ki_zu_gross_frage', el.dataset.name, asRAM((AS.st.platform || {}).ram || 0)))) post('/api/assistant/model/download', {id: el.dataset.id}); });
  on('.as-del', 'click', el => { if (confirm(t('ki_loeschen_frage', el.dataset.name))) post('/api/assistant/model/delete', {id: el.dataset.id}); });
  on('#as-cancel', 'click', () => post('/api/assistant/model/cancel'));
  on('#as-reveal', 'click', async () => { try { await api('/api/file/reveal', {path: AS.st.folder}); } catch (e) { toast(e.message, 5000); } });
  on('#as-start', 'click', () => post('/api/assistant/server', {action: 'start'}));
  on('#as-stop', 'click', () => post('/api/assistant/server', {action: 'stop'}));
  const files = async () => {
    const repo = ($('#as-repo', main).value || '').trim().replace(/^https?:\/\/huggingface\.co\//, '').replace(/\/+$/, ''), box = $('#as-filelist', main); if (!repo) return;
    box.innerHTML = `<div class="as-item muted small"><span><span class="spin"></span>${t('wird_geladen')}</span></div>`;
    try {
      const r = await api('/api/assistant/model/files', {repo});
      box.innerHTML = (r.files || []).length ? r.files.map(f => `<div class="as-item sub"><span>${esc(f.file)}<br><span class="muted small">${asGB(f.size)}</span></span><span class="as-act"><button class="small secondary as-dlf" data-file="${esc(f.file)}">${t('ki_laden')}</button></span></div>`).join('')
        : `<div class="as-item muted small"><span>${t('ki_keine_dateien')}</span></div>`;
      $$('.as-dlf', box).forEach(b => b.addEventListener('click', () => post('/api/assistant/model/download', {repo, file: b.dataset.file})));
    } catch (e) { box.innerHTML = `<div class="banner err small">${esc(e.message)}</div>`; }
  };
  asMicPerm();
  on('#as-files', 'click', files); on('#as-repo', 'keydown', (el, e) => { if (e.key === 'Enter') { e.preventDefault(); files(); } });
  on('#as-repo', 'input', el => { $('#as-files', main).disabled = !el.value.trim(); });
  // while something is loading or the model starts: the progress in place, the page anew when it is over
  clearTimeout(AS.setT);
  const a = AS.st || {}, moving = () => { const s = AS.st || {}; return (s.load && s.load.state === 'running') || (s.server || {}).state === 'starting' || !!s.updating; };
  // what the page shows counts, not the last status: the watcher at the bottom left may have fetched the end already
  let shown = moving();
  // what is being loaded as the page shows it ("update everything" goes from one to the next), and the look the page knows
  const part = () => { const l = (AS.st || {}).load; return l && l.state === 'running' ? l.kind + ' ' + l.id : ''; };
  const looked = a.checked || '', drawn = part();
  // something typed or opened here that drawing the page anew would throw away
  const inUse = () => [...main.querySelectorAll('input:not([type=checkbox]):not([type=radio])')].some(e => e.value) || !!(($('#as-filelist', main) || {}).childElementCount) || !!(document.activeElement && document.activeElement.closest('#main input, #main select'));
  const tick = async () => {
    if (S.tab !== 'settings' || S.sub !== 'assistant') return;
    try { AS.st = await api('/api/assistant/status'); } catch (e) { AS.setT = setTimeout(tick, 2000); return; }
    statusMini(); asWatch();
    const l = AS.st.load, p = $('#as-prog', main);
    const was = shown; shown = moving();
    if (was && !moving()) {
      asChrome(); await route(); return;              // the first model is chosen by the service itself
    }
    // Kontor has looked for newer versions meanwhile: what it found is shown (not while you are typing here)
    if (moving() && part() !== drawn) { await route(); return; }          // the next part: its progress in its place
    if ((AS.st.checked || '') !== looked && !moving() && !inUse()) { await route(); return; }
    if (l && l.state === 'running' && p) { $('.prog i', p).style.width = (l.total ? Math.round(100 * l.done / l.total) : 0) + '%'; $('.prog-l', p).textContent = asLoadText(l); }
    const sv = AS.st.server || {}, u = $('#as-use', main);
    if (u && sv.rss) u.textContent = t('ki_verbrauch', asRAM(sv.rss), asN(sv.cpu || 0)) + (sv.tps ? ' · ' + t('ki_tempo', asN(sv.tps)) : '');
    AS.setT = setTimeout(tick, moving() ? 1000 : 5000);
  };
  AS.setT = setTimeout(tick, moving() ? 1000 : 5000);
}

window.addEventListener('hashchange', route);
document.addEventListener('click', e => { const b = e.target.closest('#modus-seg button'); if (b) { S.mode = b.dataset.m; route(); } });
document.addEventListener('click', e => {
  const lv = e.target.closest('#cf-ebene button, .cf-lv-btn'); if (lv) { S[S.tab === 'planning' ? 'planEbene' : 'cfEbene'] = +lv.dataset.e; S.cfTog = {}; route(); return; }       // a level: every row as the level has it
  const z = e.target.closest('#cf-zeit button'); if (z) { S.cfZeit = z.dataset.z; S.cfBrZoom = S.cfWbZoom = null;
    // the table follows: its last month in view (an earlier year: the table starts with it)
    const D = B(), [cur] = cfMonths(D, S.cfZeit), end = cur[cur.length - 1];
    if (end && S.mode !== 'years' && +end.slice(0, 4) < firstYear(D)) S.vonJahr = +end.slice(0, 4);
    Promise.resolve(route()).then(() => { if (end) cfTableShow(end); }); return; }
  const st = e.target.closest('#von-jahr button'); if (st && !st.disabled) {
    const box = st.closest('#von-jahr'), y = Math.min(+box.dataset.max, Math.max(+box.dataset.min, +box.dataset.y + +st.dataset.d));
    S.vonJahr = y === +box.dataset.max - (MONTH_YEARS - 1) ? null : y; S.toEarlier = +st.dataset.d < 0; route(); }      // an earlier year: start with it
});
document.addEventListener('change', e => { const id = e.target.id; if (id === 'planan') { S.plan = e.target.checked; route(); } else if (id === 'realan') { S.real = e.target.checked; route(); } else if (id === 'alle-zeilen') { if (S.tab === 'balance') S.alleB = e.target.checked; else S.all = e.target.checked; route(); } });
$('#menu-btn').addEventListener('click', () => $('.side').classList.toggle('open'));
document.addEventListener('keydown', e => { if (e.key === 'Escape' && (REC.on || REC.starting)) { e.stopPropagation(); asMicStop(false); } }, true);          // a recording first: thrown away
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#drawer').classList.contains('open') && !(drawerDirty() && !confirm(t('ungespeicherte_aenderungen_verwerfen')))) closeDrawer(); });
// Klick neben das Seitenfenster schliesst es (bei ungespeicherten Eingaben erst nach Rueckfrage)
document.addEventListener('pointerdown', e => {
  const dr = $('#drawer'); if (!dr.classList.contains('open') || dr.contains(e.target) || e.target.closest('#toast, .dlg-back')) return;
  if (drawerDirty() && !confirm(t('ungespeicherte_aenderungen_verwerfen'))) return;
  const key = DRW.key; closeDrawer(); DRW.closed = key ? {key, t: Date.now()} : null;
});
try { const s = JSON.parse(LS.get('kontor.ui') || '{}'); Object.assign(S, {plan: s.plan !== false, real: !!s.real, area: s.area || null}); } catch (e) {}
viewApply(viewLoad());
let SNAP_T = null;
window.addEventListener('resize', () => { clearTimeout(SNAP_T); SNAP_T = setTimeout(() => { if (!PRINT.on && ['balance', 'cashflow', 'planning'].includes(S.tab)) $$('#main .wrap.snap').forEach(w => { const l = w.scrollLeft; snapTable(w); w.scrollLeft = snapLeft(w, l); }); }, 150); });
window.addEventListener('beforeunload', () => { try { LS.set('kontor.ui', JSON.stringify({plan: S.plan, real: S.real, area: S.area})); } catch (e) {} });
setInterval(async () => { if (S.csrf && !document.hidden && !OFFLINE.mode) { try { await pollStatus(); } catch (e) {} } }, 30000);
// a newer version of the assistant found meanwhile (the service looks once a day): marked without a reload -- only the status, asked on this Mac
setInterval(async () => { if (S.csrf && !document.hidden && asOn() && AS.st.local && !asLoading() && !(S.tab === 'settings' && S.sub === 'assistant')) { try { const st = await api('/api/assistant/status'); if (asOn()) { AS.st = st; statusMini(); } } catch (e) { /* the next time */ } } }, 600000);
// Zurück im Fenster (z. B. nach MoneyMoney): sofort nachsehen statt bis zu 30 s einen alten Stand zu zeigen
document.addEventListener('visibilitychange', () => { if (!document.hidden && S.csrf && !OFFLINE.mode) pollStatus().catch(() => {}); });
applyStatic();
checkSession();
