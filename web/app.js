/* Kontor -- Oberflaeche. Keine Fremdbibliotheken, alles laeuft gegen /api/ auf demselben Rechner. */
'use strict';

// ---------------------------------------------------------------- Sprache (alle Texte in web/i18n.js: Schluessel -> [Deutsch, Englisch])
const LANGS = [['de', 'Deutsch'], ['en', 'English']];      // Auswahl überall als Liste (weitere Sprachen: hier und in i18n.js ergänzen)
const langOk = l => LANGS.some(([v]) => v === l) ? l : 'de';
let LANG = 'de';
try { LANG = langOk(localStorage.getItem('kontor.lang')); } catch (e) {}
const langOpts = () => LANGS.map(([v, n]) => `<option value="${v}" ${LANG === v ? 'selected' : ''}>${n}</option>`).join('');
function t(k, ...a) {
  const e = I18N[k], s = e ? (LANG === 'en' && e[1] != null ? e[1] : e[0]) : k;
  return a.length ? s.replace(/\{(\d+)\}/g, (m, i) => String(a[+i])) : s;
}
const tx = t;                 // wo ein lokales t den Namen verdeckt
function setLang(l, pending) {
  // Sprache wechseln: merken und Oberflaeche neu laden (alle Texte, Formate und Monatsnamen einheitlich)
  l = langOk(l);
  try { localStorage.setItem('kontor.lang', l); if (pending) localStorage.setItem('kontor.lang.pending', '1'); } catch (e) {}
  if (l !== LANG) location.reload();
}
function applyStatic() {
  document.documentElement.lang = LANG;
  $$('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  $$('[data-i18n-ph]').forEach(el => { el.placeholder = t(el.dataset.i18nPh); });
  $$('[data-i18n-aria]').forEach(el => el.setAttribute('aria-label', t(el.dataset.i18nAria)));
  const ls = $('#lang-sel'); if (ls) ls.innerHTML = langOpts();
}
async function syncLang() {
  // nach der Anmeldung: Auswahl auf der Anmeldeseite an den Dienst geben, sonst die gespeicherte Sprache uebernehmen
  let pending = false; try { pending = localStorage.getItem('kontor.lang.pending') === '1'; localStorage.removeItem('kontor.lang.pending'); } catch (e) {}
  const cfg = ((S.CFG || {}).oberflaeche || {}).sprache || 'de';
  if (pending && cfg !== LANG && !OFFLINE.mode) { try { const r = await api('/api/language', {sprache: LANG}); S.CFG.oberflaeche = Object.assign(S.CFG.oberflaeche || {}, {sprache: r.sprache}); } catch (e) {} return; }
  if (cfg !== LANG) setLang(cfg);
}
function tn(k, n, ...a) { const f = t(k, n, ...a).split('|'); return f.length > 1 ? f[n === 1 ? 0 : 1] : f[0]; }   // Einzahl|Mehrzahl


// ---------------------------------------------------------------- Grundlagen
const LOCALE = LANG === 'en' ? 'en-GB' : 'de-DE';
const fmt = new Intl.NumberFormat(LOCALE, {minimumFractionDigits: 2, maximumFractionDigits: 2});
const fmt0 = new Intl.NumberFormat(LOCALE, {maximumFractionDigits: 0});
const F = v => (v == null || isNaN(v) ? '–' : fmt.format(v));
const F0 = v => (v == null || isNaN(v) ? '–' : fmt0.format(v));
const Fk = v => (v == null || isNaN(v) ? '–' : (Math.abs(v) >= 1e6 ? (v / 1e6).toLocaleString(LOCALE, {maximumFractionDigits: 2}) + ' M' : Math.abs(v) >= 1e4 ? (v / 1e3).toLocaleString(LOCALE, {maximumFractionDigits: 0}) + ' k' : F0(v)));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const MONATE = LANG === 'en' ? ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'] : ['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'];
const ML = m => MONATE[+m.slice(5) - 1] + ' ' + m.slice(2, 4);
const FD = d => (d && d.length >= 10) ? [d.slice(8, 10), d.slice(5, 7), d.slice(0, 4)].join(LANG === 'en' ? '/' : '.') : (d || '');
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const ROLE = {liquiditaet: [t('pos_bankguthaben'), 'var(--c-liq)'], wertpapiere: [t('pos_wertpapiere'), 'var(--c-anl)'], anlagen: [t('pos_gebundene_anlagen'), 'var(--c-fest)'], immobilien: [t('immobilien'), '#b8860b'],
              beteiligungen: [t('beteiligungen'), 'var(--c-bet)'], sachwerte: [t('sachwerte'), '#8e8e93'], forderungen: [t('pos_forderungen'), 'var(--c-ford)'], sonstiges: [t('sonstiges'), '#636366'], verbindlichkeiten: [t('pos_verbindlichkeiten'), 'var(--c-verb)'],
              eigenkapital: [t('role_eigenkapital'), '#7d7aa8'], eventual: [t('role_eventual'), '#a8a29e'], ignorieren: [t('nicht_bilanzieren'), '#c7c7cc']};
const ROLE_OPTS = [['liquiditaet', t('pos_bankguthaben')], ['wertpapiere', t('pos_wertpapiere')], ['anlagen', t('pos_gebundene_anlagen')], ['immobilien', t('immobilien')], ['beteiligungen', t('beteiligungen')], ['sachwerte', t('sachwerte')], ['forderungen', t('pos_forderungen')], ['sonstiges', t('sonstiges')], ['verbindlichkeiten', t('pos_verbindlichkeiten')], ['eigenkapital', t('kapitalkonten_eigenkapital_nicht_im_ne')], ['eventual', t('avale_buergschaften_nicht_im_nettoverm')], ['ignorieren', t('nicht_bilanzieren')]];
// Hilfetexte (Tooltips). Schluessel werden mit hq('schluessel') eingeblendet.
const H = {
  bereich: t('ein_bereich_ist_eine_menge'),
  haupt: t('es_gibt_genau_einen_hauptbereich'),
  anteil: t('dein_anteil_an_dieser_gesellschaft'),
  gruppenwahl: t('eine_gruppe_waehlen_heisst_alle'),
  anzeige: t('nach_aktivitaet_standard_blendet_ein'),
  position_kurz: t('wo_das_konto_in_der'),
  verlauf_kurz: t('woher_die_monatsstaende_kommen_umsaetz'),
  berechtigung: t('wofuer_kontor_liest_ueber_die'),
  position: t('die_bilanzposition_eines_kontos_sie'),
  verlauf: t('umsaetze_saldo_am_monatsende_heutiger'),
  zuordnen: t('hier_landen_alle_umsaetze_die'),
  kontor_kategorien: t('reihenfolge_manuelle_zuordnung_eigene'),
  mm_ueberschreiben: t('standard_umsaetze_mit_moneymoney_kateg'),
  konten_zuordnung: t('bereich_position_und_verlauf_werden'),
  verlauf_import: t('datei_mit_monats_oder_tagesstaenden'),
  inaktiv: t('gilt_fuer_konten_mit_anzeige'),
  probelauf: t('im_testmodus_schlaegt_kontor_die'),
  mmhist: t('sicherheit_die_datei_bleibt_verschlues'),
  depotverlauf: t('moneymoney_stellt_ueber_seine_schnitts'),
  abruf: t('stand_je_konto_in_dem'),
  touchid: t('eingeschaltet_die_anmeldung_am_mac'),
  bilanz_stand: t('salden_am_monatsende_der_laufende'),
  abgleich: t('datenstand_in_zwei_stufen_banken'),
  fern: t('fern_tip'),
  fern_was: t('fern_was_tip'),
  timemachine: t('timemachine_tip'),
  diagnose: t('diagnose_tip'),
  port: t('port_tip'),
  update_quelle: t('update_quelle_tip'),
  pruefen: t('pruefen_tip'),
  kat_auswahl: t('kat_auswahl_tip'),
  voll_lesen: t('voll_lesen_tip'),
  kennung: t('interne_kennung_des_bereichs_wird'),
  intervall: t('der_dienst_liest_alle_n'),
  mm_cat: t('erlaubt_einzelnen_umsaetzen_aus_kontor'),
  belege_ordner: t('belege_werden_als_normale_dateien'),
  belege_sub: t('platzhalter_jahr_monat_entitaet_bereic'),
  belege_kommentar: t('schreibt_den_dateinamen_des_belegs'),
  monate_zurueck: t('wie_viele_monate_historie_gelesen'),
  bind: t('auf_diesem_mac_ist_die'),
  tls: t('optional_zertifikat_schluessel_pem_fue'),
  updates: t('einzige_netzverbindung_von_kontor_einm'),
  darlehen_iban: t('die_rate_wird_am_gegenkonto'),
  darlehen_konto: t('das_manuell_gefuehrte_darlehenskonto_i'),
  darlehen_quelle: t('das_konto_von_dem_die'),
  zinsmodell: t('jahresbasis_zins_satz_stand_am'),
  satz: t('zinssaetze_mit_gueltigkeitsbeginn_z_b'),
  basis_override: t('erzwingt_die_zinsbasis_fuer_ein'),
  beteiligung: t('zielkonto_anteil_nettowert_der_gewaehl'),
  spiegel: t('zielkonto_faktor_saldo_des_quellkontos'),
  methode: t('12_6_monate_durchschnitt_der'),
  inflation: t('ausgaben_steigen_standardmaessig_mit_d'),
  steig_ein: t('jaehrliche_steigerung_der_einnahmen_z'),
  rendite: t('jaehrliche_wertentwicklung_fuer_wertpa'),
  ereignis: t('einmalige_oder_wiederkehrende_planerei'),
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
  dokumente: t('verknuepfungen_zu_dateien_auf_dem'),
  offline: t('als_app_auf_dem_iphone'),
  paket: t('einstellungspaket_regeln_bereiche_posi'),
  bch: t('bch_hinweis'),
  geld_unterwegs: t('geld_unterwegs_tip'),
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

const S = { tab: 'uebersicht', modus: 'monate', plan: true, real: false, alle: false, collapsed: {}, csrf: null, bereich: null,
            DATA: null, CFG: null, KONTEN: [], KATS: [], STATUS: null, steuerJahr: null, steuerEnt: null, vorschlag: false,
            uf: {entitaet: '', jahr: '', konto: '', q: '', ohne_beleg: false, ohne_kategorie: false, richtung: ''}, sel: new Set(), drawerTx: null };

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
  try { r = await fetch(path, opts); } catch (e) { throw new Error(IS_LOCAL ? t('err_dienst_lokal') : t('err_mac_weg')); }
  if (r.headers.get('X-Kontor-Offline') === '1' && opts.method === 'GET' && !OFFLINE.mode && !IS_LOCAL && mode !== 'direct' && path !== '/api/session') {
    // Zwischengespeicherte Antwort, obwohl wir online waren: Server nur langsam? Gegenprobe ohne Zeitlimit
    try { return await api(path, body, method, 'direct'); }
    catch (e) { OFFLINE.mode = true; offlineBanner(); }
  }
  let data = null;
  try { data = await r.json(); } catch (e) { data = {}; }
  if (r.headers.get('X-Kontor-Offline') === '1') {
    const at = r.headers.get('X-Kontor-Cached-At'); if (at) OFFLINE.stand = at;
    if (IS_LOCAL) throw new Error(t('err_dienst_antwortet_nicht'));
  } else if (OFFLINE.mode && opts.method === 'GET' && r.ok && path !== '/api/session') { OFFLINE.mode = false; OFFLINE.stand = null; offlineBanner(); }
  if (r.status === 401 && path !== '/api/session') { S.csrf = null; if (OFFLINE.mode) { OFFLINE.mode = false; OFFLINE.stand = null; checkSession(); } else showLogin(); throw new Error('nicht angemeldet'); }
  if (!r.ok) { const e = new Error(data.fehler || (t('fehler') + r.status)); e.data = data; throw e; }
  if (opts.method !== 'GET' && data && data.bericht === 'angefordert') afterRebuild(data);
  return data;
}
function download(url) { const a = document.createElement('a'); a.href = url; a.download = ''; document.body.appendChild(a); a.click(); a.remove(); }
const xlsxBtn = (was, extra = '') => `<button class="xlsx small" data-xlsx="${was}" ${extra}>Excel</button>`;

// ---------------------------------------------------------------- Offline (PWA am iPhone, Mac nicht erreichbar)
const OFFLINE = {mode: false, stand: null, idle: null};
function offlineBanner() {
  if (OFFLINE.mode) { const b = $('#banner'); b.innerHTML = `${t('offline_ansicht_der_mac_ist', OFFLINE.stand ? new Date(OFFLINE.stand).toLocaleString(LOCALE, {dateStyle: 'short', timeStyle: 'short'}) : t('unbekannt'), hq('offline'))}`; b.className = 'banner info'; }
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
  if (!(window.crypto && crypto.subtle)) throw new Error(t('err_offline_https'));
  const v = await api('/api/offline/verifier');
  if (!v.offline) throw new Error(t('err_kein_offline_pruefwert'));
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits({name: 'PBKDF2', hash: 'SHA-256', salt: bytesOf(v.offline.salt), iterations: v.offline.rounds}, key, 256);
  if (hexOf(bits) !== v.offline.hash) throw new Error(t('err_passwort_falsch'));
  if (S.CFG) S.CFG.oberflaeche = Object.assign(S.CFG.oberflaeche || {}, {sperre_minuten: v.sperre_minuten});
  return true;
}
function swApply(allowed) {
  if (!('serviceWorker' in navigator)) return;
  if (allowed) { navigator.serviceWorker.register('/sw.js').catch(() => {}); return; }
  navigator.serviceWorker.getRegistrations().then(rs => rs.forEach(r => r.unregister())).catch(() => {});
  try { caches.delete('kontor-data'); } catch (e) {}
}

// ---------------------------------------------------------------- Anmeldung
let SESSION = null;
async function checkSession() {
  try { SESSION = await api('/api/session'); } catch (e) { $('#login').classList.remove('hidden'); $('#login-err').textContent = e.message + t('neuer_versuch_in_5_s'); setTimeout(checkSession, 5000); return; }
  swApply(SESSION.offline_kopie !== false);
  $('#ver').textContent = 'v' + (SESSION.version || '');
  if (SESSION.offline && IS_LOCAL) { $('#login').classList.remove('hidden'); $('#login-err').textContent = t('der_kontor_dienst_antwortet_nicht'); setTimeout(checkSession, 5000); return; }
  if (SESSION.offline) { OFFLINE.mode = true; showLogin(); return; }
  OFFLINE.mode = false;
  if (SESSION.angemeldet) { S.csrf = SESSION.csrf; await enterApp(); } else showLogin();
}
function showLogin() {
  $('#shell').classList.add('hidden'); $('#login').classList.remove('hidden'); $('#drawer').classList.remove('open');
  const setup = SESSION && SESSION.einrichtung_noetig && !OFFLINE.mode;
  $('#login-text').textContent = OFFLINE.mode ? t('der_mac_ist_nicht_erreichbar')
    : setup ? t('erster_start_passwort_festlegen_mindes')
    : (SESSION && SESSION.einrichtung_nur_lokal ? t('noch_kein_passwort_festgelegt_die') : '');
  $('#login-text').hidden = !$('#login-text').textContent;
  // Touch ID eingeschaltet (am Mac): nur Touch ID, Passwort erst auf Wunsch – nie beides gleichzeitig
  const tid = !setup && !OFFLINE.mode && SESSION && SESSION.touchid;
  const tidMode = tid && !LOGIN.pw;
  $('#login-pw2').classList.toggle('hidden', !setup);
  $('#setup-tid').classList.toggle('hidden', !(setup && SESSION && SESSION.touchid_verfuegbar));
  $('#login-btn').textContent = setup ? t('passwort_festlegen') : t('anmelden');
  $('#tid-box').classList.toggle('hidden', !tidMode);
  $('#login-form').classList.toggle('hidden', !!tidMode);
  $('#tid-instead').classList.toggle('hidden', !(tid && LOGIN.pw));
  $('#login-err').textContent = SESSION && SESSION.gesperrt_sekunden ? (t('gesperrt_fuer') + SESSION.gesperrt_sekunden + t('s_nach_fehlversuchen')) : '';
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
  $('#login-err').textContent = t('touch_id_bitte_am_mac');
  try { const r = await api('/api/touchid', {}); S.csrf = r.csrf; $('#login-err').textContent = ''; await enterApp(); }
  catch (err) { $('#login-err').textContent = auto ? t('touch_id_nicht_bestaetigt_erneut') : err.message; }
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
  if (setup && pw !== $('#login-pw2').value) { $('#login-err').textContent = t('passwoerter_stimmen_nicht_ueberein'); return; }
  if (OFFLINE.mode) {
    $('#login-err').textContent = t('pruefe');
    try { await offlineLogin(pw); S.csrf = 'offline'; $('#login-pw').value = ''; $('#login-err').textContent = ''; await enterApp(); } catch (err) { $('#login-err').textContent = err.message; }
    return;
  }
  try {
    const r = await api(setup ? '/api/setup' : '/api/login', setup ? Object.assign({passwort: pw, sprache: LANG}, SESSION.touchid_verfuegbar ? {touchid: $('#setup-tid-cb').checked} : {}) : {passwort: pw});
    LOGIN.pw = false;
    S.csrf = r.csrf; $('#login-pw').value = ''; $('#login-pw2').value = '';
    await enterApp();
  } catch (err) { $('#login-err').textContent = err.message; }
});
$('#touchid-btn').addEventListener('click', () => tryTouchId(false));
$('#lang-sel').addEventListener('change', e => setLang(e.target.value, true));
$('#pw-instead').addEventListener('click', () => { LOGIN.pw = true; showLogin(); });
$('#tid-instead').addEventListener('click', () => { LOGIN.pw = false; showLogin(); });
$('#sync-btn').addEventListener('click', () => syncNow());
$('.side .brand').addEventListener('click', e => { location.hash = e.target.closest('#ver') ? '#updates' : '#uebersicht'; });
$('#lock-btn').addEventListener('click', async () => { try { await api('/api/lock', {}); } catch (e) {} S.csrf = null; TID.skipNext = true; await checkSession(); });

async function enterApp() {
  $('#login').classList.add('hidden'); $('#shell').classList.remove('hidden');
  await loadAll();
  await syncLang();
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
  else if (status.update && status.update.neuer) banner('Kontor ' + status.update.verfuegbar + t('ist_verfuegbar_unter_updates_installie'), 'info');
  else if (S.DATA && (S.DATA.konten_neu || []).length) { const b = $('#banner'); b.innerHTML = `${t('neue_oder_unbestaetigte_konten_0', esc(S.DATA.konten_neu.slice(0, 4).map(k => k.name).join(', ')), S.DATA.konten_neu.length > 4 ? ' …' : '')} <a href="#einrichtung/konten">${t('bereich_und_position_bestaetigen')}</a>`; b.className = 'banner info'; }
  else if (S.DATA) banner('');
  statusMini(); bereichSeg();
}
const B = () => (S.DATA && S.DATA.bereiche && S.DATA.bereiche[S.bereich] && !S.DATA.bereiche[S.bereich].fehler) ? S.DATA.bereiche[S.bereich] : null;
const BN = u => (S.DATA && S.DATA.bereich_namen && S.DATA.bereich_namen[u || S.bereich]) || '';
function mmState(st) {
  const m = st.moneymoney || {};
  if (!m.laeuft) return {cls: 'off', text: t('moneymoney_aus')};
  if (m.gesperrt === true) return {cls: 'warn', text: t('moneymoney_gesperrt')};
  if (m.gesperrt === false) return {cls: 'ok', text: t('moneymoney_laeuft')};
  return {cls: 'ok', text: t('moneymoney_laeuft')};
}
const nKonten = n => n === 1 ? t('ein_konto') : n + t('konten');
function fmtZeit(ts) {
  // 'YYYY-MM-DD HH:MM' -> 'heute 13:40' / 'gestern 08:12' / '03.11. 22:10' / '03.11.25 22:10' (Ortszeit; englisch 03/11)
  if (!ts) return '';
  const iso = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  const now = new Date(), tag = ts.slice(0, 10), zeit = ts.slice(11, 16), sep = LANG === 'en' ? '/' : '.';
  if (tag === iso(now)) return t('zeit_heute', zeit);
  if (tag === iso(new Date(now.getTime() - 864e5))) return t('zeit_gestern', zeit);
  const y = ts.slice(0, 4) === String(now.getFullYear()) ? '' : ts.slice(2, 4);
  return ts.slice(8, 10) + sep + ts.slice(5, 7) + (LANG === 'en' ? (y ? sep + y : '') : '.' + y) + ' ' + zeit;
}
function viewCtl() {
  // Spaltenansicht der Tabellen: Monate (mit Jahressummen) oder nur Jahre
  return `<div class="seg" id="modus-seg">${[['monate', t('monate'), t('monate_tip')], ['jahre', t('jahre'), '']].map(([k, l, tip]) => `<button data-m="${k}" class="${S.modus === k ? 'on' : ''}"${tip ? ` title="${tip}"` : ''}>${l}</button>`).join('')}</div>`;
}
const swCtl = (id, on, label, tip) => `<label class="switch"${tip ? ` title="${esc(tip)}"` : ''}><input type="checkbox" id="${id}" ${on ? 'checked' : ''}><i></i>${label}</label>`;
const alleCtl = n => swCtl('alle-zeilen', S.alle, t('alle_zeilen'), n ? t('alle_zeilen_tip_n', n) : t('alle_zeilen_tip'));
const planCtl = () => swCtl('planan', S.plan, t('plan'), t('plan_tip'));
const planOn = () => S.plan || S.tab === 'bilanz' || S.tab === 'planung';     // in Bilanz und Planung immer mit Plan
function hasRules() { const c = S.CFG || {}; return !!((c.darlehen || []).length || (c.beteiligungen || []).length || (c.saldo_spiegel || []).length); }
function statusMini() {
  const st = S.STATUS; if (!st) return;
  const mm = mmState(st), m = st.moneymoney || {}, b = st.bericht || {}, l = st.letzter_lauf, ba = m.bankabruf;
  const zeile = (k, v, title) => `<div class="sm-row"${title ? ' title="' + esc(title) + '"' : ''}><span>${k}</span><b>${v}</b></div>`;
  let h = `<div class="sm-head"><span class="dot ${mm.cls}"></span>${mm.text} ${hq('abgleich')}</div>`;
  if (m.stand || ba) {
    const n = ba ? ba.zurueck_anzahl : 0;
    const warn = n ? ` <span class="sm-badge" title="${esc(n + (n === 1 ? t('konto') : t('konten')) + t('laenger_nicht_abgerufen') + ba.zurueck.slice(0, 5).map(k => k.name).join(', ') + (n > 5 ? ' …' : '') + t('details_unter_synchronisierung'))}">⚠ ${n}</span>` : '';
    h += `<a href="#synchronisierung" class="sm-link" title="${t('details_zur_synchronisierung')}">`
      + zeile(t('banken_mm'), (ba ? esc(fmtZeit(ba.neuester)) : '–') + warn, '')
      + zeile(t('mm_kontor'), m.stand ? esc(fmtZeit(m.stand)) : '–', '') + '</a>';
  } else h += `<div>${t('noch_keine_daten_aus_moneymoney')}</div>`;
  if (st.neustart_ausstehend) h += `<div class="sm-busy"><span class="spin xs"></span>${t('version')} ` + esc(st.neustart_ausstehend) + ` ${t('wird_geladen')}</div>`;
  else if (b.laeuft) h += `<div class="sm-busy"><span class="spin xs"></span>${t('wird_neu_berechnet')}</div>`;
  if (m.luecken) h += `<div><a href="#synchronisierung">${t('depotstaende_pruefen')}</a></div>`;
  if (m.problem) h += `<div><a href="#synchronisierung" title="${esc(m.problem.text)}">${t('moneymoney_lief_kontor_konnte_nicht')}</a></div>`;
  if (hasRules() && st.probelauf) h += `<div><b>${t('testmodus')}</b> ${t('regeln_buchen_nichts')}</div>`;
  if (l && l.fehler) h += `<div><a href="#buchungen">${t('letzter_abgleich_mit_fehler')}</a></div>`;
  else if (l && l.probelauf && (l.vorschlaege || []).length) h += `<div><a href="#buchungen">${t('0_buchungsvorschlaege', l.vorschlaege.length)}</a></div>`;
  $('#status-mini').innerHTML = h;
  const sb = $('#sync-btn');
  if (sb) {
    const busy = !!(st.dienst.laeuft || SYNC.busy);
    sb.classList.toggle('busy', busy); sb.disabled = busy || OFFLINE.mode;
    sb.title = OFFLINE.mode ? t('offline_ansicht_der_mac_ist_2') : t('jetzt_aus_moneymoney_lesen_regeln');
  }
  const upd = $('#nav a[href="#updates"]'); if (upd) { let d = upd.querySelector('.nbadge'); const neu = !!(st.update && st.update.neuer); if (neu && !d) { d = document.createElement('span'); d.className = 'nbadge'; d.title = t('update') + st.update.verfuegbar + t('verfuegbar'); upd.appendChild(d); } else if (!neu && d) d.remove(); }
  if (!st.ablage.verschluesselt) banner(t('daten_liegen_unverschluesselt_verschlu'), 'err');
  else if (st.ablage.schluessel === 'datei') banner(t('datenschluessel_liegt_als_datei_schlue'));
}
const BER = {stand: '', timer: null};
const SYNC = {busy: false};
const MMH = {busy: false};
const DATA_TABS = ['uebersicht', 'bilanz', 'kapitalfluss', 'planung', 'steuer', 'immobilien', 'umsaetze', 'kategorien', 'buchungen'];
async function pollStatus() {
  // Status holen; läuft ein Abgleich oder Berichtsneubau, öfter nachsehen und nach Abschluss die Daten frisch laden
  S.STATUS = await api('/api/status'); statusMini();
  if (S.STATUS.version && SESSION && SESSION.version && S.STATUS.version !== SESSION.version) { toast(t('neue_version') + S.STATUS.version + t('seite_wird_neu_geladen'), 3000); setTimeout(() => location.reload(), 1200); return; }
  if (S.STATUS.neustart_ausstehend) { clearTimeout(BER.timer); BER.timer = setTimeout(() => pollStatus().catch(() => setTimeout(() => location.reload(), 4000)), 3000); return; }
  const b = S.STATUS.bericht || {};
  clearTimeout(BER.timer);
  if (b.laeuft || (S.STATUS.dienst || {}).laeuft) { BER.timer = setTimeout(() => pollStatus().catch(() => {}), 3000); return; }
  if ((b.stand || '') !== BER.stand) {
    BER.stand = b.stand || '';
    if (b.fehler) { toast(t('auswertung_konnte_nicht_aktualisiert_w') + b.fehler, 6000); return; }
    await loadAll();
    const dr = $('#drawer');
    if (dr.classList.contains('open') && HD.uuid && $('#hq-seg', dr)) { if (!HD.live && !$$('#h-grid input:not(.auto)', dr).some(i => i.value !== i.defaultValue)) { try { await openHistDrawer(HD.uuid); } catch (e) {} } }
    else if (DATA_TABS.includes(S.tab) && !dr.classList.contains('open')) route();
    toast(t('auswertung_aktualisiert'));
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
  D = D || B(); const ist = D.monate, plan = planOn() ? (D.plan_monate || []) : [];
  const mcol = (m, isPlan) => ({key: m, label: ML(m), months: [m], plan: isPlan, cur: m === D.ist_bis, part: m === D.ist_bis, year: false});
  const all = [...ist.map(m => mcol(m, false)), ...plan.map(m => mcol(m, true))];
  const years = {};
  for (const c of all) { const y = c.key.slice(0, 4); (years[y] = years[y] || {months: [], plan: false, ist: false}).months.push(c.key); if (c.plan) years[y].plan = true; else years[y].ist = true; }
  const ycol = y => ({key: y, label: (S.modus === 'jahre' ? y : 'Σ ' + y) + (years[y].plan && years[y].ist ? ' ' + t('ist_plan_kurz') : '') + (years[y].months.length < 12 ? ' · ' + years[y].months.length + t('mon') : ''), months: years[y].months, plan: years[y].plan && !years[y].ist, mixed: years[y].plan && years[y].ist, part: years[y].months.includes(D.ist_bis), cur: false, year: true});
  if (S.modus === 'jahre') return Object.keys(years).sort().map(ycol);
  const out = [];
  for (const c of all) { out.push(c); if (c.key.endsWith('-12') || c.key === all[all.length - 1].key) out.push(ycol(c.key.slice(0, 4))); }
  return out;
}
function defl(m) {
  const D = B(); if (!S.real || S.tab !== 'planung' || !D || !D.plan_monate || !D.plan_monate.includes(m)) return 1;
  const i = D.plan_monate.indexOf(m) + 1, infl = +((D.plan || {}).inflation_prozent_pa || 0);
  return Math.pow(1 + infl / 100, -i / 12);
}
const sumOver = (vals, months) => months.reduce((a, m) => a + (vals[m] ?? 0) * defl(m), 0);
const lastOf = (vals, months) => { for (let i = months.length - 1; i >= 0; i--) if (vals[months[i]] != null) return vals[months[i]] * defl(months[i]); return null; };
function cls(v, c) { let s = ''; if (c.plan) s += ' plan'; else if (c.part) s += ' part'; if (c.cur && S.modus !== 'jahre') s += ' cur'; if (c.year) s += ' year'; if (v == null || Math.abs(v) < 0.005) s += ' zero'; else s += v < 0 ? ' neg' : ' pos'; return s; }
const cells = (C, fn) => C.map(c => { const v = fn(c); return `<td class="${cls(v, c)}">${F(v)}</td>`; }).join('');
const isCurCol = c => { const D = B(), ib = (D && D.ist_bis) || ''; return c.year ? c.key === ib.slice(0, 4) && S.modus === 'jahre' : c.key === ib; };
const thead = (first, C) => `<thead><tr><th>${first}</th>${C.map(c => `<th data-key="${c.key}" class="${c.year ? 'year' : ''}${c.plan ? ' plan' : ''}"${isCurCol(c) ? ' data-cur="1"' : ''} title="${c.plan ? t('plan') : c.mixed ? t('ist_plan') : t('ist')}">${c.label}</th>`).join('')}</tr></thead>`;
const noData = `<div class="card"><div class="v s">${t('noch_keine_daten')}</div><div class="d">${t('unter_einrichtung_den_bericht_erstelle')}</div></div>`;
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
  s += '</svg><div class="chart-legend">' + Object.entries(ROLE).filter(([r]) => !series[r].every(v => Math.abs(v) < 0.5)).map(([r, [l, c]]) => `<span><i style="background:${c}"></i>${l}</span>`).join('') + `<span><i style="background:var(--fg)"></i>${t('nettovermoegen')}` + (pm.length ? t('gestrichelt_plan') : '') + '</span></div>';
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
    s += `<rect x="${(x(i) + bw * 0.12).toFixed(1)}" y="${y(ein[i]).toFixed(1)}" width="${(bw * 0.76).toFixed(1)}" height="${Math.max(0, y(0) - y(ein[i])).toFixed(1)}" fill="var(--c-ein)" rx="2"${o}/>`;
    s += `<rect x="${(x(i) + bw * 0.12).toFixed(1)}" y="${y(0).toFixed(1)}" width="${(bw * 0.76).toFixed(1)}" height="${Math.max(0, y(aus[i]) - y(0)).toFixed(1)}" fill="var(--c-aus)" rx="2"${o}/>`;
    if (m.endsWith('-01') || (i === 0 && +m.slice(5) <= 10)) s += `<text x="${(x(i) + bw / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle">${ML(m)}</text>`;
  });
  s += `<path d="${op.map((v, i) => (i ? 'L' : 'M') + (x(i) + bw / 2).toFixed(1) + ' ' + y(v).toFixed(1)).join(' ')}" fill="none" stroke="var(--fg)" stroke-width="2"/>`;
  s += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(0)}" y2="${y(0)}" stroke="var(--line-2)"/>`;
  return s + `</svg><div class="chart-legend"><span><i style="background:var(--c-ein)"></i>${t('einnahmen')}</span><span><i style="background:var(--c-aus)"></i>${t('ausgaben')}</span><span><i style="background:var(--fg)"></i>${t('operatives_ergebnis')}</span>` + (pm.length ? `<span class="muted">${t('blass_plan')}</span>` : '') + '</div>';
}
function niceTicks(min, max, n) {
  const span = (max - min) || 1, raw = span / n, p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p, step = (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p;
  const out = []; for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(v); return out;
}

// ---------------------------------------------------------------- Übersicht
async function vUebersicht() {
  const D = B();
  let h = '';
  if (!D) return h + (S.einrichtung || !S.DATA ? `<div class="card"><div class="v s">${t('willkommen_bei_kontor')}</div><div class="d">${t('die_einrichtung_fuehrt_dich_durch')}</div><div class="actions"><a href="#einrichtung"><button>${t('einrichtung_oeffnen')}</button></a></div></div>` : noData);
  const nw = D.bilanz.nettovermoegen, m = D.monate, K = D.kennzahlen || {};
  const cur = m[m.length - 1], prev = m[m.length - 2], yago = m[m.length - 13], y = cur.slice(0, 4), ly = String(+y - 1);
  const ytd = m.filter(k => k.startsWith(y)), lytd = m.filter(k => k.startsWith(ly) && +k.slice(5) <= +cur.slice(5)), lyAll = m.filter(k => k.startsWith(ly));
  const proj = D.bilanz.projektion, pm = D.plan_monate || [];
  const delta = (a, b) => a == null || b == null ? '' : `<span class="delta ${a - b >= 0 ? 'pos' : 'neg'}">${a - b >= 0 ? '+' : ''}${F0(a - b)} €</span>`;
  const pct = x => x == null ? '–' : (x * 100).toFixed(0) + ' %';
  const liqRow = D.bilanz.zeilen.filter(r => !r.gruppe && r.rolle === 'liquiditaet'), liq = Object.fromEntries(m.map(k => [k, liqRow.reduce((a, r) => a + (r.werte[k] || 0), 0)]));
  const kpi = (l, v, d, spark, go) => `<div class="card${go ? ' link' : ''}"${go ? ` data-goto="${go}"` : ''}><div class="l">${l}</div><div class="v">${v}</div><div class="d">${d || ''}</div>${spark || ''}</div>`;
  const opYtd = sumsOf(D, 'Operativ', ytd), opLytd = sumsOf(D, 'Operativ', lytd), opLy = sumsOf(D, 'Operativ', lyAll);
  const einYtd = sumsOf(D, 'Einnahmen', ytd), einLytd = sumsOf(D, 'Einnahmen', lytd), ausYtd = sumsOf(D, 'Ausgaben', ytd), ausLytd = sumsOf(D, 'Ausgaben', lytd);
  const pend = pm.length ? pm[pm.length - 1] : null;
  h += '<div class="cards">'
    + kpi(t('nettovermoegen'), F0(nw[cur]) + ' €', (prev != null ? t('monat') + delta(nw[cur], nw[prev]) : '') + (yago != null ? t('jahr') + delta(nw[cur], nw[yago]) : '') + (pend ? t('plan_2') + ML(pend) + ': ' + F0(proj.nettovermoegen[pend] * defl(pend)) + ' €' : ''), sparkline(m.slice(-24).map(k => nw[k])), '#bilanz')
    + kpi(t('pos_bankguthaben'), F0(liq[cur]) + ' €', t('reicht') + (K.reichweite_monate == null ? '–' : K.reichweite_monate.toFixed(1) + t('monate_2')) + t('bei_ausgaben_inkl_zinsen') + (pend ? t('plan_2') + ML(pend) + ': ' + F0(proj.liquiditaet[pend] * defl(pend)) + ' €' : ''), sparkline(m.slice(-24).map(k => liq[k]), 'var(--c-liq)'), '#bilanz')
    + kpi(t('einnahmen_2') + y, F0(einYtd) + ' €', t('vorjahr_gleicher_zeitraum') + F0(einLytd) + ' € ' + delta(einYtd, einLytd), sparkline(m.slice(-24).map(k => D.kapitalfluss.summen[k]?.Einnahmen ?? 0), 'var(--c-ein)'), '#kapitalfluss')
    + kpi(t('ausgaben_2') + y, F0(ausYtd) + ' €', t('vorjahr_gleicher_zeitraum') + F0(ausLytd) + ' € ' + delta(ausYtd, ausLytd), sparkline(m.slice(-24).map(k => -(D.kapitalfluss.summen[k]?.Ausgaben ?? 0)), 'var(--c-aus)'), '#kapitalfluss')
    + kpi(t('operatives_ergebnis_2') + y, F0(opYtd) + ' €', t('vorjahr_gleicher_zeitraum') + F0(opLytd) + ' € ' + delta(opYtd, opLytd) + ' · ' + t('jahr_gesamt', ly, F0(opLy)), sparkline(m.slice(-24).map(k => D.kapitalfluss.summen[k]?.Operativ ?? 0), 'var(--c-anl)'), '#kapitalfluss')
    + kpi(t('sparquote_12_monate'), pct(K.sparquote), t('operatives_ergebnis_3') + F0(K.operativ_12m) + t('einnahmen_ausgaben') + t('eur_monat', F0(K.ausgaben_monat)), '', '#kapitalfluss')
    + kpi(t('zinslast'), t('eur_monat', F0(K.zinsen_monat)), t('durchschnitt_der_letzten_12_monate') + t('eur_jahr', F0((K.zinsen_monat || 0) * 12)), '', '#kapitalfluss')
    + '</div>';
  h += `<div class="grid2"><div class="card link" data-goto="#bilanz"><h3>${t('vermoegensstruktur')}</h3>${chartStack(D)}</div><div class="card link" data-goto="#kapitalfluss"><h3>${t('einnahmen_und_ausgaben_je_monat')}</h3>${chartCashflow(D)}</div></div>`;
  // Jahresvergleich (kumuliert)
  const years = [...new Set([...m, ...(S.plan ? pm : [])].map(k => k.slice(0, 4)))].sort();
  const ycols = years.map(yy => ({key: yy, months: [...m, ...(S.plan ? pm : [])].filter(k => k.startsWith(yy)), plan: !m.some(k => k.startsWith(yy)), mixed: m.some(k => k.startsWith(yy)) && pm.some(k => k.startsWith(yy)), year: true, cur: false}));
  const lab = c => c.key + (c.mixed ? ' ' + t('ist_plan_kurz') : c.plan ? t('plan_3') : '') + (c.months.length < 12 ? ' · ' + c.months.length + t('mon') : '');
  h += `<h2>${t('jahresvergleich')} <span class="x">${t('kumulierte_werte_spalte_0_bis', ly, MONATE[+cur.slice(5) - 1])}</span></h2><div class="wrap auto"><table><thead><tr><th>${t('position')}</th>${ycols.map(c => `<th class="year${c.plan ? ' plan' : ''}">${lab(c)}</th>`).join('')}${lytd.length ? `<th class="year">${t('0_bis_1', ly, MONATE[+cur.slice(5) - 1])}</th>` : ''}</tr></thead><tbody>`;
  const rowY = (label, fn, total) => `<tr class="${total ? 'total' : ''}"><td>${label}</td>${ycols.map(c => { const v = fn(c.months); return `<td class="${cls(v, c)}">${F0(v)}</td>`; }).join('')}${lytd.length ? `<td class="year ${(fn(lytd) || 0) < 0 ? 'neg' : 'pos'}">${F0(fn(lytd))}</td>` : ''}</tr>`;
  for (const [k, l] of [['Einnahmen', t('einnahmen')], ['Ausgaben', t('ausgaben')], ['Zinsen', t('davon_zinsen')]]) h += rowY(l, ms => sumsOf(D, k, ms));
  h += rowY(t('operatives_ergebnis'), ms => sumsOf(D, 'Operativ', ms), true);
  for (const [k, l] of [['Investitionen', t('investitionen_umschichtung')], ['Finanzierung', t('finanzierung_tilgung_zinsen')], ['Bewertung', t('bewertung_wertaenderungen')]]) h += rowY(l, ms => sumsOf(D, k, ms));
  h += rowY(t('nettovermoegensaenderung'), ms => sumsOf(D, 'Nettovermoegen_delta', ms), true);
  h += rowY(t('nettovermoegen_am_jahresende'), ms => lastOf(Object.assign({}, nw, proj ? proj.nettovermoegen : {}), ms));
  h += '</tbody></table></div>';
  // Offene Punkte + naechste Monate
  const yr = cur.slice(0, 4);
  const [ok, ob] = await Promise.all([api(`/api/transactions?year=${yr}&uncategorized=1&limit=1&entity=${S.bereich}`), api(`/api/transactions?year=${yr}&without_receipt=1&direction=out&limit=1&entity=${S.bereich}`)]);
  const lastRun = S.STATUS.letzter_lauf, items = [];
  if (lastRun && lastRun.probelauf && lastRun.vorschlaege && lastRun.vorschlaege.length) items.push(['warn', lastRun.vorschlaege.length + t('buchungsvorschlaege_warten_testmodus'), '#buchungen']);
  if (ok.treffer) items.push(['warn', ok.treffer + t('umsaetze') + yr + t('ohne_kategorie_zuordnen'), '#kategorien']);
  if ((S.DATA.konten_neu || []).length) items.push(['warn', nKonten(S.DATA.konten_neu.length) + t('ohne_bestaetigte_zuordnung_bereich_pos'), '#einrichtung/konten']);
  if (ob.treffer) items.push(['neutral', ob.treffer + t('ausgaben_3') + yr + t('ohne_beleg'), '#umsaetze?ohne_beleg=1']);
  const ue = (D.kapitalfluss.ueberleitung || {})[cur]; if (ue && Math.abs(ue.unerklaert) > 1) items.push(['warn', t('unerklaerte_vermoegensaenderung_im_lau') + F(ue.unerklaert) + t('pruefzeile'), '#kapitalfluss']);
  for (const w of (D.warnungen || []).slice(0, 6)) items.push(['warn', w, '#buchungen']);
  if (S.STATUS.update && S.STATUS.update.neuer) items.push(['info', t('update') + S.STATUS.update.verfuegbar + t('verfuegbar'), '#updates']);
  let nx = '';
  if (pm.length) {
    const sums = D.kapitalfluss.summen;
    nx = `<table class="plain"><thead><tr><th>${t('monat_2')}</th><th class="num">${t('operativ')}</th><th class="num">${t('zahlungsfluss')}</th><th class="num">${t('pos_bankguthaben')}</th></tr></thead><tbody>` + pm.slice(0, 6).map(k => `<tr><td>${ML(k)}</td><td class="num ${(sums[k]?.Operativ || 0) < 0 ? 'neg' : 'pos'}">${F0((sums[k]?.Operativ || 0) * defl(k))}</td><td class="num ${(sums[k]?.Cashflow || 0) < 0 ? 'neg' : 'pos'}">${F0((sums[k]?.Cashflow || 0) * defl(k))}</td><td class="num">${F0(proj.liquiditaet[k] * defl(k))}</td></tr>`).join('') + '</tbody></table>';
  }
  h += `<div class="grid2"><div class="card"><h3>${t('offene_punkte')}</h3>${items.length ? items.map(([k, t, href]) => `<div style="margin:4px 0"><a href="${href}" class="pill ${k}">${esc(t)}</a></div>`).join('') : `<div class="muted">${t('nichts_offen')}</div>`}</div><div class="card"><h3>${t('naechste_monate_plan')}</h3>${nx || `<div class="muted">${t('plan_unter_planung_aktivieren')}</div>`}</div></div>`;
  // andere Bereiche
  const others = Object.keys(S.DATA.bereiche).filter(k => k !== S.bereich);
  if (others.length) {
    h += `<h2>${t('weitere_bereiche')}</h2><div class="cards">` + others.map(k => { const o = S.DATA.bereiche[k]; if (o.fehler) return `<div class="card"><div class="l">${esc(BN(k))}</div><div class="v s"><span class="pill err">${t('fehler_2')}</span></div><div class="d">${esc(o.fehler)}</div></div>`;
      const om = o.monate, oc = om[om.length - 1], op = om[om.length - 2], onw = o.bilanz.nettovermoegen; const ko = o.kennzahlen || {};
      return `<div class="card clickable" data-b="${k}" style="cursor:pointer"><div class="l">${esc(BN(k))}</div><div class="v s">${F0(onw[oc])} €</div><div class="d">${t('monat_0_operativ_12_m', delta(onw[oc], onw[op]), F0(ko.operativ_12m))}</div>${sparkline(om.slice(-24).map(x => onw[x]), 'var(--c-bet)')}</div>`; }).join('') + '</div>';
  }
  return h;
}

// ---------------------------------------------------------------- Einrichtung (modular)
const MODULES = [
  {id: 'verbindung', t: t('verbindung'), d: t('moneymoney_laeuft_und_ist_entsperrt'), done: () => S.KONTEN.length > 0},
  {id: 'bereiche', t: t('bereiche'), d: t('welche_konten_gehoeren_zusammen_privat'), done: () => (S.CFG.bereiche || []).length > 0 || !!S.DATA},
  {id: 'konten', t: t('konten_2'), d: t('jedes_konto_bestaetigen_bereich_und'), done: () => !!S.DATA && !((S.DATA.konten_neu || []).length)},
  {id: 'historie', t: t('kontostaende_aus_moneymoney'), d: t('bisherigen_verlauf_aller_konten_einmal'), done: () => !!((S.STATUS || {}).moneymoney || {}).historie},
  {id: 'kategorien', t: t('kategorien_auswaehlen'), d: t('kategorien_auswaehlen_d'), done: () => !!((S.DATA && S.DATA.kategorien || {}).verwendung) || Object.keys((S.CFG.kapitalfluss || {}).kategorie_zuordnung || {}).length > 0, href: '#kategorien/auswahl', optional: true},
  {id: 'zuordnen', t: t('kategorien_zuordnen'), d: t('kontor_eigene_kategorien_baum_aus'), done: () => !!S.DATA && !(((S.DATA.kategorien || {}).gesamt || {}).ohne), href: '#kategorien', optional: true},
  {id: 'regeln', t: t('regeln_gegenbuchungen'), d: t('darlehen_spiegeln_und_verzinsen_beteil'), done: () => (S.CFG.darlehen || []).length + (S.CFG.beteiligungen || []).length + (S.CFG.saldo_spiegel || []).length > 0, href: '#regeln', optional: true},
  {id: 'immobilien', t: t('immobilien'), d: t('kalkulationen_anlegen_mit_konten_und'), done: () => (S.CFG.immobilien || []).length > 0, href: '#immobilien', optional: true},
  {id: 'planung', t: t('planung'), d: t('horizont_inflation_steigerungen_darleh'), done: () => !!S.DATA, href: '#planung', optional: true},
  {id: 'steuer', t: t('steuer'), d: t('vermietungskategorie_darlehen_objekt_a'), done: () => !!(S.CFG.steuer || {}).vermietung_kategorie, href: '#einstellungen/steuer', optional: true},
  {id: 'belege', t: t('belege_dokumente'), d: t('belegordner_und_ablagemuster_belege_zu'), done: () => !!(S.CFG.belege || {}).ordner, href: '#einstellungen', optional: true},
  {id: 'iphone', t: t('zugriff_vom_iphone'), d: t('zugriff_vom_iphone_d'), done: () => ((S.CFG.oberflaeche || {}).bind || '127.0.0.1') !== '127.0.0.1', href: '#einstellungen/zugang', optional: true},
  {id: 'betrieb', t: t('betrieb_zugang'), d: t('testmodus_automatischer_abgleich_mitte'), done: () => true, href: '#einstellungen'},
];
function vEinrichtung(sub) {
  const sh = id => `<h2 class="sub-h">${esc((MODULES.find(m => m.id === id) || {}).t || '')}</h2>`;      // gleicher Name wie im Einrichtungsplan
  if (sub === 'bereiche') return sh('bereiche') + vBereicheEditor();
  if (sub === 'konten') return sh('konten') + vKontenEditor();
  if (sub === 'verbindung') return sh('verbindung') + vVerbindung();
  if (sub === 'historie') return sh('historie') + vMMHistorie();
  const roots = S.KONTEN.filter(k => k.gruppe && k.ebene === 0);
  let h = `<div class="lang-pick"><label for="w-lang" class="small muted">${t('sprache_label')}</label><select id="w-lang">${langOpts()}</select></div><div class="note">${t('in_dieser_reihenfolge_einrichten_die', S.KONTEN.length ? roots.length + t('kontengruppen_n') + S.KONTEN.filter(k => !k.gruppe).length + t('konten_aus_moneymoney_bekannt') : t('noch_keine_konten_aus_moneymoney'))}</div><div class="setup-list">`;
  MODULES.forEach((m, i) => {
    const ok = m.done();
    h += `<div class="srow ${ok ? 'done' : ''}"><div class="n">${ok ? '✓' : i + 1}</div><div class="b"><div class="t">${esc(m.t)}<span class="pill ${ok ? 'ok' : (m.optional ? 'neutral' : 'warn')}">${ok ? t('eingerichtet') : (m.optional ? t('optional') : t('offen'))}</span></div><div class="d">${esc(m.d)}</div></div><div class="a"><a href="${m.href || ('#einrichtung/' + m.id)}"><button class="small ${ok ? 'secondary' : ''}">${ok ? t('anpassen') : t('einrichten')}</button></a></div></div>`;
  });
  h += '</div>';
  h += `<div class="actions"><button id="check-btn" class="secondary">${t('einrichtung_pruefen')}</button>${hq('pruefen')}</div><div id="findings-e" class="findings"></div>`;
  if (!S.DATA) h += `<div class="card"><h3>${t('erste_auswertung_erstellen')}</h3><div class="small muted">${t('liest_alle_umsaetze_aus_moneymoney')}</div><div class="actions"><button id="w-report" class="small">${t('auswertung_erstellen')}</button></div></div>`;
  return h;
}
function mmhStep1(st) {
  const off = !(st.moneymoney || {}).laeuft;
  return `<div class="b"><b>${t('moneymoney_beenden')}</b><span class="dot ${off ? 'ok' : 'warn'}"></span>${off ? t('moneymoney_ist_beendet') : t('in_moneymoney_q_druecken_sonst')}</div>`;
}
function vMMHistorie() {
  const st = S.STATUS, last = (st.moneymoney || {}).historie;
  if (!st.lokal) return `<div class="note">${t('nur_direkt_am_mac_moeglich')}</div>`;
  const n = x => x === 1 ? t('ein_konto_2') : x + t('konten');
  return `${last ? `<div class="banner info small">${t('uebernommen_am_0_1_2', esc(fmtZeit(last.zeit)), n(last.konten), last.von ? `${t('0_bis_1_2', ML(last.von), ML(last.bis))}` : '')}</div>` : ''}
  <div class="note">${t('kontor_uebernimmt_einmalig_den_bisheri', hq('mmhist'))}</div>
  <div class="steps">
    <div class="step ${(st.moneymoney || {}).laeuft ? '' : 'done'}" id="mmh-s1">${mmhStep1(st)}</div>
    <div class="step"><div class="b"><b>${t('datei_im_finder_zeigen')}</b>${t('kontor_oeffnet_ein_finder_fenster')}<div class="actions"><button id="mmh-zeigen" class="small">${t('im_finder_zeigen')}</button></div><div class="small muted">${t('kein_fenster_in_moneymoney_hilfe')}</div></div></div>
    <div class="step ${last ? 'done' : ''}"><div class="b"><b>${t('hierher_ziehen_passwort_eingeben')}</b>${t('danach_erscheint_ein_fenster_von')}<div class="drop" id="mmh-drop">${t('moneymoney_sqlite_hierher_ziehen')}<br><button id="mmh-pick" class="small" style="margin-top:8px">${t('datei_waehlen')}</button><input type="file" id="mmh-file" class="hidden"></div><div id="mmh-res" class="findings"></div></div></div>
    <div class="step"><div class="b"><b>${t('weiter')}</b><div class="actions"><button data-next="#kategorien" ${last ? '' : 'class="secondary"'}>${t('weiter_kategorien_amp_zuordnen')}</button><button class="secondary" data-next="#einrichtung">${t('zurueck_zur_einrichtung')}</button></div></div></div></div>`;
}
const MMH_TXT = {received: t('gleich_erscheint_das_passwortfenster_v'), password: t('bitte_im_fenster_von_macos'), decrypt: t('wird_im_arbeitsspeicher_entschluesselt'), search: t('kontostaende_werden_gesucht_und_geprue')};
async function mmhFollow() {
  // Fortschritt des Einlesens verfolgen, bis ein Ergebnis da ist
  for (;;) {
    let r; try { r = await api('/api/history/mm-status'); } catch (e) { await new Promise(ok => setTimeout(ok, 1500)); continue; }
    const res = $('#mmh-res');
    if (r.laeuft) { if (res) res.innerHTML = `<div class="working"><span class="spin"></span>${esc(MMH_TXT[r.schritt] || t('bitte_warten'))}</div>`; await new Promise(ok => setTimeout(ok, 800)); continue; }
    const e = r.ergebnis || {};
    if (e.ok) { try { S.STATUS = await api('/api/status'); statusMini(); } catch (x) {} }
    const msg = e.ok ? `${t('kontostaende_von_0_uebernommen_1', e.konten === 1 ? t('einem_konto') : e.konten + t('konten'), e.von ? ` ${t('0_bis_1_3', ML(e.von), ML(e.bis))}` : '', e.depots ? `${t('davon_0', e.depots === 1 ? t('ein_depot') : e.depots + t('depots'))}` : '')}` : (e.text || t('nicht_uebernommen'));
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
  const txt = !m.laeuft ? t('moneymoney_starten_und_entsperren_kont')
    : m.gesperrt === true ? t('moneymoney_laeuft_ist_aber_gesperrt') : t('moneymoney_laeuft_und_ist_entsperrt_2');
  return `<div class="b"><b>${t('moneymoney_laeuft')}</b><span class="dot ${!m.laeuft ? 'off' : m.gesperrt === true ? 'warn' : 'ok'}"></span>${txt}</div>`;
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
      if (bar && p.schritt && p.start) {
        const est = Object.fromEntries(READ_STEPS.map(([k, d]) => [k, (p.dauer || {})[k] || d])), idx = READ_STEPS.findIndex(([k]) => k === p.schritt);
        const inStep = Math.max(0, p.jetzt - p.seit), cur = idx >= 0 ? Math.max(est[p.schritt], inStep * 1.15) : 0;
        const total = READ_STEPS.reduce((a, [k]) => a + est[k], 0) - (idx >= 0 ? est[p.schritt] - cur : 0);
        const done = READ_STEPS.slice(0, Math.max(0, idx)).reduce((a, [k]) => a + est[k], 0) + Math.min(inStep, cur);
        bar.style.width = (p.schritt === 'done' ? 100 : Math.min(99, 100 * done / Math.max(1, total))).toFixed(1) + '%';
        if (lab) lab.textContent = (READ_LABEL[p.schritt] || t('lese_konten_und_umsaetze_aus')) + ' · ' + Math.round(p.jetzt - p.start) + ' s';
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
    <div class="step ${S.KONTEN.length ? 'done' : ''}"><div class="b"><b>${t('zugriff_erlauben_und_konten_lesen', hq('berechtigung'))}</b>${t('macos_fragt_einmal_ob_python3')}<div class="actions"><button id="w-check" class="small">${t('verbindung_pruefen')}</button></div><div id="w-busy" class="prog-wrap hidden"><div class="prog"><i id="w-prog"></i></div><span class="prog-l" id="w-prog-l">${t('lese_konten_und_umsaetze_aus')}</span></div><div id="w-findings" class="findings"></div></div></div>
    <div class="step ${S.KONTEN.length ? 'done' : ''}"><div class="b"><b>${t('weiter')}</b><div class="actions"><button data-next="#einrichtung/bereiche" ${S.KONTEN.length ? '' : 'class="secondary"'}>${t('weiter_bereiche')}</button><button class="secondary" data-next="#einrichtung">${t('zurueck_zur_einrichtung')}</button></div></div></div></div>`;
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
  let h = `<div class="note">${t('standard_jede_kontengruppe_der_oberste', hq('bereich'), S.KONTEN.length ? '' : `<b>${t('noch_keine_konten_geladen_zuerst')}</b>`)}</div><div class="list" id="bereiche">`;
  list.forEach((b, i) => { h += bereichForm(b, i); });
  h += `</div><div class="actions"><button id="add-bereich" class="secondary">${t('bereich_hinzufuegen')}</button><button id="save-bereiche" class="secondary">${t('speichern')}</button><button data-savenext="#einrichtung/konten" data-save="bereiche">${t('speichern_und_weiter_konten')}</button><button class="secondary" data-next="#einrichtung">${t('zurueck_zur_einrichtung')}</button></div><div id="findings-b" class="findings"></div>`;
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
    rows.push(`<label class="chk small ${implied ? 'implied' : ''}" style="padding-left:${k.ebene * 14}px"><input type="checkbox" class="b-k" data-ebene="${k.ebene}" data-gruppe="${k.gruppe ? 1 : 0}" value="${k.uuid} | ${esc(k.name)}" ${checked ? 'checked' : ''} ${implied ? 'disabled' : ''}> ${esc(k.name)}${k.gruppe ? ` <span class="muted">${t('gruppe_mit_allen_konten_darunter')}</span>` : ''}</label>`);
  }
  return `<div class="item" data-i="${i}"><div class="grow"><div class="form">
    <label>${t('name')}</label><input type="text" class="b-name" value="${esc(b.name || '')}">
    <input type="hidden" class="b-id" value="${esc(b.id || '')}">
    <label>${t('art')}</label><select class="b-art"><option value="privat" ${art === 'privat' ? 'selected' : ''}>${t('privat')}</option><option value="gesellschaft" ${art === 'gesellschaft' ? 'selected' : ''}>${t('gesellschaft_gbr_gmbh')}</option></select>
    <label>${t('hauptbereich_0', hq('haupt'))}</label><label class="chk"><input type="radio" name="b-haupt" class="b-haupt" ${b.haupt ? 'checked' : ''}> ${b.haupt ? t('ja') : t('nein')}</label>
    <label class="b-anteil-row ${art === 'privat' ? 'hidden' : ''}">${t('anteil_0', hq('anteil'))}</label><div class="row tight b-anteil-row ${art === 'privat' ? 'hidden' : ''}"><input type="number" step="0.01" min="0" max="100" class="b-anteil" value="${pct}" placeholder="${regel != null ? Math.round(regel * 10000) / 100 : '100'}" style="width:110px"> %${regel != null && pct === '' ? `<span class="small muted">${t('vorschlag_aus_der_beteiligungsregel_0', Math.round(regel * 10000) / 100)}</span>` : ''}</div>
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
  let h = `<div class="note">${t('jedes_konto_gehoert_zu_einem', hq('konten_zuordnung'))}</div>
  ${neu.length ? `<div class="banner info">${t('0_noch_nicht_bestaetigt_1', nKonten(neu.length), esc(neu.slice(0, 6).map(k => k.name).join(', ')), neu.length > 6 ? ' …' : '')}</div>` : ''}
  <div class="row tight"><label>${t('nach_aktivitaet_ausblenden_ohne_bestan')} <input type="number" id="k-inaktiv" min="0" value="${cfg.bilanz.inaktiv_monate ?? 12}" style="width:70px"> ${t('monaten_0', hq('inaktiv'))}</label><label class="switch"><input type="checkbox" id="k-show-inactive" checked><i></i>${t('ausgeblendete_hier_zeigen')}</label></div>
  <div class="wrap auto"><table class="plain acct-table"><thead><tr><th>${t('konto_2')}</th><th>${t('bereich_0', hq('bereich'))}</th><th>${t('position_0', hq('position_kurz'))}</th><th>${t('verlauf_0', hq('verlauf_kurz'))}</th><th>${t('anzeige_0', hq('anzeige'))}</th><th class="num">${t('saldo')}</th></tr></thead><tbody>`;
  // Reihenfolge: Bereiche wie unter „Bereiche“ angeordnet, darin die Konten wie in MoneyMoney; ohne Bereich zum Schluss
  const zuOf = k => ((cfg.bilanz.konten_zuordnung || {})[k.uuid + ' | ' + k.name]) || Object.entries(cfg.bilanz.konten_zuordnung || {}).find(([r]) => r.split('|')[0].trim() === k.uuid)?.[1] || {};
  const bIdx = Object.fromEntries(bereiche.map(([id], i) => [id, i]));
  const rows = leaves.map((k, i) => ({k, i, bsel: zuOf(k).bereich || k.bereich_id || ''})).sort((a, b) => ((bIdx[a.bsel] ?? 1e6) - (bIdx[b.bsel] ?? 1e6)) || a.i - b.i);
  let lastB = null;
  for (const {k, bsel} of rows) {
    if (bsel !== lastB) { lastB = bsel; h += `<tr class="bgroup"><td colspan="6">${esc((bereiche.find(([id]) => id === bsel) || [null, t('ohne_bereich')])[1])}</td></tr>`; }
    const cur = roleOf(k.uuid), ver = verOf(k.uuid);
    const vis = hide.has(k.uuid) ? 'hide' : show.has(k.uuid) ? 'show' : '', grenze = k.aktiv_grenze ?? (k.inaktiv_auto ? 9999 : 0), auto = autoHidden(grenze, cfg.bilanz.inaktiv_monate ?? 12);
    const rolle = cur || k.rolle || 'sonstiges', quelle = ver || k.verlauf || (k.depot ? 'stand' : 'umsaetze');
    // Vorschlag (was Kontor aus Name, Typ und Gruppe erkennt) steht in der Liste mit „(Vorschlag)“; gestrichelt = Vorschlag gewählt
    const sv = k.rolle_vorschlag || rolle, vv = k.depot ? 'stand' : 'umsaetze';
    const dash = (cur, v) => cur === v ? ' vorschlag' : '';
    h += `<tr data-uuid="${k.uuid}" data-ref="${k.uuid} | ${esc(k.name)}" data-auto="${auto ? 1 : 0}" data-grenze="${grenze}" class="${kontoHidden(vis, auto) ? 'inactive' : ''}${k.bestaetigt ? '' : ' neu'}"><td title="${esc(k.pfad)}">${esc(k.name)}${k.bestaetigt ? '' : `<span class="tag warn">${t('neu')}</span>`}<span class="tag k-vis">${t('ausgeblendet')}</span>${k.veraltet ? `<span class="tag warn" title="${t('saldo_0_aber_seit_1', F(k.saldo), esc(k.letzte_buchung || k.aktualisiert || t('jeher')))}">${t('veraltet')}</span>` : ''}<div class="small muted">${esc(k.pfad.split(' / ').slice(0, -1).join(' / '))} · ${k.depot ? t('depot') : (k.manuell || k.abruf === 'offline') ? t('manuell') : esc(k.typ || t('bank'))}</div></td><td><select class="k-bereich"><option value="">${t('keiner')}</option>${bereiche.map(([id, n]) => `<option value="${esc(id)}" ${bsel === id ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></td>
      <td><select class="k-rolle${dash(rolle, sv)}" data-vor="${sv}">${ROLE_OPTS.map(([v, l]) => `<option value="${v}" ${rolle === v ? 'selected' : ''}>${l}${v === sv ? ` (${t('vorschlag')})` : ''}</option>`).join('')}</select></td>
      <td class="nowrap"><select class="k-verlauf${dash(quelle, vv)}" data-vor="${vv}">${[['umsaetze', t('umsaetze_2')], ['stand', t('kontostaende')]].map(([v, l]) => `<option value="${v}" ${quelle === v ? 'selected' : ''}>${l}${v === vv ? ` (${t('vorschlag')})` : ''}</option>`).join('')}</select> <button class="ghost small k-hist" title="${t('monatsstaende_ansehen_und_bearbeiten')}">${t('verlauf')}</button></td>
      <td><select class="k-show" title="${auto ? t('kein_bestand_und_kein_umsatz') + (cfg.bilanz.inaktiv_monate ?? 12) + t('monaten') : t('mit_bestand_oder_umsatz_in') + (cfg.bilanz.inaktiv_monate ?? 12) + t('monaten')}"><option value="">${t('nach_aktivitaet')}</option><option value="show" ${vis === 'show' ? 'selected' : ''}>${t('immer_anzeigen')}</option><option value="hide" ${vis === 'hide' ? 'selected' : ''}>${t('ausblenden')}</option></select></td>
      <td class="num ${(k.saldo || 0) < 0 ? 'neg' : 'pos'}">${F(k.saldo)}</td></tr>`;
  }
  h += `</tbody></table></div><div class="actions"><button id="save-konten" class="secondary">${t('speichern')}</button><button data-savenext="#einrichtung/historie" data-save="konten">${t('speichern_und_weiter_kontostaende_aus')}</button><button class="secondary" data-next="#einrichtung">${t('zurueck_zur_einrichtung')}</button></div><div id="findings-k2" class="findings"></div>`;
  h += `<h2>${t('saldenverlauf_importieren_0', hq('verlauf_import'))}</h2><div class="note">${t('fuer_depots_und_konten_ohne')}</div>
    <div class="drop" id="hi-drop">${t('datei_hierher_ziehen')}<br><button id="hi-pick" class="small" style="margin-top:8px">${t('datei_waehlen')}</button></div><div id="hi-preview"></div>`;
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
  const opts = sel => `<option value="">${t('nicht_uebernehmen')}</option>` + leaves.map(k => `<option value="${k.uuid} | ${esc(k.name)}" ${sel === k.uuid ? 'selected' : ''}>${esc(k.name)}${k.depot ? t('depot_2') : ''}${k.verlauf === 'stand' ? t('kontostaende_2') : ''}</option>`).join('');
  el.innerHTML = `<div class="card" style="margin-top:12px"><h3>${esc(HI.name)} <span class="muted">${t('0_spalten_konten_erkannt_1', HI.vorschau.length, HI.hinweise.length ? ' · ' + esc(HI.hinweise.join(' ')) : '')}</span></h3>
    <div class="wrap auto"><table class="plain"><thead><tr><th>${t('in_der_datei')}</th><th class="num">${t('monate')}</th><th>${t('zeitraum')}</th><th>${t('konto_in_kontor')}</th></tr></thead><tbody>${HI.vorschau.map(v => `<tr data-name="${esc(v.name)}"><td>${esc(v.name)}</td><td class="num">${v.anzahl}</td><td class="small">${v.von} – ${v.bis}</td><td><select class="hi-map">${opts(v.uuid)}</select>${v.uuid && !v.sicher ? ` <span class="tag" title="${t('automatisch_zugeordnet_pruefen')}">${t('vorschlag')}</span>` : ''}</td></tr>`).join('')}</tbody></table></div>
    <div class="row tight" style="margin-top:8px"><label class="chk"><input type="checkbox" id="hi-gaps" checked> ${t('nur_monate_uebernehmen_fuer_die')}</label><button id="hi-import" class="small">${t('uebernehmen')}</button><span class="small muted">${t('ohne_zuordnung_bleibt_eine_zeile')}</span></div><div id="hi-report" class="findings"></div></div>`;
  $('#hi-import').onclick = async () => {
    const zuordnung = {}; $$('#hi-preview tr[data-name]').forEach(tr => { zuordnung[tr.dataset.name === t('s_ohne_konto') ? '' : tr.dataset.name] = $('.hi-map', tr).value; });
    try { const r = await api('/api/history/import', {datei: HI.b64, name: HI.name, zuordnung, uebernehmen: true, nur_luecken: $('#hi-gaps').checked}); showFindings($('#hi-report'), [], r.uebernommen + t('monatswerte_fuer') + (r.konten === 1 ? t('ein_konto_2') : r.konten + t('konten')) + t('uebernommen') + (r.bericht ? t('bericht_aktualisiert') : '.'), 'ok'); await loadAll(); } catch (e) { showFindings($('#hi-report'), [], e.message, 'fehler'); }
  };
}
function kontoHidden(vis, auto) { return vis === 'hide' || (vis === '' && !!auto); }
function autoHidden(grenze, n) { n = +n || 0; return n > 0 && n <= (+grenze || 0); }      // "nach Aktivität": ohne Bestand und Umsatz seit N Monaten
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
function holdingsBox(uuid) {
  // Depot: Positionen aus MoneyMoney (Stand des letzten Lesens), aufklappbar oben im Verlaufsfenster
  const d = ((S.DATA && S.DATA.depots) || []).find(x => x.konto === uuid); if (!d || !d.positionen.length) return '';
  const gv = d.einstand ? d.summe - d.einstand : null;
  return `<details class="holdings"><summary>${t('0_positionen', d.positionen.length)} · ${F0(d.summe)} €${gv != null ? ` · <span class="${gv >= 0 ? 'pos' : 'neg'}">${gv >= 0 ? '+' : ''}${F0(gv)} € (${((d.summe / d.einstand - 1) * 100).toFixed(1)} %)</span>` : ''}</summary>
    <div class="small muted" style="margin:4px 0">${t('bestaende_aus_moneymoney_stand_des')} ${xlsxBtn('holdings')}</div>
    <table class="plain small"><thead><tr><th>${t('position')}</th><th class="num">${t('menge')}</th><th class="num">${t('wert')}</th><th class="num">G/V</th></tr></thead><tbody>`
    + d.positionen.map(p => `<tr><td title="${esc([p.isin, p.klasse].filter(Boolean).join(' · '))}">${esc(p.name)}</td><td class="num">${p.menge.toLocaleString(LOCALE, {maximumFractionDigits: 4})}</td><td class="num">${F(p.wert)}</td><td class="num ${p.wert - p.einstand >= 0 ? 'pos' : 'neg'}">${p.einstand ? F(p.wert - p.einstand) : ''}</td></tr>`).join('')
    + '</tbody></table></details>';
}
async function openHistDrawer(uuid, vorschau) {
  // vorschau: Verlaufsquelle, die erst angezeigt und mit „Speichern“ übernommen wird (z. B. aus der Kontentabelle)
  const r = await api('/api/history?account=' + encodeURIComponent(uuid) + (vorschau ? '&source=' + vorschau : ''));
  const k = S.KONTEN.find(x => x.uuid === uuid) || {name: r.name || uuid};
  const d = $('#drawer');
  HD.uuid = uuid; HD.live = r.live;
  d.innerHTML = `<button class="close icon">✕</button><h2>${esc(k.name || r.name)}</h2>${holdingsBox(uuid)}
    <div class="row tight"><span class="small muted">${t('verlauf_aus_0', hq('verlauf'))}</span><div class="seg" id="hq-seg"><button class="hq-q" data-q="umsaetze">${t('umsaetze_2')}</button><button class="hq-q" data-q="stand">${t('kontostaenden')}</button></div></div>
    <div class="small muted" id="hq-erkl" style="margin:4px 0 8px"></div>
    <div id="hq-hinweis"></div><div id="hq-pending"></div>
    <div class="h-chart" id="h-chart"></div>
    <h3>${t('monatsstaende')}</h3>
    <div class="row tight" id="h-addrow"><input type="month" id="h-von" style="width:140px"><button id="h-add" class="small secondary">${t('monat_ergaenzen')}</button></div>
    <div class="hist-grid" id="h-grid"></div>
    <div class="actions" id="h-actions"><button id="h-save" class="small">${t('speichern')}</button><button id="h-undo" class="small secondary hidden">${t('verwerfen')}</button><button id="h-clear" class="small secondary">${t('alle_eigenen_werte_loeschen')}</button></div>
    <div id="h-importbox"><h3>${t('import_aus_saldenexport')}</h3><div class="small muted">${t('csv_mit_datum_saldo_ein')}</div>
    <textarea id="h-csv" placeholder="${t('datum_saldo_31_12_2024')}"></textarea><div class="actions"><button id="h-import" class="small secondary">${t('vorschau')}</button><button id="h-import2" class="small hidden">${t('uebernehmen')}</button></div><div id="h-prev" class="findings"></div></div>`;
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
  $('#h-add', d).onclick = () => {
    // eingegebenen Monat hinzufuegen (gibt es ihn schon, wird sein Feld gewaehlt); Liste bleibt nach Monaten sortiert
    const mk = $('#h-von', d).value; if (!/^\d{4}-\d{2}$/.test(mk)) return;
    const have = $(`#h-grid input[data-mk="${mk}"]`, d); if (have) { have.focus(); return; }
    const next = $$('#h-grid input', d).find(i => i.dataset.mk > mk), html = `<label>${ML(mk)}<input type="text" data-mk="${mk}" class="auto" value=""></label>`;
    if (next) next.parentNode.insertAdjacentHTML('beforebegin', html); else $('#h-grid', d).insertAdjacentHTML('beforeend', html);
    $(`#h-grid input[data-mk="${mk}"]`, d).focus();
  };
  $('#h-save', d).onclick = async () => {
    const werte = {}; if (HD.r.quelle === 'stand') $$('#h-grid input', d).forEach(i => { if (!i.classList.contains('auto') || i.value.trim()) werte[i.dataset.mk] = i.value.trim() === '' ? null : i.value.trim(); });
    const body = {konto: uuid, werte}; if (HD.r.quelle !== HD.r.quelle_gespeichert) body.quelle = HD.r.quelle;
    try {
      const res = await api('/api/history', body); renderHist(res.historie); toast(t('gespeichert'));
      if (body.quelle) { S.CFG = await api('/api/config'); const sel = $(`tr[data-uuid="${uuid}"] .k-verlauf`); if (sel) { sel.value = body.quelle; sel.classList.toggle('vorschlag', sel.value === sel.dataset.vor); } }
    } catch (e) { toast(e.message, 6000); }
  };
  $('#h-clear', d).onclick = async () => { if (!confirm(t('alle_eigenen_monatswerte_dieses_kontos'))) return; try { const res = await api('/api/history', {konto: uuid, werte: {}, loeschen: true}); renderHist(res.historie); } catch (e) { toast(e.message, 6000); } };
  $('#h-import', d).onclick = async () => { try { const r2 = await api('/api/history/import', {konto: uuid, csv: $('#h-csv', d).value}); $('#h-prev', d).innerHTML = r2.vorschau.map(v => `<div class="${v.uuid ? 'ok' : 'warnung'}">${t('0_1_monate_2_3', esc(v.name), v.anzahl, v.von, v.bis, v.uuid ? '' : t('kein_konto_zugeordnet'))}</div>`).join(''); $('#h-import2', d).classList.remove('hidden'); } catch (e) { $('#h-prev', d).innerHTML = `<div class="fehler">${esc(e.message)}</div>`; } };
  $('#h-import2', d).onclick = async () => { try { const r2 = await api('/api/history/import', {konto: uuid, csv: $('#h-csv', d).value, uebernehmen: true}); toast(r2.uebernommen + t('werte_uebernommen')); S.CFG = await api('/api/config'); const sel = $(`tr[data-uuid="${uuid}"] .k-verlauf`); if (sel) sel.value = 'stand'; await openHistDrawer(uuid); } catch (e) { toast(e.message, 6000); } };
}
function renderHist(r) {
  // Fensterinhalt aus der Vorschau des Dienstes (fuer dieses eine Konto sofort gerechnet)
  const d = $('#drawer'); if (!d.classList.contains('open')) return;
  HD.r = r; HD.live = r.live;
  const stand = r.quelle === 'stand';
  $$('.hq-q', d).forEach(x => x.classList.toggle('on', x.dataset.q === r.quelle));
  $('#hq-erkl', d).textContent = stand
    ? (r.depot ? t('letzter_bekannter_kontostand_gilt_depo')
               : t('eingetragene_kontostaende_sind_massgeb'))
    : t('saldo_am_monatsende_heutiger_saldo');
  const P = r.pruefung || {}, infos = [];
  if (r.hinweis) infos.push(r.hinweis.replace(/^'[^']*': /, ''));
  if (!stand && P.erste_buchung && Math.abs(P.anfangssaldo || 0) > 0.005) infos.push(`${t('moneymoney_hat_umsaetze_erst_ab', P.erste_buchung.slice(8, 10), P.erste_buchung.slice(5, 7), P.erste_buchung.slice(0, 4), F(P.anfangssaldo))}`);
  if (!stand && !P.buchungen && !r.depot) infos.push(t('keine_umsaetze_in_moneymoney_der'));
  if (P.vorgemerkt_anzahl) infos.push(`${t('0_vorgemerkte_umsaetze_zusammen_1', P.vorgemerkt_anzahl, F(P.vorgemerkt_summe))}`);
  if (!r.live) infos.push(t('noch_kein_moneymoney_stand_im'));
  $('#hq-hinweis', d).innerHTML = infos.map(t => `<div class="banner info small">${esc(t)}</div>`).join('');
  const pending = r.quelle_gespeichert && r.quelle !== r.quelle_gespeichert;
  $('#hq-pending', d).innerHTML = pending ? `<div class="banner small">${t('vorschau_verlauf_aus_0_gespeichert', r.quelle === 'stand' ? t('kontostaenden') : t('umsaetzen'), r.quelle_gespeichert === 'stand' ? t('kontostaende') : t('umsaetze_2'))}</div>` : '';
  const werte = r.werte || {}, man = r.manuell || {};
  const months = Object.keys(Object.assign({}, werte, man)).sort();
  const anker = new Set(r.anker || []);
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
function histChart(pts) {
  // Verlauf des Kontos im Fenster: Monatsend-Staende als Linie mit Flaeche, Nulllinie, Jahre unten
  if (pts.length < 2) return '';
  const W = 420, H = 130, P = {l: 46, r: 6, t: 8, b: 18}, n = pts.length - 1, vals = pts.map(p => p[1]);
  let max = Math.max(...vals, 0), min = Math.min(...vals, 0); if (max === min) max = min + 1;
  const x = i => P.l + i * (W - P.l - P.r) / n, y = v => P.t + (max - v) * (H - P.t - P.b) / (max - min), f = v => v.toFixed(1);
  let g = '';
  for (const tk of niceTicks(min, max, 3)) g += `<line class="bch-grid${Math.abs(tk) < 1e-9 ? ' zero' : ''}" x1="${P.l}" x2="${W - P.r}" y1="${f(y(tk))}" y2="${f(y(tk))}"/><text class="bch-y" x="${P.l - 5}" y="${f(y(tk) + 4)}">${Fk(tk)}</text>`;
  const every = Math.max(1, Math.ceil(pts.length / 12 / 6));
  pts.forEach(([mk], i) => { if (mk.endsWith('-01') && (+mk.slice(0, 4)) % every === 0 && x(i) > P.l + 10 && x(i) < W - 14) g += `<line class="bch-year" x1="${f(x(i))}" x2="${f(x(i))}" y1="${P.t}" y2="${H - P.b}"/><text class="bch-x" x="${f(x(i))}" y="${H - 4}">${mk.slice(0, 4)}</text>`; });
  const line = pts.map((p, i) => (i ? 'L' : 'M') + f(x(i)) + ' ' + f(y(p[1]))).join('');
  g += `<path class="h-area" d="${line}L${f(x(n))} ${f(y(0))}L${f(x(0))} ${f(y(0))}Z"/><path class="h-line" d="${line}"/>`;
  return `<svg viewBox="0 0 ${W} ${H}" class="h-svg">${g}<g class="h-hover"></g></svg>`;
}
function bindHistChart(box, pts) {
  // Zeigen: Stand zum Monat unter dem Zeiger (Linie, Punkt, Monat und Betrag)
  const svg = $('svg', box); if (!svg || pts.length < 2) return;
  const W = 420, H = 130, P = {l: 46, r: 6, t: 8, b: 18}, n = pts.length - 1, vals = pts.map(p => p[1]);
  let max = Math.max(...vals, 0), min = Math.min(...vals, 0); if (max === min) max = min + 1;
  const x = i => P.l + i * (W - P.l - P.r) / n, y = v => P.t + (max - v) * (H - P.t - P.b) / (max - min), hv = $('.h-hover', svg);
  svg.addEventListener('pointermove', e => {
    const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * W / r.width, i = Math.max(0, Math.min(n, Math.round((px - P.l) * n / (W - P.l - P.r))));
    const [mk, v] = pts[i], xi = x(i), right = xi > W * 0.6, lab = `${ML(mk)}: ${F(v)}`;
    hv.innerHTML = `<line class="bch-cross" x1="${xi.toFixed(1)}" x2="${xi.toFixed(1)}" y1="${P.t}" y2="${H - P.b}"/><circle class="bch-dot" cx="${xi.toFixed(1)}" cy="${y(v).toFixed(1)}" r="3.5"/>`
      + `<text class="h-lab" x="${(right ? xi - 6 : xi + 6).toFixed(1)}" y="${P.t + 10}" text-anchor="${right ? 'end' : 'start'}">${esc(lab)}</text>`;
  });
  svg.addEventListener('pointerleave', () => { hv.innerHTML = ''; });
}
const HD = {uuid: null, live: false, r: null};
function openTransitDrawer() {
  // Geldtransit: die erkannten Umbuchungen, deren Ab- und Gutschrift in verschiedene Monate fallen
  const r = ((B() || {}).bilanz || {zeilen: []}).zeilen.find(x => x.transit); if (!r) return;
  const list = (r.umbuchungen || []).slice().reverse(), d = $('#drawer');
  d.innerHTML = `<button class="close icon">✕</button><h2>${esc(r.name)}</h2><div class="note">${t('geld_unterwegs_tip')}</div>
    <div class="wrap auto"><table class="plain small"><thead><tr><th>${t('abgebucht')}</th><th>${t('gutgeschrieben')}</th><th class="num">${t('betrag')}</th></tr></thead><tbody>`
    + list.map(u => `<tr><td>${FD(u.ab)}<div class="muted">${esc(u.von)}</div></td><td>${FD(u.an)}<div class="muted">${esc(u.nach)}</div></td><td class="num">${F(u.betrag)}</td></tr>`).join('')
    + `</tbody></table></div>`;
  d.classList.add('open');
  $('.close', d).onclick = closeDrawer;
}
const drawerDirty = () => $$('#drawer #h-grid input:not(.auto)').some(i => i.value !== i.defaultValue) || !!($('#drawer #h-csv') && $('#drawer #h-csv').value.trim());

// ---------------------------------------------------------------- Bilanz
function vBilanz() {
  // Eine Tabelle: Positionen (farbig, aufklappbar) mit ihren Konten; Plan-Spalten rechts angehängt
  const D = B(); if (!D) return noData;
  const C = cols();
  const pr = D.bilanz.projektion || null;
  const proj = pr ? Object.fromEntries(pr.zeilen.map(r => [r.id, r.werte])) : {};
  const W = new Map(), werte = r => { if (!W.has(r.id)) W.set(r.id, proj[r.id] ? Object.assign({}, r.werte, proj[r.id]) : r.werte); return W.get(r.id); };
  const nw = pr ? Object.assign({}, D.bilanz.nettovermoegen, pr.nettovermoegen) : D.bilanz.nettovermoegen;
  const nInactive = (D.konten_inaktiv || []).length;
  const pos = D.bilanz.zeilen.filter(r => r.gruppe);
  S.posOpen = S.posOpen || {};
  const allOpen = pos.length && pos.every(r => S.posOpen[r.rolle]);
  let h = `<div class="toolbar">${viewCtl()}<span class="tb-sep"></span><button class="ghost small" id="pos-all">${allOpen ? t('alle_zuklappen') : t('alle_aufklappen')}</button>${alleCtl(nInactive)} ${hq('bilanz_stand')}<span class="sp"></span>${xlsxBtn('balance')}</div>`;
  h += vBilanzChart(D);
  const tag = r => (r.depot ? `<span class="tag">${t('depot')}</span>` : '') + (r.offline && !r.gruppe ? `<span class="tag">${t('manuell')}</span>` : '') + (r.inaktiv ? `<span class="tag">${t('ausgeblendet')}</span>` : '')
    + (r.verlauf === 'stand' && !r.gruppe ? `<span class="tag" title="${t('verlauf_aus_kontostaenden')}">${t('kontostaende')}</span>` : '')
    + (r.fortgeschrieben_vor ? `<span class="tag warn" title="${t('vor_0_ist_kein_stand', ML(r.fortgeschrieben_vor))}">${t('vor_0_unbekannt', ML(r.fortgeschrieben_vor))}</span>` : '');
  const row = (r, cls0, label) => `<tr class="${cls0}" data-id="${r.id}"><td title="${esc(r.pfad || r.name)}">${label}</td>${C.map(c => { const v = lastOf(werte(r), c.months); return `<td class="${cls(v, c)}">${F(v)}</td>`; }).join('')}</tr>`;
  const skip = r => !S.alle && (r.inaktiv || C.every(c => { const v = lastOf(werte(r), c.months); return v == null || Math.abs(v) < 0.005; }));
  h += '<div class="wrap"><table>' + thead(t('position_konto'), C) + '<tbody>';
  for (const r of D.bilanz.zeilen) {
    if (r.gruppe) {
      const [label, color] = ROLE[r.rolle] || [r.name, 'var(--c-neutral)'], open = !!S.posOpen[r.rolle];
      h += row(r, 'group pos', `<span class="caret">${open ? '▾' : '▸'}</span><i class="pos-dot" style="background:${color}"></i>${label} <span class="small muted">(${r.anzahl}${r.inaktive ? t('n_ausgeblendet', r.inaktive) : ''})</span>`).replace('<tr ', `<tr data-pos="${r.rolle}" `).replace(` data-id="${r.id}"`, '');
      continue;
    }
    if (!S.posOpen[r.rolle] || skip(r)) continue;
    if (r.transit) { h += row(r, 'ind1 transit clickable', `${esc(r.name)} ${hq('geld_unterwegs')}`); continue; }
    h += row(r, 'clickable acct ind1', esc(r.name) + tag(r));
    if (pr && r.rolle === 'beteiligungen' && proj.einlagen && r === D.bilanz.zeilen.filter(x => !x.gruppe && x.rolle === 'beteiligungen').slice(-1)[0])
      h += row({id: 'einlagen', name: t('einlagen_entnahmen_kumuliert_plan'), werte: {}}, 'ind1 muted', t('einlagen_entnahmen_beteiligungen_kumul'));
  }
  h += `<tr class="total"><td>${t('nettovermoegen')}</td>${cells(C, c => lastOf(nw, c.months))}</tr>`;
  h += (D.bilanz.ausserhalb || []).map(r => `<tr class="muted"><td>${esc(r.name)} <span class="tag">${t('0_nicht_im_nettovermoegen', esc((ROLE[r.rolle] || [r.rolle])[0]))}</span></td>${cells(C, c => lastOf(r.werte, c.months))}</tr>`).join('');
  h += '</tbody></table></div>';
  h += `<div class="note">${t('klick_auf_eine_position_klappt')}</div>`;
  return h;
}

// ---------------------------------------------------------------- Bilanz-Grafik (Zusammensetzung im Zeitverlauf)
const MONATE_LANG = LANG === 'en' ? ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
  : ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
const BCH = {d: null, i0: 0, i1: 0, drag: null, hover: null, ro: null};
function bchData(D) {
  // Positionen (Farben wie in der Tabelle), Ist + Plan; aufgeklappte Positionen zeigen ihre Konten (Abstufungen der Farbe)
  const pr = D.bilanz.projektion || null, proj = pr ? Object.fromEntries(pr.zeilen.map(r => [r.id, r.werte])) : {};
  const months = [...D.monate, ...(pr ? (D.plan_monate || []) : [])];
  const vals = r => { const w = Object.assign({}, r.werte, proj[r.id] || {}); return months.map(m => w[m] == null ? null : w[m] * defl(m)); };
  const series = [];
  for (const r of D.bilanz.zeilen.filter(x => x.gruppe && ROLE[x.rolle])) {
    const [label, color] = ROLE[r.rolle];
    const accs = (S.posOpen || {})[r.rolle] ? D.bilanz.zeilen.filter(x => !x.gruppe && x.rolle === r.rolle) : [];
    if (accs.length) accs.forEach((a, i) => series.push({rolle: r.rolle, label: a.name, color, op: [1, .7, .5, .36, .26][i % 5], sub: true, vals: vals(a)}));
    else series.push({rolle: r.rolle, label, color, op: 1, vals: vals(r)});
  }
  const nwAll = pr ? Object.assign({}, D.bilanz.nettovermoegen, pr.nettovermoegen) : D.bilanz.nettovermoegen;
  return {months, ist: D.monate.length, series: series.filter(x => x.vals.some(v => v != null && Math.abs(v) >= 0.5)), nw: months.map(m => nwAll[m] == null ? null : nwAll[m] * defl(m))};
}
function vBilanzChart(D) {
  const d = bchData(D); if (d.months.length < 2 || !d.series.length) return '';
  BCH.d = d;
  // Ausschnitt (als Monate gemerkt, damit er Neuaufbau und Bereichswechsel uebersteht)
  const r = S.bchRange, n = d.months.length;
  let i0 = r ? d.months.indexOf(r[0]) : -1, i1 = r ? d.months.indexOf(r[1]) : -1;
  if (i0 < 0 || i1 <= i0) { [i0, i1] = bchWindow(d, 12); S.bchRange = [d.months[i0], d.months[i1]]; S.bchBtn = 12; }    // Standard: 1 Jahr
  BCH.i0 = BCH.f0 = i0; BCH.i1 = BCH.f1 = i1;
  const rb = [[12, t('bch_jahre', 1)], [36, t('bch_jahre', 3)], [120, t('bch_jahre', 10)], [0, t('alle')]];
  return `<div class="card bch" id="bch"><div class="bch-head"><span class="bch-range" id="bch-range"></span> ${hq('bch')}<span class="sp"></span><label class="bch-n" title="${t('bch_monate_tip')}"><input type="number" id="bch-n" min="3" max="${n}" step="1">${t('bch_m')}</label><div class="seg small" id="bch-rb">${rb.map(([m, l]) => `<button data-m="${m}">${l}</button>`).join('')}</div></div>
    <div class="bch-plot" id="bch-plot"><svg class="bch-svg" id="bch-svg"></svg><div class="bch-tip hidden" id="bch-tip"></div></div></div>`;
}
function bchDraw() {
  const box = $('#bch-plot'), svg = $('#bch-svg'), d = BCH.d; if (!box || !svg || !d) return;
  const W = Math.max(320, box.clientWidth), H = window.matchMedia('(max-width:820px)').matches ? 200 : 250, P = {l: 58, r: 10, t: 14, b: 24};
  const i0 = BCH.i0, i1 = BCH.i1, n = i1 - i0;
  // Stapel: positive Anteile von der Nulllinie nach oben, negative nach unten (Reihenfolge wie die Tabelle von oben)
  const pos = [], neg = [];
  for (let i = i0; i <= i1; i++) { let up = 0, dn = 0; for (const x of d.series) { const v = x.vals[i] || 0; if (v > 0) up += v; else dn += v; } pos.push(up); neg.push(dn); }
  const nwv = d.nw.slice(i0, i1 + 1).filter(v => v != null);
  let max = Math.max(...pos, ...nwv, 0), min = Math.min(...neg, ...nwv, 0); if (max === min) max = min + 1;
  const pad = (max - min) * 0.04; max += pad; if (min < 0) min -= pad;
  const x = i => P.l + (i - i0) * (W - P.l - P.r) / Math.max(1, n), y = v => P.t + (max - v) * (H - P.t - P.b) / (max - min);
  const pf = v => v.toFixed(1);
  let g = `<rect class="bch-bg" x="${P.l}" y="${P.t}" width="${W - P.l - P.r}" height="${H - P.t - P.b}"/>`;
  for (const t of niceTicks(min, max, H < 220 ? 4 : 5)) g += `<line class="bch-grid${Math.abs(t) < 1e-9 ? ' zero' : ''}" x1="${P.l}" x2="${W - P.r}" y1="${pf(y(t))}" y2="${pf(y(t))}"/><text class="bch-y" x="${P.l - 6}" y="${pf(y(t) + 4)}">${Fk(t)}</text>`;
  // Zeitachse: Abstand der Beschriftungen passt sich dem Ausschnitt an (Monate bis Jahrzehnte)
  const ppm = (W - P.l - P.r) / Math.max(1, n), step = [1, 2, 3, 6, 12, 24, 60, 120].find(st => st * ppm >= 62) || 120;
  for (let i = i0; i <= i1; i++) {
    const m = d.months[i], mo = +m.slice(5), yr = +m.slice(0, 4), xi = pf(x(i));
    if (mo === 1 && i > i0) g += `<line class="bch-year" x1="${xi}" x2="${xi}" y1="${P.t}" y2="${H - P.b}"/>`;
    if (ppm >= 5) g += `<line class="bch-tick" x1="${xi}" x2="${xi}" y1="${H - P.b}" y2="${H - P.b + (mo === 1 ? 5 : 3)}"/>`;
    const lab = step < 12 ? (mo - 1) % step === 0 : mo === 1 && yr % (step / 12) === 0;
    if (lab && x(i) > P.l + 14 && x(i) < W - P.r - 14) g += `<text class="bch-x" x="${xi}" y="${H - 6}">${step < 12 ? (mo === 1 ? yr : MONATE[mo - 1] + ' ' + String(yr).slice(2)) : yr}</text>`;
  }
  // Flaechen
  const band = (sel, sign) => {
    const base = Array(n + 1).fill(0); let out = '';
    for (const sx of sel) {
      const top = [], bot = [];
      for (let k = 0; k <= n; k++) { const v = sx.vals[i0 + k] || 0, part = sign > 0 ? Math.max(0, v) : Math.min(0, v); bot.push(base[k]); base[k] += part; top.push(base[k]); }
      if (top.every((t, k) => Math.abs(t - bot[k]) < 0.5)) continue;
      const path = top.map((t, k) => (k ? 'L' : 'M') + pf(x(i0 + k)) + ' ' + pf(y(t))).join('') + bot.map((b, k) => [k, b]).reverse().map(([k, b]) => 'L' + pf(x(i0 + k)) + ' ' + pf(y(b))).join('') + 'Z';
      out += `<path class="bch-area${sx.sub ? ' sub' : ''}" d="${path}" fill="${sx.color}"${sx.op < 1 ? ` fill-opacity="${sx.op}"` : ''}/>`;
    }
    return out;
  };
  const ordered = d.series.slice().reverse();          // unterste Flaeche = letzte Position der Tabelle
  g += band(ordered, 1) + band(ordered, -1);
  // Plan-Bereich blass, heute markiert
  const ist = d.ist - 1;
  if (ist < i1) { const xs = Math.max(P.l, x(Math.max(ist, i0))); g += `<rect class="bch-plan" x="${pf(xs)}" y="${P.t}" width="${pf(W - P.r - xs)}" height="${H - P.t - P.b}"/>`; }
  if (ist >= i0 && ist <= i1) g += `<line class="bch-today" x1="${pf(x(ist))}" x2="${pf(x(ist))}" y1="${P.t - 4}" y2="${H - P.b}"/><text class="bch-today-l" x="${pf(x(ist))}" y="${P.t - 5}"${x(ist) > W - P.r - 20 ? ' style="text-anchor:end"' : ''}>${t('heute')}</text>`;
  // Nettovermoegen
  const line = (a, b, cls0) => { const pts = []; for (let i = a; i <= b; i++) if (d.nw[i] != null) pts.push((pts.length ? 'L' : 'M') + pf(x(i)) + ' ' + pf(y(d.nw[i]))); return pts.length > 1 ? `<path class="${cls0}" d="${pts.join('')}"/>` : ''; };
  g += line(i0, Math.min(i1, ist), 'bch-nw') + (ist < i1 ? line(Math.max(i0, ist), i1, 'bch-nw plan') : '');
  g += `<g id="bch-hover"></g><rect class="bch-sel hidden" id="bch-sel" y="${P.t}" height="${H - P.t - P.b}"/><rect class="bch-hit" id="bch-hit" x="${P.l}" y="0" width="${W - P.l - P.r}" height="${H}"/>`;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('width', W); svg.setAttribute('height', H); svg.innerHTML = g;
  BCH.geo = {W, H, P, x, y, idx: px => Math.max(i0, Math.min(i1, Math.round(i0 + (px - P.l) * n / Math.max(1, W - P.l - P.r))))};
  const rl = $('#bch-range'); if (rl) rl.textContent = `${MONATE_LANG[+d.months[i0].slice(5) - 1]} ${d.months[i0].slice(0, 4)} – ${MONATE_LANG[+d.months[i1].slice(5) - 1]} ${d.months[i1].slice(0, 4)}`;
  $$('#bch-rb button').forEach(b => b.classList.toggle('on', S.bchRange ? +b.dataset.m === S.bchBtn : b.dataset.m === '0'));
  const nf = $('#bch-n'); if (nf && document.activeElement !== nf) nf.value = i1 - i0 + 1;
  bchBind();
}
function bchWindow(d, m) {
  // m Monate sichtbar; mit Plan endet der Ausschnitt ein Viertel davon nach heute, sonst heute
  const last = d.months.length - 1, today = d.ist - 1, plan = planOn() ? Math.min(Math.round(m / 4), last - today) : 0;
  const i1 = Math.min(last, today + plan), i0 = Math.max(0, i1 - m + 1);
  return [i0, Math.min(last, Math.max(i1, i0 + 2))];
}
function bchSet(i0, i1, btn) {
  const d = BCH.d, n = d.months.length; i0 = Math.max(0, Math.min(i0, n - 3)); i1 = Math.max(i0 + 2, Math.min(i1, n - 1));
  BCH.f0 = i0; BCH.f1 = i1;
  if (i0 === BCH.i0 && i1 === BCH.i1 && (btn || null) === S.bchBtn) return;
  BCH.i0 = i0; BCH.i1 = i1; S.bchRange = i0 === 0 && i1 === n - 1 ? null : [d.months[i0], d.months[i1]]; S.bchBtn = btn || null; bchDraw();
}
function bchView(f0, span, keepBtn) {
  // Ausschnitt in Bruchteilen von Monaten (fliessendes Wischen und Zoomen); am Rand wird verschoben, nicht gestaucht
  const last = BCH.d.months.length - 1; span = Math.max(2, Math.min(last, span)); f0 = Math.max(0, Math.min(f0, last - span));
  const i0 = Math.round(f0), i1 = Math.min(last, i0 + Math.round(span));
  bchSet(i0, i1, keepBtn ? S.bchBtn : null);
  BCH.f0 = f0; BCH.f1 = f0 + span;
}
function bchZoom(c, factor) {
  // um den Monat c (Bruchteil) vergroessern (factor < 1) bzw. verkleinern
  const span = BCH.f1 - BCH.f0, ns = Math.max(2, Math.min(BCH.d.months.length - 1, span * factor));
  bchView(c - (c - BCH.f0) * ns / span, ns, false);
}
function bchHover(i) {
  const d = BCH.d, G = BCH.geo, hv = $('#bch-hover'), tip = $('#bch-tip'); if (!hv || !tip) return;
  if (i == null) { hv.innerHTML = ''; tip.classList.add('hidden'); bchMark(null); return; }
  const xi = G.x(i).toFixed(1), m = d.months[i], plan = i >= d.ist;
  let dots = `<line class="bch-cross" x1="${xi}" x2="${xi}" y1="${G.P.t}" y2="${G.H - G.P.b}"/>`;
  if (d.nw[i] != null) dots += `<circle class="bch-dot" cx="${xi}" cy="${G.y(d.nw[i]).toFixed(1)}" r="4"/>`;
  hv.innerHTML = dots;
  const rows = d.series.filter(x => x.vals[i] != null && Math.abs(x.vals[i]) >= 0.5).map(x => `<div><i style="background:${x.color};opacity:${x.op || 1}"></i><span>${esc(x.label)}</span><b>${F0(x.vals[i])}</b></div>`).join('');
  tip.innerHTML = `<div class="bch-tip-h">${MONATE_LANG[+m.slice(5) - 1]} ${m.slice(0, 4)}${plan ? ` <span class="pill neutral">${t('plan')}</span>` : ''}</div>${rows}<div class="bch-tip-nw"><span>${t('nettovermoegen')}</span><b>${F0(d.nw[i])}</b></div>`;
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
  const w = $('.wrap.snap'), th = w && ($(`th[data-key="${m}"]`, w) || $(`th[data-key="${m.slice(0, 4)}"]`, w)); if (!th) return;
  const sw = $('thead th', w).offsetWidth, target = colX(w, th) - sw - (w.clientWidth - sw - th.offsetWidth) / 2;
  w.scrollTo({left: snapLeft(w, target), behavior: 'smooth'});
  const idx = [...th.parentNode.children].indexOf(th);
  $$('tr', w).forEach(tr => { const c = tr.children[idx]; if (c) { c.classList.remove('flash'); void c.offsetWidth; c.classList.add('flash'); } });
}
function bchBind() {
  const hit = $('#bch-hit'); if (!hit) return;
  const pt = e => { const r = $('#bch-svg').getBoundingClientRect(); return (e.clientX - r.left) * BCH.geo.W / r.width; };
  hit.addEventListener('pointermove', e => {
    const px = pt(e), G = BCH.geo;
    if (BCH.drag) { const sel = $('#bch-sel'), a = Math.max(G.P.l, Math.min(BCH.drag.x, px)), b = Math.min(G.W - G.P.r, Math.max(BCH.drag.x, px)); sel.setAttribute('x', a); sel.setAttribute('width', b - a); sel.classList.toggle('hidden', b - a < 4); }
    bchHover(G.idx(px));
  });
  hit.addEventListener('pointerleave', () => { if (!BCH.drag) bchHover(null); });
  hit.addEventListener('pointerdown', e => { if (e.pointerType === 'touch') return; BCH.drag = {x: pt(e)}; hit.setPointerCapture(e.pointerId); });
  hit.addEventListener('pointerup', e => {
    const G = BCH.geo, px = pt(e), dr = BCH.drag; BCH.drag = null;
    if (dr && Math.abs(px - dr.x) > 6) { const a = G.idx(Math.min(px, dr.x)), b = G.idx(Math.max(px, dr.x)); bchSet(a, b); return; }
    $('#bch-sel') && $('#bch-sel').classList.add('hidden');
    bchJump(BCH.d.months[G.idx(px)]);
  });
  const at = px => { const G = BCH.geo; return BCH.f0 + (px - G.P.l) * (BCH.f1 - BCH.f0) / Math.max(1, G.W - G.P.l - G.P.r); };   // Monat (Bruchteil) unter dem Zeiger
  hit.addEventListener('dblclick', e => bchZoom(at(pt(e)), 0.5));          // Doppelklick: auf den halben Zeitraum um diese Stelle
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
  hit.addEventListener('gesturestart', e => { e.preventDefault(); BCH.gesture = {c: at(pt(e)), span: BCH.f1 - BCH.f0, f0: BCH.f0}; });
  hit.addEventListener('gesturechange', e => {
    e.preventDefault(); const g = BCH.gesture; if (!g || !e.scale) return;
    const ns = Math.max(2, Math.min(BCH.d.months.length - 1, g.span / e.scale));
    bchView(g.c - (g.c - g.f0) * ns / g.span, ns, false);
  });
  hit.addEventListener('gestureend', e => { e.preventDefault(); BCH.gesture = null; });
}
function bindBilanzChart(main) {
  if (!$('#bch', main)) return;
  $$('#bch-rb button', main).forEach(b => b.addEventListener('click', () => {
    const d = BCH.d, m = +b.dataset.m;
    if (!m) bchSet(0, d.months.length - 1); else { const [a, z] = bchWindow(d, m); bchSet(a, z, m); }
  }));
  const nf = $('#bch-n', main);
  if (nf) nf.addEventListener('change', () => {
    // eigene Anzahl Monate: rechter Rand bleibt, der Ausschnitt waechst bzw. schrumpft nach links
    const d = BCH.d, m = Math.max(3, Math.min(d.months.length, Math.round(+nf.value) || 12)), z = BCH.i1;
    let a = z - m + 1, e = z; if (a < 0) { e = Math.min(d.months.length - 1, e - a); a = 0; }
    const btn = [12, 36, 120].includes(m) && bchWindow(d, m)[0] === a ? m : null;
    bchSet(a, e, btn); nf.blur();
  });
  bchDraw();
  if (BCH.ro) BCH.ro.disconnect();
  let last = 0; BCH.ro = new ResizeObserver(() => { const w = $('#bch-plot'); if (w && Math.abs(w.clientWidth - last) > 2) { last = w.clientWidth; bchDraw(); } });
  BCH.ro.observe($('#bch-plot', main));
}

// ---------------------------------------------------------------- Tabellen: Spalten rasten ein (nichts angeschnitten)
const colX = (w, el) => el.getBoundingClientRect().left - w.getBoundingClientRect().left - w.clientLeft + w.scrollLeft;   // Lage im Inhalt
function snapLeft(w, target) {
  // naechster Spaltenanfang ab target (erste Spalte bleibt stehen)
  const ths = $$('thead th', w).slice(1).filter(th => !th.classList.contains('snap-pad')), sw = $('thead th', w).offsetWidth;
  const max = w.scrollWidth - w.clientWidth;
  const b = ths.map(th => Math.round(colX(w, th) - sw)).find(v => v >= target - 1);
  return Math.max(0, Math.min(max, b == null ? max : b));
}
function snapTable(w) {
  const t = $('table', w), first = $('thead th', w); if (!t || !first) return;
  $$('.snap-pad', w).forEach(c => c.remove());
  w.classList.add('snap');
  const sw = first.offsetWidth, max = w.scrollWidth - w.clientWidth;
  w.style.scrollPaddingLeft = sw + 'px';
  if (max <= 0) return;
  // Leerspalte am Ende, damit auch ganz rechts die erste sichtbare Spalte vollstaendig ist
  const starts = $$('thead th', w).slice(1).map(th => colX(w, th) - sw), b = starts.find(v => v >= max - 0.5);
  const padw = b == null ? 0 : b - max;
  if (padw > 0.5) $$('tr', t).forEach(tr => { const c = document.createElement(tr.parentNode.tagName === 'THEAD' ? 'th' : 'td'); c.className = 'snap-pad'; c.style.minWidth = c.style.width = padw + 'px'; tr.appendChild(c); });
}

// ---------------------------------------------------------------- Kapitalfluss / Planung
const SEC_LABEL = {Einnahmen: t('einnahmen'), Ausgaben: t('ausgaben'), Investitionen: t('investitionen_umschichtung'), Finanzierung: t('finanzierung_tilgung_zinsen'), Bewertung: t('bewertung_manuelle_buchungen_nicht_zah'), Unklar: t('unklar_zuordnung_pruefen')};
const METH = {gleitend12: t('12_monate'), gleitend6: t('6_monate'), vorjahr: t('vorjahresmonat'), fix: t('fester_betrag_monat'), jahresbetrag: t('meth_jahresbetrag'), budget: t('meth_budget'), keine: t('keine')};
function vKapitalfluss(editable) {
  const D = B(); if (!D) return noData;
  const C = cols(), KF = D.kapitalfluss, sums = KF.summen || {}, P = D.plan || {};
  const vOf = (z, c) => sumOver(Object.assign({}, z.werte, (z.plan && z.plan.werte) || {}), c.months);
  const sOf = (z, c) => sumOver(Object.assign({}, z.werte, (z.plan && z.plan.vorschlag) || {}), c.months);
  let h = `<div class="toolbar">${viewCtl()}<span class="tb-sep"></span>${alleCtl(0)}${editable ? swCtl('realan', S.real, t('inflationsbereinigt'), t('inflationsbereinigt_tip')) : planCtl()}<span class="sp"></span>${xlsxBtn(editable ? 'planning' : 'cashflow')}</div>`;
  h += `<div class="legend"><span class="p">${t('plan')}</span><span class="c">${t('laufender_monat')}</span><span class="y">${t('jahressumme')}</span><span class="o">${t('ueberschrieben')}</span>` + (editable ? '<label class="chk"><input type="checkbox" id="vorschlag-an" ' + (S.vorschlag ? 'checked' : '') + `${t('vorschlagswerte_zeigen')}</label><em>${t('doppelklick_auf_eine_planzelle_eigener')}</em>` : '') + (editable && S.real ? `<em class="pill info">${t('planwerte_in_heutiger_kaufkraft')}</em>` : '') + '</div>';
  if (editable) {
    h += `<div class="card" style="margin-bottom:12px"><h3>${t('parameter')}</h3><div class="row tight">
      <label>${t('horizont')} <input id="p_horizont" type="number" min="1" max="240" value="${P.horizont_monate ?? 24}" style="width:70px"> ${t('monate')}</label>
      <label>${t('standardmethode_0', hq('methode'))} <select id="p_methode">${['gleitend12', 'gleitend6', 'vorjahr', 'budget', 'keine'].map(x => `<option value="${x}" ${P.standard_methode === x ? 'selected' : ''}>${METH[x]}</option>`).join('')}</select></label>
      <label>${t('inflation_0', hq('inflation'))} <input id="p_infl" type="number" step="0.1" value="${P.inflation_prozent_pa ?? 2}" style="width:64px"> % p.a.</label>
      <label>${t('steigerung_einnahmen_0', hq('steig_ein'))} <input id="p_se" type="number" step="0.1" value="${P.steigerung_einnahmen_prozent_pa ?? 0}" style="width:64px"> %</label>
      <label>${t('ausgaben')} <input id="p_sa" type="number" step="0.1" value="${P.steigerung_ausgaben_prozent_pa ?? ''}" placeholder="${t('inflation')}" style="width:64px"> %</label>
      <label>${t('rendite_wertpapiere_anlagen_0', hq('rendite'))} <input id="p_rendite" type="number" step="0.1" value="${P.rendite_prozent_pa ?? 0}" style="width:64px"> %</label>
      <button id="p_save" class="small">${t('uebernehmen')}</button><button id="p_reset" class="small secondary" title="${t('alle_planeinstellungen_dieses_bereichs')}">${t('plan_zuruecksetzen')}</button></div>
      <div class="note" style="margin:6px 0 0">${t('ausgaben_steigen_standardmaessig_mit_d_2')}</div></div>`;
  }
  h += '<div class="wrap"><table' + (editable ? ' class="ptable"' : '') + '>' + thead(t('position'), C) + '<tbody>';
  const secTotal = name => C.map(c => c.months.reduce((a, m) => a + (sums[m]?.[name] ?? 0) * defl(m), 0));
  for (const sek of KF.sektionen) {
    const tot = secTotal(sek.name);
    if (!sek.zeilen.length && !S.alle) continue;
    h += `<tr class="sec"><td>${SEC_LABEL[sek.name] || sek.name}</td>${tot.map((v, i) => `<td class="${cls(v, C[i])}">${F(v)}</td>`).join('')}</tr>`;
    const groups = [];
    for (const z of sek.zeilen) { let g = groups.find(x => x.name === z.gruppe); if (!g) groups.push(g = {name: z.gruppe, rows: []}); g.rows.push(z); }
    for (const g of groups) {
      const gvals = C.map(c => g.rows.reduce((a, z) => a + vOf(z, c), 0));
      const single = g.rows.length === 1 && g.rows[0].zeile === g.name;
      if (!S.alle && gvals.every(v => Math.abs(v) < 0.005)) continue;
      const gid = sek.name + '|' + g.name, coll = S.collapsed[gid];
      if (!single) h += `<tr class="sub ind1" data-gid="${esc(gid)}"><td>${coll ? '▸ ' : '▾ '}${esc(g.name)}</td>${gvals.map((v, i) => `<td class="${cls(v, C[i])}">${F(v)}</td>`).join('')}</tr>`;
      if (coll && !single) continue;
      for (const z of g.rows) {
        const vals = C.map(c => vOf(z, c));
        if (!S.alle && vals.every(v => Math.abs(v) < 0.005)) continue;
        const key = sek.name + '/' + z.zeile;
        const label = single ? z.zeile : z.zeile.startsWith(g.name + ' / ') ? z.zeile.slice(g.name.length + 3) : z.zeile;
        let e = '';
        const p = z.plan || {}, ov = new Set(p.ueberschrieben || []);
        if (editable) {
          const isLoan = p.methode === 'darlehen';
          e = isLoan ? `<div class="edit"><span class="tag">${t('darlehensplan_zins_auf_restsaldo')}</span>${ov.size ? ` <button class="small secondary reset-row" data-key="${esc(key)}" title="${t('alle_ueberschreibungen_loeschen')}">↺</button>` : ''}</div>`
            : `<div class="edit" data-key="${esc(key)}">
              <select class="meth"><option value="">${t('standard')}</option>${Object.entries(METH).map(([mm, ml]) => `<option value="${mm}" ${p.methode === mm && (D.plan.zeilen || {})[key]?.methode ? 'selected' : ''}>${ml}</option>`).join('')}</select>
              <input class="betrag" type="number" step="0.01" placeholder="${t('betrag')}" value="${p.betrag ?? ''}" title="${t('betrag_fuer_fester_betrag_jahresbetrag')}">
              <input class="pct steig" type="number" step="0.1" placeholder="% p.a." value="${(D.plan.zeilen || {})[key]?.steigerung_prozent_pa ?? ''}" title="${t('steigerung_p_a_leer_standard')}">
              <button class="save small" title="${t('uebernehmen')}">✓</button>${ov.size ? `<button class="small secondary reset-row" data-key="${esc(key)}" title="${t('alle_ueberschreibungen_loeschen')}">↺</button>` : ''}</div>`;
        }
        h += `<tr class="${single ? 'ind1' : 'ind2'}" data-key="${esc(key)}"><td title="${esc(z.zeile)}">${esc(label)}${z.nw ? '' : `<span class="tag">${t('umschichtung')}</span>`}${editable && p.methode && p.methode !== 'darlehen' ? `<span class="tag">${METH[p.methode] || p.methode}${p.budget ? t('budget') + F0(p.budget) : ''}</span>` : ''}${e}</td>`
           + vals.map((v, i) => {
               const c = C[i], isOv = c.plan && c.months.some(mm => ov.has(mm));
               const sug = (S.vorschlag && c.plan) ? `<div class="small muted">${F(sOf(z, c))}</div>` : '';
               return `<td class="${cls(v, c)}${editable && c.plan && !c.year ? ' editable' : ''}${isOv ? ' ov' : ''}" data-month="${c.key}" ${isOv ? `title="${t('vorschlag_0', F(sOf(z, c)))}"` : ''}>${F(v)}${sug}</td>`; }).join('') + '</tr>';
      }
    }
  }
  for (const [name, label] of [['Operativ', t('operatives_ergebnis_einnahmen_ausgaben')], ['Zinsen', t('davon_zinsen')], ['Cashflow', t('zahlungsfluss_gesamt_veraenderung_liqu')], ['Nettovermoegen_delta', t('nettovermoegensaenderung_erklaert')]]) {
    const tot = secTotal(name);
    h += `<tr class="total"><td>${label}</td>${tot.map((v, i) => `<td class="${cls(v, C[i])}">${F(v)}</td>`).join('')}</tr>`;
  }
  const ue = KF.ueberleitung || {};
  h += `<tr><td>${t('unerklaerte_vermoegensaenderung_pruefz')}</td>${C.map(c => { const v = c.plan ? null : c.months.reduce((a, m) => a + (ue[m]?.unerklaert ?? 0), 0); return `<td class="${cls(v, c)}">${v == null ? '' : F(v)}</td>`; }).join('')}</tr>`;
  h += '</tbody></table></div>';
  if (editable) h += vPlanExtras(D);
  h += `<div class="note">${t('umschichtungen_tilgung_investition_ein')}` + (editable ? t('methoden_12_6_monate_der') : '') + '</div>';
  return h;
}
function vPlanExtras(D) {
  const P = D.plan || {}, loans = D.darlehen_konfig || {};
  const fin = (D.kapitalfluss.sektionen.find(s => s.name === 'Finanzierung') || {zeilen: []}).zeilen;
  const loanNames = [...new Set(fin.filter(z => z.konto).map(z => z.gruppe))];
  let h = `<h2>${t('darlehensplan')}</h2><div class="note">${t('zins_auf_den_fortgeschriebenen_restsal')}</div><div class="wrap auto"><table class="plain"><thead><tr><th>${t('darlehen')}</th><th>${t('zins_p_a')}</th><th>${t('modell')}</th><th>${t('zahlung_je_monat_leer_durchschnitt')}</th><th></th></tr></thead><tbody>`;
  for (const name of loanNames) {
    const d = (P.darlehen || {})[name] || {}; const cfgLoan = Object.values(loans).find(l => l.name === name);
    h += `<tr data-loan="${esc(name)}"><td>${esc(name)}${cfgLoan ? `<span class="tag">${t('regel')} ` + esc(cfgLoan.modell) + '</span>' : ''}</td><td class="num"><input type="number" step="0.01" class="lz" value="${d.zins_prozent_pa ?? ''}" style="width:90px"></td><td><select class="lm"><option value="restschuld_monatlich" ${d.modell === 'restschuld_monatlich' ? 'selected' : ''}>${t('restschuld_monatlich')}</option><option value="jahresbasis" ${d.modell === 'jahresbasis' ? 'selected' : ''}>${t('jahresbasis_31_12')}</option></select></td><td class="num"><input type="number" step="0.01" class="lp" value="${d.zahlung ?? ''}" style="width:110px"></td><td><button class="small save-loan">✓</button></td></tr>`;
  }
  if (!loanNames.length) h += `<tr><td colspan="5" class="muted">${t('keine_darlehenszeilen_im_kapitalfluss')}</td></tr>`;
  h += '</tbody></table></div>';
  const leafs = D.bilanz.zeilen.filter(r => !r.gruppe && r.rolle !== 'liquiditaet');
  const others = Object.entries((S.DATA && S.DATA.bereich_namen) || {}).filter(([k]) => k !== S.bereich);
  h += `<h2>${t('wertentwicklung_je_konto_0', hq('rendite'))}</h2><div class="note">${t('jaehrliche_wertaenderung_in_prozent_ba', hq('wert_bereich'))}</div><div class="wrap auto"><table class="plain"><thead><tr><th>${t('konto_2')}</th><th>${t('position')}</th><th>% p.a.</th><th>${t('basis_optional')}</th><th>${t('kopplung_an_bereich')}</th><th>${t('anteil')}</th><th></th></tr></thead><tbody>`;
  for (const r of leafs) {
    const w = (P.wertentwicklung || {})[r.name] || {};
    h += `<tr data-acct="${esc(r.name)}"><td>${esc(r.pfad)}${r.inaktiv ? `<span class="tag">${t('ausgeblendet')}</span>` : ''}</td><td class="small">${(ROLE[r.rolle] || [r.rolle])[0]}</td><td class="num"><input type="number" step="0.1" class="wp" value="${w.prozent_pa ?? ''}" style="width:80px"></td><td class="num"><input type="number" step="1" class="wb" value="${w.basis ?? ''}" style="width:130px"></td><td><select class="wbr"><option value="">–</option>${others.map(([k, n]) => `<option value="${k}" ${w.bereich === k ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></td><td class="num"><input type="number" step="0.01" min="0" max="1" class="wa" value="${w.anteil ?? ''}" placeholder="1" style="width:70px"></td><td><button class="small save-wert">✓</button></td></tr>`;
  }
  h += '</tbody></table></div>';
  // Ereignisse
  const evs = P.ereignisse || [];
  const konten = D.bilanz.zeilen.filter(r => !r.gruppe);
  const kOpt = sel => `<option value="">${t('liquiditaet_bereich')}</option>` + konten.map(k => `<option value="${k.id} | ${esc(k.name)}" ${sel && sel.split('|')[0].trim() === k.id ? 'selected' : ''}>${esc(k.name)}${k.rolle ? ' · ' + (ROLE[k.rolle] || [k.rolle])[0] : ''}</option>`).join('');
  const WH = {einmalig: t('einmalig'), monatlich: t('monatlich'), quartal: t('je_quartal'), jaehrlich: t('jaehrlich')};
  const nextM = (() => { const d = new Date(); d.setMonth(d.getMonth() + 1); return d.toISOString().slice(0, 7); })();
  const evRow = (e, isNew) => `<div class="ev-row item" data-id="${esc(e.id || '')}"><div class="grow">
    <div class="row tight"><input type="text" class="ev-text" value="${esc(e.text || '')}" placeholder="${t('bezeichnung_z_b_rueckzahlung_unternehm')}" style="width:260px">
      <select class="ev-art">${[['umschichtung', t('umschichtung')], ['ausgabe', t('ausgabe')], ['einnahme', t('einnahme')]].map(([v, l]) => `<option value="${v}" ${(e.art || 'umschichtung') === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <label class="chk small">${t('betrag')} <input type="number" step="0.01" class="ev-betrag" value="${e.betrag ?? ''}" style="width:120px"></label>
      <label class="chk small">${t('monat_2')} <input type="month" class="ev-monat" value="${esc(e.monat || (isNew ? nextM : ''))}"></label>
      <select class="ev-wdh">${Object.entries(WH).map(([v, l]) => `<option value="${v}" ${(e.wiederholung || 'einmalig') === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <label class="chk small">${t('bis')} <input type="month" class="ev-bis" value="${esc(e.bis || '')}" title="${t('enddatum_bei_wiederholung_leer_horizon')}"></label></div>
    <div class="row tight"><label class="chk small">${t('von')} <select class="ev-von">${kOpt(e.von)}</select></label><span class="muted">→</span><label class="chk small">${t('nach')} <select class="ev-nach">${kOpt(e.nach)}</select></label>
      <label class="chk small"><input type="checkbox" class="ev-aktiv" ${e.aktiv !== false ? 'checked' : ''}> ${t('aktiv')}</label>
      <button class="small ev-save">${e.id ? t('speichern') : t('hinzufuegen')}</button>${e.id ? `<button class="small danger ev-del">${t('loeschen')}</button>` : ''}</div></div></div>`;
  h += `<h2>${t('geplante_ereignisse_0', hq('ereignis'))}</h2><div class="note">${t('umschichtung_betrag_geht_von_von')}</div><div class="list">`;
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
    ${card('MoneyMoney', `<span class="dot ${mmState(st).cls}"></span>${mmState(st).text}`, m.laeuft ? (m.gesperrt ? t('zum_lesen_in_moneymoney_entsperren') : t('kontor_kann_lesen')) : t('kontor_rechnet_mit_dem_zuletzt'))}
    ${card(t('banken_moneymoney'), r.neuester ? esc(fmtZeit(r.neuester)) : '–', t('neuester_bankabruf_in_moneymoney_den'))}
    ${card(t('moneymoney_kontor'), r.gelesen ? esc(fmtZeit(r.gelesen)) : '–', (z.automatisch ? t('automatisch_alle') + z.intervall_minuten + t('minuten_wenn_moneymoney_laeuft_und') : t('automatischer_abgleich_ist_aus')) + ` (<a href="#einstellungen">${t('einstellungen')}</a>).`)}
    ${hasRules() ? card(t('regeln_zuletzt_angewendet'), l ? esc(fmtZeit(l.zeit)) : '–', `${t('nur_wenn_sich_in_moneymoney')} <a href="#buchungen">${t('buchungen')}</a>`) : ''}
  </div>
  <div class="toolbar"><button id="sync-now" ${OFFLINE.mode ? 'disabled' : ''}>${t('jetzt_synchronisieren')}</button><span class="muted small">${t('liest_sofort_aus_moneymoney_wendet')}</span></div>
  <div class="toolbar"><button id="sync-full" class="secondary" ${OFFLINE.mode ? 'disabled' : ''}>${t('alles_neu_lesen')}</button><span class="muted small">${t('voll_lesen_info', r.voll && r.voll.zuletzt ? esc(fmtZeit(r.voll.zuletzt)) : '–', (r.voll || {}).stunden || 24)} ${hq('voll_lesen')}</span></div>`;
  if (stale.length) h += `<div class="banner">${t('0_mehr_als_einen_tag', stale.length === 1 ? t('1_konto_liegt') : stale.length + t('konten_liegen'), esc(stale.map(k => k.name).join(', ')))}</div>`;
  const row = k => {
    const d = tage(k.zeit);
    const stand = k.art === 'offline' ? `<span class="muted">${esc(k.grund)}</span>` : k.alt ? `<span class="tag">${t('ruht_seit_ueber')} ` + ((S.CFG.bilanz || {}).inaktiv_monate || 12) + ` ${t('monaten_kein_abruf')}</span>` : k.zurueck ? `<span class="tag warn">${t('0_1_zurueck', d, d === 1 ? t('tag') : t('tage'))}</span>` : d != null && d >= 1 && !(k.saldo) ? `<span class="muted">${t('0_tage_zurueck_ohne_saldo', d)}</span>` : `<span class="tag ok">${t('aktuell')}</span>`;
    return `<tr data-uuid="${k.uuid}"><td>${esc(k.name)}<div class="small muted">${esc(k.pfad.split(' / ').slice(0, -1).join(' / '))}</div></td><td class="small">${esc(k.bereich || '–')}</td>
      ${k.art === 'online' ? `<td class="nowrap">${k.zeit ? esc(fmtZeit(k.zeit)) : '–'}</td>` : ''}<td>${stand}</td>
      <td class="c"><input type="checkbox" class="ab-chk" ${k.art === 'online' ? 'checked' : ''} title="${t('wird_von_moneymoney_bei_bank')}"></td></tr>`;
  };
  const dep = r.depots || [];
  if (m.problem) h += `<div class="banner err">${t('moneymoney_lief_am_0_kontor', esc(fmtZeit(m.problem.zeit)), esc(m.problem.text))}</div>`;
  if ((r.luecken || []).length) h += `<div class="banner">${t('moeglicherweise_fehlen_depotstaende_mo', r.luecken.map(l => `<b>${esc(l.name)}</b> ${l.monate.map(ML).join(', ')}`).join('; '))} <button class="small secondary" id="gap-ok">${t('hinweis_ausblenden')}</button></div>`;
  if (dep.length) h += `<h2>${t('depots_wertverlauf_0', hq('depotverlauf'))}</h2><div class="note">${t('bankkonten_rechnet_kontor_exakt_aus', r.aufzeichnung_seit ? ML(r.aufzeichnung_seit) : t('heute'))}</div>
    <div class="small" style="margin:6px 0 10px">${r.mm_verlauf ? `${t('verlauf_aus_moneymoney_uebernommen_am', esc(fmtZeit(r.mm_verlauf.zeit)))}` : t('bisheriger_verlauf_noch_nicht_uebernom')} <a href="#einrichtung/historie">${t('kontostaende_aus_moneymoney_0_einlesen', r.mm_verlauf ? 'erneut ' : '')}</a></div>
    <div class="wrap auto"><table class="plain acct-table sync-table"><thead><tr><th>${t('depot')}</th><th>${t('bereich')}</th><th>${t('bekannt_ab')}</th><th></th></tr></thead><tbody>${dep.map(k => `<tr data-uuid="${k.uuid}"><td>${esc(k.name)}<div class="small muted">${esc(k.pfad.split(' / ').slice(0, -1).join(' / '))}</div></td><td class="small">${esc(k.bereich || '–')}</td><td>${k.erster_stand ? ML(k.erster_stand) : '–'}${k.aus_moneymoney ? ` <span class="small muted">${t('aus_moneymoney')}</span>` : ''}${k.eigene ? ` <span class="small muted">${t('0_eingetragen', k.eigene)}</span>` : ''}</td><td class="c"><button class="small secondary dep-hist">${t('staende_eintragen')}</button></td></tr>`).join('')}</tbody></table></div>`;
  h += `<h2>${t('sync_mit_abruf', online.length, hq('abruf'))}</h2><div class="wrap auto"><table class="plain acct-table sync-table"><thead><tr><th>${t('konto_2')}</th><th>${t('bereich')}</th><th>${t('letzter_abruf')}</th><th>${t('stand')}</th><th class="c">${t('abgerufen')}</th></tr></thead><tbody>${online.map(row).join('') || `<tr><td colspan="5" class="muted">${t('keine')}</td></tr>`}</tbody></table></div>`;
  h += `<h2>${t('sync_ohne_abruf', offline.length)}</h2><div class="note">${t('von_hand_gefuehrte_konten_z')}</div>
    <div class="wrap auto"><table class="plain acct-table sync-table"><thead><tr><th>${t('konto_2')}</th><th>${t('bereich')}</th><th>${t('erkannt_als')}</th><th class="c">${t('abgerufen')}</th></tr></thead><tbody>${offline.map(row).join('') || `<tr><td colspan="4" class="muted">${t('keine')}</td></tr>`}</tbody></table></div>`;
  return h;
}

// ---------------------------------------------------------------- Buchungen (Laeufe)
function vBuchungen(runs) {
  const st = S.STATUS, l = runs.letzter_lauf;
  let h = `<div class="toolbar">
    <button id="run-dry">${t('abgleich_jetzt_test')}</button>
    <button id="run-live" class="${st.probelauf ? 'secondary' : ''}" ${st.lokal ? '' : t('disabled_title_nur_am_mac')}>${t('jetzt_buchen')}</button>
    <button id="run-report" class="secondary">${t('nur_bericht_aktualisieren')}</button>
  </div>`;
  if (l) {
    h += `<h2>${t('regeln_zuletzt_angewendet_0_1', esc(l.zeit), l.probelauf ? `<span class="pill warn">${t('testmodus')}</span>` : `<span class="pill ok">${t('gebucht')}</span>`, l.geschrieben, l.fehler ? ' · <span class="pill err">' + esc(l.fehler) + '</span>' : '')}</h2>`;
    if (l.vorschlaege && l.vorschlaege.length) {
      h += `<div class="wrap auto"><table class="plain"><thead><tr><th>${t('datum')}</th><th>${t('konto_2')}</th><th>${t('art')}</th><th class="num">${t('betrag')}</th><th>${t('text')}</th><th>${t('kategorie')}</th></tr></thead><tbody>`
        + l.vorschlaege.map(v => `<tr><td style="white-space:nowrap">${FD(v.datum)}</td><td>${esc(v.konto)}</td><td>${esc(v.art)}</td><td class="num ${v.betrag < 0 ? 'neg' : 'pos'}">${F(v.betrag)}</td><td>${esc(v.text)}</td><td>${esc(v.kategorie || '')}</td></tr>`).join('') + '</tbody></table></div>';
      if (l.probelauf) h += `<div class="note">${t('diese_buchungen_sind_noch_nicht')}</div>`;
    } else h += `<div class="note">${t('keine_buchungen_noetig')}</div>`;
    if (l.hinweise && l.hinweise.length) h += `<h3>${t('rechenwege')}</h3>` + l.hinweise.map(x => `<div class="small muted">${esc(x)}</div>`).join('');
    if (l.warnungen && l.warnungen.length) h += `<h3>${t('hinweise')}</h3>` + l.warnungen.map(x => `<div class="banner">${esc(x)}</div>`).join('');
  }
  h += `<h2>${t('verlauf_2')}</h2><div class="wrap auto"><table class="plain"><thead><tr><th>${t('zeit')}</th><th>${t('modus')}</th><th class="num">${t('vorschlaege')}</th><th class="num">${t('gebucht_2')}</th><th>${t('fehler_2')}</th><th>${t('buchungen')}</th></tr></thead><tbody>`
    + (runs.verlauf || []).map(v => `<tr><td>${esc(v.zeit)}</td><td>${v.probelauf ? t('test') : t('gebucht')}</td><td class="num">${v.vorschlaege ?? ''}</td><td class="num">${v.geschrieben}</td><td>${esc(v.fehler || '')}</td><td class="small">${(v.buchungen || []).map(esc).join('<br>')}</td></tr>`).join('') + '</tbody></table></div>';
  return h;
}

// ---------------------------------------------------------------- Steuer
function vSteuer() {
  if (!S.DATA || !S.DATA.steuer) return noData;
  const T = S.DATA.steuer, years = T.jahre, ents = T.entitaeten;
  if (!years.length || !ents.length) return `<div class="note">${t('keine_steuerdaten_keine_kategorisierte')}</div>`;
  if (!S.steuerJahr) S.steuerJahr = String(years[years.length - 1]);
  if (!S.steuerEnt || !ents.some(e => e.uuid === S.steuerEnt)) S.steuerEnt = (ents.find(e => e.uuid === S.bereich) || ents[0]).uuid;
  const ent = ents.find(e => e.uuid === S.steuerEnt) || ents[0];
  let h = `<div class="toolbar"><label>${t('jahr_2')} <select id="st-jahr">${years.map(y => `<option ${String(y) === S.steuerJahr ? 'selected' : ''}>${y}</option>`).join('')}</select></label>
    <label>${t('entitaet')} <select id="st-ent">${ents.map(e => `<option value="${e.uuid}" ${e.uuid === ent.uuid ? 'selected' : ''}>${esc(e.name)} (${e.art}${e.anteil ? t('anteil_2') + (e.anteil * 100).toFixed(0) + ' %' : ''})</option>`).join('')}</select></label>
    <span class="sp"></span><button id="st-belege" class="secondary small">${t('belege_0_exportieren', esc(S.steuerJahr))}</button>${xlsxBtn('tax')}</div>`;
  const J = ent.jahre[S.steuerJahr]; if (!J) return h + `<div class="note">${t('keine_daten_fuer_dieses_jahr')}</div>`;
  const objs = Object.keys(J.objekte);
  h += `<div class="cards"><div class="card"><div class="l">${t('einnahmen_kategorisiert')}</div><div class="v">${F0(J.summe_einnahmen)} €</div></div><div class="card"><div class="l">${t('ausgaben_kategorisiert')}</div><div class="v">${F0(J.summe_ausgaben)} €</div></div><div class="card"><div class="l">${t('schuldzinsen')}</div><div class="v">${F0(Object.values(J.schuldzinsen).reduce((a, b) => a + b, 0))} €</div></div><div class="card"><div class="l">${t('ohne_kategorie')}</div><div class="v">${J.ohne_kategorie.anzahl ? '<span class="pill warn">' + J.ohne_kategorie.anzahl + ` ${t('buchungen')}</span>` : `<span class="pill ok">${t('keine')}</span>`}</div><div class="d">${F(J.ohne_kategorie.betrag)} € – <a href="#umsaetze?ohne_kategorie=1&jahr=${S.steuerJahr}&entitaet=${ent.uuid}">${t('kategorisieren')}</a></div></div></div>`;
  if (objs.length) {
    h += `<h2>${t('vermietung_je_objekt')} <span class="x">${t('kategorien_0_objekt_art', esc(T.vermietung_kategorie))}</span></h2><div class="wrap auto"><table class="plain"><thead><tr><th>${t('position')}</th>${objs.map(o => `<th class="num">${esc(o)}</th>`).join('')}</tr></thead><tbody>`;
    const arten = [...new Set(objs.flatMap(o => Object.keys(J.objekte[o].arten)))];
    for (const a of arten) h += `<tr><td class="ind1">${esc(a)}</td>${objs.map(o => `<td class="num">${F(J.objekte[o].arten[a] ?? 0)}</td>`).join('')}</tr>`;
    h += `<tr class="total"><td>${t('einnahmen')}</td>${objs.map(o => `<td class="num pos">${F(J.objekte[o].einnahmen)}</td>`).join('')}</tr>`;
    h += `<tr class="total"><td>${t('werbungskosten_ohne_zinsen_afa')}</td>${objs.map(o => `<td class="num neg">${F(J.objekte[o].werbungskosten)}</td>`).join('')}</tr>`;
    const loans = [...new Set(objs.flatMap(o => Object.keys(J.objekte[o].schuldzinsen)))];
    for (const l of loans) h += `<tr><td class="ind1">${t('schuldzinsen_0', esc(l))}</td>${objs.map(o => `<td class="num">${F(J.objekte[o].schuldzinsen[l] ?? 0)}</td>`).join('')}</tr>`;
    h += `<tr><td class="ind1">${t('afa_manuell')}</td>${objs.map(o => `<td class="num"><input type="number" step="0.01" class="afa" data-obj="${esc(o)}" value="${J.objekte[o].afa || ''}" style="width:110px"></td>`).join('')}</tr>`;
    h += `<tr class="total"><td>${t('ergebnis_ueberschuss_verlust')}</td>${objs.map(o => `<td class="num ${J.objekte[o].ergebnis < 0 ? 'neg' : 'pos'}">${F(J.objekte[o].ergebnis)}</td>`).join('')}</tr>`;
    if (ent.anteil) h += `<tr class="total"><td>${t('davon_anteil_0', (ent.anteil * 100).toFixed(0))}</td>${objs.map(o => `<td class="num">${F(J.objekte[o].anteil_ergebnis)}</td>`).join('')}</tr>`;
    h += `</tbody></table></div><div class="actions"><button id="afa-save" class="small">${t('afa_speichern')}</button></div>`;
  } else h += `<div class="note">${t('keine_vermietungskategorien_fuer_diese', esc(T.vermietung_kategorie))}</div>`;
  h += `<h2>${ent.art === 'privat' ? t('steuerpositionen') : t('oberkategorien')}</h2><div class="wrap auto"><table class="plain"><thead><tr><th>${t('position')}</th><th>${t('kategorie')}</th><th class="num">${t('betrag')}</th><th class="num">${t('buchungen')}</th></tr></thead><tbody>`;
  for (const [pos, p] of Object.entries(J.positionen)) {
    h += `<tr class="sub"><td colspan="2">${esc(pos)}</td><td class="num ${p.betrag < 0 ? 'neg' : 'pos'}">${F(p.betrag)}</td><td></td></tr>` + p.kategorien.map(k => `<tr><td></td><td>${esc(k.pfad)}</td><td class="num">${F(k.betrag)}</td><td class="num">${k.anzahl}</td></tr>`).join('');
  }
  h += `</tbody></table></div><div class="note">${t('zusammenstellung_der_kategorisierten_b')}</div>`;
  return h;
}

// ---------------------------------------------------------------- Immobilien
const IM = {edit: null, res: null, tab: 'kalkulation', kalk: null, timer: null};
const immoOf = id => (S.CFG.immobilien || []).find(x => String(x.id) === String(id));
const immoData = id => ((S.DATA && S.DATA.immobilien) || []).find(x => String(x.id) === String(id));
function vImmobilien(id) {
  if (id) return vImmobilie(id);
  const list = S.CFG.immobilien || [];
  let h = `<div class="toolbar"><span class="muted small">${t('kalkulationen_je_objekt_mehrere_szenar')}</span><span class="sp"></span><button id="im-new" class="small">${t('neues_objekt')}</button></div>`;
  if (!list.length) return h + `<div class="card"><div class="v s">${t('noch_keine_immobilie')}</div><div class="d">${t('lege_ein_objekt_an_und')}</div></div>`;
  h += '<div class="cards k3">' + list.map(im => { const d = immoData(im.id) || {}; const K = d.kennzahlen || {}; const j1 = (d.jahre || []).find(j => j.monate === 12) || (d.jahre || [])[0];
    return `<div class="card clickable" data-im="${esc(im.id)}" style="cursor:pointer"><div class="l">${esc(BN(im.bereich) || im.bereich || '–')}${im.in_planung ? `<span class="tag">${t('in_planung')}</span>` : ''}</div><div class="v s">${esc(im.name)}</div>
      <div class="d">${K.kaufpreis != null ? t('kaufpreis') + F0(K.kaufpreis) + t('faktor') + (K.kaufpreisfaktor ?? '–') + t('bruttorendite') + (K.bruttomietrendite != null ? (K.bruttomietrendite * 100).toFixed(2) + ' %' : '–') : t('keine_kalkulation')}</div>
      <div class="d">${j1 ? t('cashflow') + j1.jahr + ': <b class="' + (j1.cashflow < 0 ? 'neg' : 'pos') + '">' + F0(j1.cashflow) + ` €</b> ${t('ek_rendite')} ` + (j1.ek_rendite != null ? (j1.ek_rendite * 100).toFixed(1) + ' %' : '–') + t('irr') + (K.irr != null ? (K.irr * 100).toFixed(1) + ' %' : '–') : ''}</div>
      ${(d.hinweise || []).length ? `<div class="d"><span class="pill warn">${t('0_hinweise', d.hinweise.length)}</span></div>` : ''}</div>`; }).join('') + '</div>';
  return h;
}
function vImmobilie(id) {
  const im = immoOf(id); if (!im) return `<div class="banner err">${t('immobilie_nicht_gefunden')}</div>`;
  const d = immoData(id) || {};
  const kalks = im.kalkulationen || [];
  if (!IM.kalk || !kalks.some(k => k.id === IM.kalk)) IM.kalk = (kalks.find(k => k.aktiv) || kalks[0] || {}).id || null;
  const k = kalks.find(x => x.id === IM.kalk);
  if (!IM.edit || IM.editFor !== id + '|' + IM.kalk) { IM.edit = JSON.parse(JSON.stringify((k && k.eingaben) || null)); IM.editFor = id + '|' + IM.kalk; IM.res = null; }
  const konten = S.KONTEN.filter(x => !x.gruppe);
  const kats = S.KATS.filter(x => x.ebene <= 1);
  let h = `<div class="toolbar"><a href="#immobilien" class="small">${t('alle_objekte')}</a><h2 style="margin:0">${esc(im.name)}</h2><span class="sp"></span>${xlsxBtn('property', `data-immo="${esc(im.id)}" data-kalk="${esc(IM.kalk || '')}"`)}<button id="im-del" class="danger small">${t('objekt_loeschen')}</button></div>
  <div class="card" style="margin-bottom:12px"><div class="immo-form">
    <label>${t('name')}</label><input type="text" id="im-name" value="${esc(im.name)}">
    <label>${t('bereich_0', hq('bereich'))}</label><select id="im-bereich">${Object.entries((S.DATA && S.DATA.bereich_namen) || {}).map(([bid, n]) => `<option value="${bid}" ${im.bereich === bid ? 'selected' : ''}>${esc(n)}</option>`).join('') || (S.CFG.bereiche || []).map(b => `<option value="${esc(b.id)}" ${im.bereich === b.id ? 'selected' : ''}>${esc(b.name)}</option>`).join('')}</select>
    <label>${t('vermietungskategorie_0', hq('immo_kategorie'))}</label><input type="text" id="im-kat" list="im-kats" value="${esc(im.kategorie || '')}" placeholder="${t('vermietung_objekt')}"><datalist id="im-kats">${kats.map(c => `<option value="${esc(c.roh)}">`).join('')}</datalist>
    <label>${t('objektkonto_wert_0', hq('immo_objektkonto'))}</label><select id="im-konto">${acctOptions(im.objekt_konto, x => !x.gruppe)}</select>
    <label>${t('in_planung_uebernehmen_0', hq('immo_planung'))}</label><label class="switch"><input type="checkbox" id="im-plan" ${im.in_planung ? 'checked' : ''}><i></i>${im.in_planung ? t('aktiv') : t('aus')}</label>
    <label>${t('notizen')}</label><input type="text" id="im-notiz" value="${esc(im.notizen || '')}">
  </div><div class="actions"><button id="im-save-meta" class="small">${t('objekt_speichern')}</button></div></div>
  <div class="tabs">${[['kalkulation', t('kalkulation')], ['jahre', t('jahrestabelle')], ['sollist', t('soll_ist')], ['dokumente', t('dokumente') + (im.dokumente || []).length + ')']].map(([t, l]) => `<button data-t="${t}" class="${IM.tab === t ? 'on' : ''}">${l}</button>`).join('')}</div>`;
  if (IM.tab === 'kalkulation') h += vImmoKalk(im, k, konten);
  else if (IM.tab === 'jahre') h += vImmoJahre(d);
  else if (IM.tab === 'sollist') h += vImmoSollIst(d);
  else h += vImmoDokumente(im);
  return h;
}
function vImmoKalk(im, k, konten) {
  const kalks = im.kalkulationen || [];
  let h = `<div class="row tight"><label>${t('szenario')} <select id="im-kalk">${kalks.map(x => `<option value="${esc(x.id)}" ${x.id === IM.kalk ? 'selected' : ''}>${esc(x.name)}${x.aktiv ? ' (aktiv)' : ''}</option>`).join('')}${!kalks.length ? `<option value="">${t('keine_2')}</option>` : ''}</select></label>
    <button id="im-kalk-new" class="small secondary">${kalks.length ? t('als_neues_szenario_kopieren') : t('kalkulation_anlegen')}</button>${k && !k.aktiv ? `<button id="im-kalk-aktiv" class="small secondary">${t('als_aktiv_setzen')}</button>` : ''}${k ? `<button id="im-kalk-del" class="small danger">${t('szenario_loeschen')}</button>` : ''}
    <span class="small muted">${t('das_aktive_szenario_gilt_fuer')}</span></div>`;
  if (!IM.edit) return h + `<div class="note">${t('noch_keine_kalkulation_kalkulation_anl')}</div>`;
  const e = IM.edit;
  const inp = (path, label, type = 'number', opts = {}) => { let v = get(e, path); if (type === 'month' && v) v = String(v).slice(0, 7); const attrs = Object.entries(opts).filter(([a]) => a !== 'hq').map(([a, b]) => `${a}="${b}"`).join(' '); return `<label>${label}${opts.hq ? hq(opts.hq) : ''}</label><input type="${type}" data-p="${path}" value="${v == null ? '' : esc(v)}" ${attrs}>`; };
  const sel = (path, label, options, hqk) => `<label>${label}${hqk ? hq(hqk) : ''}</label><select data-p="${path}">${options.map(([v, l]) => `<option value="${v}" ${String(get(e, path) ?? '') === String(v) ? 'selected' : ''}>${l}</option>`).join('')}</select>`;
  h += `<div class="immo-grid"><div class="card"><h3>${t('eingaben')} <span class="muted" style="text-transform:none;letter-spacing:0">${t('szenario_0', esc(k ? k.name : t('neu')))}</span></h3><div class="immo-form">
    <h4>${t('objekt')}</h4>
    ${inp('name', t('bezeichnung'), 'text')}${sel('art', t('art'), [['gewerbe', t('gewerbe')], ['wohnen', t('wohnen')]])}${inp('flaeche_qm', t('flaeche_m2'), 'number', {step: '0.1'})}${inp('einheiten', t('einheiten'), 'number', {step: '1'})}
    ${inp('kaufpreis', t('kaufpreis_2'), 'number', {step: '1000'})}${inp('uebergang', t('uebergang_nutzen_lasten'), 'month', {hq: 'immo_uebergang'})}${inp('horizont_jahre', t('horizont_jahre'), 'number', {step: '1', min: '1', max: '60'})}
    <h4>${t('nebenkosten_0', hq('immo_nk'))}</h4>
    ${inp('nebenkosten.grunderwerbsteuer_prozent', t('grunderwerbsteuer'), 'number', {step: '0.1'})}${inp('nebenkosten.notar', t('notar_kaufvertrag'), 'number', {step: '1'})}${inp('nebenkosten.grundbuch', t('grundbuch'), 'number', {step: '1'})}${inp('nebenkosten.makler', t('makler'), 'number', {step: '1'})}${inp('nebenkosten.sonstige_afa', t('sonstige_afa_basis'), 'number', {step: '1'})}${inp('nebenkosten.sofort_abziehbar', t('sofort_abziehbar'), 'number', {step: '1'})}
    <h4>${t('abschreibung')}</h4>
    ${inp('gebaeudeanteil_prozent', t('gebaeudeanteil'), 'number', {step: '0.01', hq: 'immo_geb'})}${inp('afa_prozent', 'AfA % p.a.', 'number', {step: '0.01', hq: 'immo_afa'})}${inp('restnutzungsdauer_jahre', t('oder_restnutzungsdauer_jahre'), 'number', {step: '1'})}
    <h4>${t('miete')}</h4>
    ${inp('miete.nettokalt_monat', t('nettokaltmiete_monat'), 'number', {step: '1'})}${inp('miete.nebenkosten_monat', t('umlage_nk_vorauszahlung_monat'), 'number', {step: '1'})}${inp('miete.leerstand_prozent', t('leerstand_mietausfall'), 'number', {step: '0.5'})}
    ${sel('miete.index.art', t('anpassung'), [['vpi', t('indexmiete_vpi')], ['prozent', t('feste_steigerung_p_a')], ['keine', t('keine')]], 'immo_index')}
    ${inp('miete.index.vpi_basis', t('vpi_bei_letzter_anpassung'), 'number', {step: '0.1'})}${inp('miete.index.vpi_aktuell', t('vpi_aktuell'), 'number', {step: '0.1'})}${inp('miete.index.vpi_steigerung_prozent', t('vpi_annahme_p_a'), 'number', {step: '0.1'})}${inp('miete.index.faktor', t('weitergabe_faktor_01'), 'number', {step: '0.05'})}${inp('miete.index.schwelle_prozent', t('schwelle'), 'number', {step: '0.5'})}${inp('miete.index.steigerung_prozent', t('feste_steigerung_p_a'), 'number', {step: '0.1'})}
    <h4>${t('kosten')}</h4>
    ${inp('kosten.nicht_umlagefaehig_pa', t('nicht_umlagefaehig_p_a'), 'number', {step: '10', hq: 'immo_kosten'})}${inp('kosten.ruecklage_pa', t('ruecklage_p_a'), 'number', {step: '10', hq: 'immo_ruecklage'})}${sel('kosten.steigerung', t('steigerung'), [['vpi', t('mit_vpi')], ['prozent', t('fester_satz')], ['keine', t('keine')]])}${inp('kosten.steigerung_prozent', t('fester_satz_p_a'), 'number', {step: '0.1'})}
    <h4>${t('gesellschafter_0', hq('immo_ges'))}</h4></div><div id="im-ges">${(e.gesellschafter || []).map((g, i) => `<div class="row tight" data-g="${i}"><input type="text" data-p="gesellschafter.${i}.name" value="${esc(g.name || '')}" placeholder="${t('name')}" style="width:140px"><input type="number" step="0.01" data-p="gesellschafter.${i}.anteil_prozent" value="${g.anteil_prozent ?? ''}" placeholder="${t('anteil_3')}" style="width:90px"><input type="number" step="0.001" data-p="gesellschafter.${i}.steuersatz_prozent" value="${g.steuersatz_prozent ?? ''}" placeholder="${t('steuersatz')}" style="width:110px"><button class="ghost small im-ges-del" data-i="${i}">✕</button></div>`).join('')}</div><div class="row tight"><button id="im-ges-add" class="small secondary">${t('gesellschafter_hinzufuegen')}</button></div>
    <div class="immo-form">${inp('ausschuettung_prozent', t('ausschuettung_des_ergebnisses'), 'number', {step: '1', hq: 'immo_aussch'})}${sel('steuererstattung_in_cashflow', t('steuererstattung_im_cashflow'), [['true', t('ja')], ['false', t('nein')]])}
    <h4>${t('wert_verkauf')}</h4>${inp('wertentwicklung_prozent', t('wertentwicklung_p_a'), 'number', {step: '0.1', hq: 'immo_wert'})}${inp('verkauf.jahr', t('verkaufsjahr_optional'), 'number', {step: '1', hq: 'immo_verkauf'})}${inp('verkauf.kosten_prozent', t('verkaufskosten'), 'number', {step: '0.1'})}</div>
    <h4 style="margin:12px 0 2px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)">${t('finanzierung')}</h4><div id="im-loans">${(e.darlehen || []).map((l, i) => loanBox(l, i, im, konten)).join('')}</div><div class="row tight"><button id="im-loan-add" class="small secondary">${t('darlehen_hinzufuegen')}</button></div>
    <div class="actions"><button id="im-calc" class="small secondary">${t('neu_berechnen')}</button><label class="chk small">${t('szenario_name')} <input type="text" id="im-kalk-name" value="${esc(k ? k.name : t('kalkulation'))}" style="width:160px"></label><button id="im-kalk-save" class="small">${t('speichern')}</button></div><div id="im-err" class="findings"></div></div>
    <div id="im-result">${IM.res ? immoResultHtml(IM.res) : `<div class="card"><div class="muted">${t('berechnung_laeuft')}</div></div>`}</div></div>`;
  return h;
}
function loanBox(l, i, im, konten) {
  const p = k => `darlehen.${i}.${k}`;
  const v = k => l[k] == null ? '' : esc(l[k]);
  const ref = (im.darlehen_konten || {})[l.name] || '';
  const st = (l.sondertilgungen || []).map(x => `${x.datum ? String(x.datum).slice(0, 7) : ''}: ${x.betrag}`).join('; ');
  return `<div class="loan-box" data-loan="${i}"><div class="immo-form">
    <label>${t('bezeichnung')}</label><input type="text" data-p="${p('name')}" value="${v('name')}">
    <label>${t('betrag_2')}</label><input type="number" step="1000" data-p="${p('betrag')}" value="${v('betrag')}">
    <label>${t('zins_p_a')}</label><input type="number" step="0.01" data-p="${p('zins_prozent')}" value="${v('zins_prozent')}">
    <label>${t('art_0', hq('immo_darlehen_art'))}</label><select data-p="${p('art')}">${[['annuitaet', t('annuitaet')], ['tilgung', t('tilgungsdarlehen')], ['endfaellig', t('endfaellig')]].map(([a, b]) => `<option value="${a}" ${l.art === a ? 'selected' : ''}>${b}</option>`).join('')}</select>
    <label>${t('annuitaet_monat')}</label><input type="number" step="0.01" data-p="${p('annuitaet_monat')}" value="${v('annuitaet_monat')}" placeholder="${t('oder_anfangstilgung')}">
    <label>${t('anfangstilgung_p_a')}</label><input type="number" step="0.01" data-p="${p('anfangstilgung_prozent')}" value="${v('anfangstilgung_prozent')}">
    <label>${t('tilgung_monat_tilgungsdarlehen')}</label><input type="number" step="1" data-p="${p('tilgung_monat')}" value="${v('tilgung_monat')}">
    <label>${t('sondertilgung_monat_0', hq('immo_sonder'))}</label><input type="number" step="1" data-p="${p('sondertilgung_monat')}" value="${v('sondertilgung_monat')}">
    <label>${t('ab_monat')}</label><input type="month" data-p="${p('sondertilgung_ab')}" value="${l.sondertilgung_ab ? String(l.sondertilgung_ab).slice(0, 7) : ''}">
    <label>${t('einzelne_sondertilgungen')}</label><input type="text" data-p="${p('sondertilgungen')}" data-kind="st" value="${esc(st)}" placeholder="2027-06: 50000; 2028-06: 50000">
    <label>${t('zinsbindung_bis_0', hq('immo_zinsbindung'))}</label><input type="month" data-p="${p('zinsbindung_bis')}" value="${l.zinsbindung_bis ? String(l.zinsbindung_bis).slice(0, 7) : ''}">
    <label>${t('anschlusszins_p_a')}</label><input type="number" step="0.01" data-p="${p('anschluss_zins_prozent')}" value="${v('anschluss_zins_prozent')}">
    <label>${t('faelligkeit_0', hq('immo_faellig'))}</label><input type="month" data-p="${p('faelligkeit')}" value="${l.faelligkeit ? String(l.faelligkeit).slice(0, 7) : ''}">
    <label>${t('bei_faelligkeit')}</label><select data-p="${p('faelligkeit_art')}">${[['offen', t('offen_hinweis')], ['rueckzahlung', t('rueckzahlung_aus_liquiditaet')]].map(([a, b]) => `<option value="${a}" ${(l.faelligkeit_art || 'offen') === a ? 'selected' : ''}>${b}</option>`).join('')}</select>
    <label>${t('beginn_auszahlung')}</label><input type="month" data-p="${p('beginn')}" value="${l.beginn ? String(l.beginn).slice(0, 7) : ''}" placeholder="${t('uebergang')}">
    <label>${t('abrechnung_0', hq('immo_abrechnung'))}</label><select data-p="${p('abrechnung')}">${[['monatlich', t('monatlich_bank')], ['jaehrlich', t('jaehrlich_stand_1_1')]].map(([a, b]) => `<option value="${a}" ${(l.abrechnung || 'monatlich') === a ? 'selected' : ''}>${b}</option>`).join('')}</select>
    <label>${t('zinsen_abziehbar_0', hq('immo_abziehbar'))}</label><select data-p="${p('abziehbar')}"><option value="true" ${l.abziehbar !== false ? 'selected' : ''}>${t('ja')}</option><option value="false" ${l.abziehbar === false ? 'selected' : ''}>${t('nein')}</option></select>
    <label>${t('darlehenskonto_in_moneymoney_0', hq('immo_darlehen_konten'))}</label><select class="im-loan-konto" data-loan-name="${esc(l.name || '')}">${acctOptions(ref, x => !x.gruppe)}</select>
  </div><div class="row tight"><button class="ghost small im-loan-del" data-i="${i}">${t('darlehen_entfernen')}</button></div></div>`;
}
function get(o, path) { return path.split('.').reduce((a, k) => (a == null ? undefined : a[k]), o); }
function setp(o, path, v) { const ks = path.split('.'); let a = o; for (let i = 0; i < ks.length - 1; i++) { const k = ks[i]; if (a[k] == null) a[k] = /^\d+$/.test(ks[i + 1]) ? [] : {}; a = a[k]; } a[ks[ks.length - 1]] = v; }
function immoResultHtml(r) {
  const K = r.kennzahlen, J = r.jahre;
  const pct = x => x == null ? '–' : (x * 100).toFixed(2) + ' %';
  const kp = (l, v) => `<div class="k"><div class="l">${l}</div><div class="v">${v}</div></div>`;
  let h = `<div class="card"><h3>${t('kennzahlen')}</h3><div class="kpis">${kp(t('gesamtinvestition'), F0(K.gesamtinvestition) + ' €')}${kp(t('eigenkapital_inkl_nk'), F0(K.eigenkapital_inkl_nk) + ' €')}${kp(t('fremdkapital_ltv'), F0(K.darlehen) + ' € (' + pct(K.ltv) + ')')}${kp(t('kaufpreisfaktor'), K.kaufpreisfaktor ?? '–')}${kp(t('bruttomietrendite'), pct(K.bruttomietrendite))}${kp(t('nettomietrendite'), pct(K.nettomietrendite))}${kp(t('cashflow_jahr_1'), F0(K.cashflow_jahr1) + ' €')}${kp('Cash-on-Cash', pct(K.cash_on_cash))}${kp(t('dscr_jahr_1'), K.dscr_jahr1 ?? '–')}${kp('AfA p.a.', F0(K.afa_jahr) + ' € (' + (K.afa_satz || 0).toFixed(2) + t('auf') + F0(K.afa_basis) + ')')}${kp(t('kapitaldienst_monat'), F0(K.kapitaldienst_monat) + ' €')}${kp(t('irr_bis') + (K.exit_jahr || '–'), pct(K.irr))}${K.preis_qm ? kp(t('preis_m2'), F0(K.preis_qm) + ' €') : ''}${K.miete_qm ? kp(t('miete_m2'), F(K.miete_qm) + ' €') : ''}</div>
    ${(r.hinweise || []).map(x => `<div class="banner" style="margin:4px 0">${esc(x)}</div>`).join('')}
    ${(K.mietanpassungen || []).length ? `<div class="small muted">${t('mietanpassungen')} ` + K.mietanpassungen.slice(0, 6).map(a => a.jahr + ': +' + a.erhoehung_prozent + ' % → ' + F0(a.nkm_neu) + ' €').join(' · ') + (K.mietanpassungen.length > 6 ? ' …' : '') + '</div>' : ''}
    ${immoChart(J)}</div>
    <div class="card" style="margin-top:12px"><h3>${t('erste_jahre')}</h3><div class="wrap auto"><table class="plain"><thead><tr><th>${t('jahr_2')}</th><th class="num">${t('miete')}</th><th class="num">${t('kosten')}</th><th class="num">${t('zinsen')}</th><th class="num">${t('tilgung')}</th><th class="num">${t('afa')}</th><th class="num">${t('ergebnis')}</th><th class="num">${t('steuer')}</th><th class="num">${t('cashflow_2')}</th><th class="num">${t('vermoegensaufbau')}</th><th class="num">${t('ek_rendite_2')}</th><th class="num">${t('restschuld')}</th></tr></thead><tbody>`
    + J.slice(0, 12).map(j => `<tr><td>${j.jahr}${j.monate < 12 ? ' <span class="muted small">(' + j.monate + ` ${t('mon_2')}</span>` : ''}</td><td class="num">${F0(j.miete)}</td><td class="num">${F0(j.kosten + j.ruecklage)}</td><td class="num">${F0(j.zins)}</td><td class="num">${F0(j.tilgung + j.sondertilgung)}</td><td class="num">${F0(j.afa)}</td><td class="num ${j.ergebnis < 0 ? 'neg' : 'pos'}">${F0(j.ergebnis)}</td><td class="num">${F0(j.steuer)}</td><td class="num ${j.cashflow < 0 ? 'neg' : 'pos'}">${F0(j.cashflow)}</td><td class="num">${F0(j.vermoegensaufbau)}</td><td class="num">${j.ek_rendite == null ? '–' : (j.ek_rendite * 100).toFixed(1) + ' %'}</td><td class="num">${F0(j.restschuld)}</td></tr>`).join('') + '</tbody></table></div></div>';
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
  return s + `</svg><div class="chart-legend"><span><i style="background:var(--c-ein)"></i>${t('cashflow_je_jahr_links')}</span><span><i style="background:var(--c-verb)"></i>${t('restschuld_rechts')}</span><span><i style="background:#b8860b"></i>${t('objektwert_rechts')}</span></div>`;
}
function vImmoJahre(d) {
  const J = d.jahre || []; if (!J.length) return `<div class="note">${t('keine_kalkulation_vorhanden_oder_beric')}</div>`;
  const names = d.darlehen_namen || [];
  let h = `<div class="toolbar"><span class="muted small">${t('aktive_kalkulation_0_alle_jahre', esc(d.name || ''))}</span><span class="sp"></span>${xlsxBtn('property', `data-immo="${esc(d.id)}"`)}</div><div class="wrap"><table><thead><tr><th>${t('jahr_2')}</th>${[t('miete'), t('umlage'), t('kosten'), t('ruecklage'), t('zinsen'), t('tilgung'), t('sondertilgung'), 'AfA', t('ergebnis'), t('steuer'), t('ergebnis_n_st'), t('ausschuettung'), t('cashflow_2'), t('cashflow_kum'), t('vermoegensaufbau'), 'EK-Rendite', t('restschuld'), t('objektwert'), t('ek_im_objekt'), 'DSCR', 'NKM/Monat'].map(x => `<th>${x}</th>`).join('')}${names.map(n => `<th>${t('0_zins', esc(n))}</th><th>${t('0_tilgung', esc(n))}</th><th>${t('0_saldo', esc(n))}</th>`).join('')}</tr></thead><tbody>`;
  const c = v => `<td class="${v == null ? 'zero' : v < 0 ? 'neg' : 'pos'}">${v == null ? '–' : F(v)}</td>`;
  for (const j of J) h += `<tr><td>${j.jahr}${j.monate < 12 ? ' (' + j.monate + ' Mon.)' : ''}</td>${[j.miete, j.umlage, j.kosten, j.ruecklage, j.zins, j.tilgung, j.sondertilgung, j.afa, j.ergebnis, j.steuer, j.ergebnis_nach_steuern, j.ausschuettung, j.cashflow, j.cashflow_kumuliert, j.vermoegensaufbau].map(c).join('')}<td>${j.ek_rendite == null ? '–' : (j.ek_rendite * 100).toFixed(2) + ' %'}</td>${[j.restschuld, j.wert, j.eigenkapital_objekt].map(c).join('')}<td>${j.dscr ?? '–'}</td>${c(j.nkm_monat)}${names.map(n => c(j.darlehen[n].zins) + c(j.darlehen[n].tilgung) + c(j.darlehen[n].saldo)).join('')}</tr>`;
  h += '</tbody></table></div>';
  return h;
}
function vImmoSollIst(d) {
  const rows = d.soll_ist || [];
  if (!rows.length) return `<div class="note">${t('fuer_soll_ist_braucht_das')}</div>`;
  const c = (v, cls2 = '') => `<td class="num ${cls2}">${v == null ? '–' : F0(v)}</td>`;
  const dv = (soll, ist) => ist == null || soll == null ? '<td></td>' : `<td class="num ${ist - soll >= 0 ? 'pos' : 'neg'}">${F0(ist - soll)}</td>`;
  return `<div class="wrap auto"><table class="plain"><thead><tr><th>${t('jahr_2')}</th><th class="num">${t('miete_soll')}</th><th class="num">${t('miete_ist')}</th><th class="num">Δ</th><th class="num">${t('kosten_soll')}</th><th class="num">${t('kosten_ist')}</th><th class="num">Δ</th><th class="num">${t('zinsen_soll')}</th><th class="num">${t('zinsen_ist')}</th><th class="num">Δ</th><th class="num">${t('restschuld_soll')}</th><th class="num">${t('restschuld_ist')}</th><th class="num">Δ</th></tr></thead><tbody>`
    + rows.map(r => `<tr><td>${r.jahr}</td>${c(r.miete_soll)}${c(r.miete_ist)}${dv(r.miete_soll, r.miete_ist)}${c(r.kosten_soll)}${c(r.kosten_ist)}${dv(r.kosten_soll, r.kosten_ist)}${c(r.zins_soll)}${c(r.zins_ist)}${dv(r.zins_soll, r.zins_ist)}${c(r.restschuld_soll)}${c(r.restschuld_ist)}${dv(r.restschuld_soll, r.restschuld_ist)}</tr>`).join('')
    + `</tbody></table></div><div class="note">${t('ist_kategorisierte_umsaetze_der_vermie')}</div>`;
}
function vImmoDokumente(im) {
  const docs = im.dokumente || [];
  let h = `<div class="note">${H.dokumente}</div><div class="card">${docs.map(d => `<div class="doc" data-id="${esc(d.id)}"><div class="n"><b>${esc(d.titel)}</b>${d.art ? ' <span class="tag">' + esc(d.art) + '</span>' : ''}<div class="p" title="${esc(d.pfad)}">${esc(d.pfad)}</div></div><span class="small muted">${esc(d.hinzugefuegt || '')}</span>${S.STATUS.lokal ? `<button class="ghost small doc-open">${t('oeffnen')}</button><button class="ghost small doc-show">${t('finder')}</button>` : ''}<button class="ghost small doc-del">✕</button></div>`).join('') || `<div class="muted small">${t('noch_keine_dokumente_verknuepft')}</div>`}
    <div class="row tight" style="margin-top:10px"><input type="text" id="doc-titel" placeholder="${t('titel_z_b_kaufvertrag')}" style="width:200px"><input type="text" id="doc-art" placeholder="${t('art_vertrag_gutachten')}" style="width:160px"><input type="text" id="doc-pfad" placeholder="${t('pfad_auf_dem_mac')}" style="min-width:260px;flex:1">${S.STATUS.lokal ? `<button id="doc-pick" class="small secondary">${t('datei_waehlen_2')}</button>` : ''}<button id="doc-add" class="small">${t('verknuepfen')}</button></div></div>`;
  return h;
}
async function immoCalc() {
  if (!IM.edit) return;
  try { IM.res = await api('/api/properties/calculate', {eingaben: IM.edit, ohne_monate: true}); const el = $('#im-result'); if (el) el.innerHTML = immoResultHtml(IM.res); const er = $('#im-err'); if (er) er.innerHTML = ''; }
  catch (e) { const el = $('#im-err'); if (el) el.innerHTML = `<div class="fehler">${esc(e.message)}</div>`; }
}
function bindImmo(main) {
  $$('.card[data-im]', main).forEach(c => c.addEventListener('click', () => { location.hash = '#immobilien/' + c.dataset.im; }));
  const nw = $('#im-new', main); if (nw) nw.addEventListener('click', async () => { const name = prompt(t('name_des_objekts')); if (!name) return; const b = S.bereich || ((S.CFG.bereiche || [])[0] || {}).id || ''; try { const r = await api('/api/properties', {aktion: 'anlegen', name, bereich: b}); S.CFG = await api('/api/config'); location.hash = '#immobilien/' + r.immobilie.id; } catch (e) { toast(e.message, 5000); } });
  const id = (location.hash.split('/')[1] || '').split('?')[0]; if (!id) return;
  const im = immoOf(id); if (!im) return;
  $$('.tabs button[data-t]', main).forEach(b => b.addEventListener('click', () => { IM.tab = b.dataset.t; route(); }));
  const del = $('#im-del', main); if (del) del.addEventListener('click', async () => { if (!confirm(t('objekt_2') + im.name + t('mit_allen_kalkulationen_loeschen'))) return; await api('/api/properties', {aktion: 'loeschen', id}); S.CFG = await api('/api/config'); location.hash = '#immobilien'; });
  const sm = $('#im-save-meta', main); if (sm) sm.addEventListener('click', async () => { try { await api('/api/properties', {aktion: 'aendern', id, name: $('#im-name').value, bereich: $('#im-bereich').value, kategorie: $('#im-kat').value, objekt_konto: $('#im-konto').value, in_planung: $('#im-plan').checked, notizen: $('#im-notiz').value}); toast(t('gespeichert')); await loadAll(); route(); } catch (e) { toast(e.message, 5000); } });
  const ks = $('#im-kalk', main); if (ks) ks.addEventListener('change', e => { IM.kalk = e.target.value; IM.edit = null; route(); });
  const kn = $('#im-kalk-new', main); if (kn) kn.addEventListener('click', async () => {
    let eing = IM.edit ? JSON.parse(JSON.stringify(IM.edit)) : (await api('/api/properties/template')).eingaben;
    if (!IM.edit) { eing.name = im.name; if (S.DATA && S.DATA.bereich_info && S.DATA.bereich_info[im.bereich] && S.DATA.bereich_info[im.bereich].art === 'privat') eing.gesellschafter = [{name: t('eigentuemer'), anteil_prozent: 100, steuersatz_prozent: 42}]; }
    const name = prompt(t('name_des_szenarios'), IM.edit ? t('variante') : t('basis')); if (!name) return;
    try { const r = await api('/api/properties', {aktion: 'kalkulation_speichern', id, kalkulation: {name, eingaben: eing}}); S.CFG = await api('/api/config'); IM.kalk = r.immobilie.kalkulationen[r.immobilie.kalkulationen.length - 1].id; IM.edit = null; await loadAll(); route(); } catch (e) { toast(e.message, 6000); } });
  const ka = $('#im-kalk-aktiv', main); if (ka) ka.addEventListener('click', async () => { await api('/api/properties', {aktion: 'kalkulation_aktiv', id, kalkulation_id: IM.kalk}); await loadAll(); route(); });
  const kd = $('#im-kalk-del', main); if (kd) kd.addEventListener('click', async () => { if (!confirm(t('szenario_loeschen_2'))) return; await api('/api/properties', {aktion: 'kalkulation_loeschen', id, kalkulation_id: IM.kalk}); IM.kalk = null; IM.edit = null; await loadAll(); route(); });
  // Eingaben binden
  $$('[data-p]', main).forEach(inp => inp.addEventListener('input', () => {
    let v = inp.value;
    if (inp.dataset.kind === 'st') { v = v.split(';').map(x => x.trim()).filter(Boolean).map(x => { const [d, b] = x.split(':'); return {datum: (d || '').trim(), betrag: parseFloat((b || '0').replace(',', '.')) || 0}; }); }
    else if (inp.type === 'number') v = v === '' ? null : parseFloat(v.replace(',', '.'));
    else if (v === 'true') v = true; else if (v === 'false') v = false;
    setp(IM.edit, inp.dataset.p, v);
    clearTimeout(IM.timer); IM.timer = setTimeout(immoCalc, 600);
  }));
  const la = $('#im-loan-add', main); if (la) la.addEventListener('click', () => { IM.edit.darlehen = IM.edit.darlehen || []; IM.edit.darlehen.push({name: t('darlehen_2') + (IM.edit.darlehen.length + 1), betrag: 0, zins_prozent: 3.5, art: 'annuitaet', abrechnung: 'monatlich', abziehbar: true}); route(); });
  $$('.im-loan-del', main).forEach(b => b.addEventListener('click', () => { IM.edit.darlehen.splice(+b.dataset.i, 1); route(); }));
  const ga = $('#im-ges-add', main); if (ga) ga.addEventListener('click', () => { IM.edit.gesellschafter = IM.edit.gesellschafter || []; IM.edit.gesellschafter.push({name: '', anteil_prozent: 0, steuersatz_prozent: 42}); route(); });
  $$('.im-ges-del', main).forEach(b => b.addEventListener('click', () => { IM.edit.gesellschafter.splice(+b.dataset.i, 1); route(); }));
  const cb = $('#im-calc', main); if (cb) cb.addEventListener('click', immoCalc);
  const sv = $('#im-kalk-save', main); if (sv) sv.addEventListener('click', async () => {
    const dk = {}; $$('.im-loan-konto', main).forEach(sel => { const name = sel.closest('.loan-box').querySelector('[data-p$=".name"]').value; if (sel.value) dk[name] = sel.value; });
    try { await api('/api/properties', {aktion: 'aendern', id, darlehen_konten: dk}); await api('/api/properties', {aktion: 'kalkulation_speichern', id, kalkulation: {id: IM.kalk, name: $('#im-kalk-name').value, eingaben: IM.edit}}); toast(t('kalkulation_gespeichert')); await loadAll(); route(); } catch (e) { $('#im-err').innerHTML = `<div class="fehler">${esc(e.message)}</div>`; } });
  if (IM.edit && !IM.res) immoCalc();
  // Dokumente
  const dp = $('#doc-pick', main); if (dp) dp.addEventListener('click', async () => { toast(t('dateiauswahl_am_mac_geoeffnet'), 4000); try { const r = await api('/api/file/choose', {art: 'datei', prompt: t('dokument_fuer') + im.name}); if (r.ok) { $('#doc-pfad').value = r.pfad; if (!$('#doc-titel').value) $('#doc-titel').value = r.name.replace(/\.[^.]+$/, ''); } else toast(r.text); } catch (e) { toast(e.message, 5000); } });
  const da = $('#doc-add', main); if (da) da.addEventListener('click', async () => { try { await api('/api/properties', {aktion: 'dokument_hinzufuegen', id, titel: $('#doc-titel').value, art: $('#doc-art').value, pfad: $('#doc-pfad').value}); S.CFG = await api('/api/config'); route(); } catch (e) { toast(e.message, 5000); } });
  $$('.doc-del', main).forEach(b => b.addEventListener('click', async e => { const did = e.target.closest('.doc').dataset.id; await api('/api/properties', {aktion: 'dokument_entfernen', id, dokument_id: did}); S.CFG = await api('/api/config'); route(); }));
  $$('.doc-open', main).forEach(b => b.addEventListener('click', async e => { const did = e.target.closest('.doc').dataset.id; const d = (im.dokumente || []).find(x => x.id === did); try { const r = await api('/api/file/open', {pfad: d.pfad}); if (r.status === 'icloud') toast(t('datei_liegt_in_icloud_und'), 5000); } catch (er) { toast(er.message, 5000); } }));
  $$('.doc-show', main).forEach(b => b.addEventListener('click', async e => { const did = e.target.closest('.doc').dataset.id; const d = (im.dokumente || []).find(x => x.id === did); try { await api('/api/file/reveal', {pfad: d.pfad}); } catch (er) { toast(er.message, 5000); } }));
}

// ---------------------------------------------------------------- Depots
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
  let h = `<div class="toolbar">
    <select id="uf-ent"><option value="">${t('alle_bereiche')}</option>${Object.keys(S.DATA.bereiche).map(k => `<option value="${k}" ${f.entitaet === k ? 'selected' : ''}>${esc(BN(k))}</option>`).join('')}</select>
    <select id="uf-jahr"><option value="">${t('alle_jahre')}</option>${UMS.jahre.map(y => `<option ${f.jahr === y ? 'selected' : ''}>${y}</option>`).join('')}</select>
    <select id="uf-konto"><option value="">${t('alle_konten')}</option>${konten.map(k => `<option value="${k.uuid}" ${f.konto === k.uuid ? 'selected' : ''}>${esc(k.name)}</option>`).join('')}</select>
    <input type="search" id="uf-q" placeholder="${t('suche_name_zweck_kategorie_betrag')}" value="${esc(f.q)}" style="min-width:220px">
    <div class="seg"><button data-r="" class="${!f.richtung ? 'on' : ''}">${t('alle_2')}</button><button data-r="aus" class="${f.richtung === 'aus' ? 'on' : ''}">${t('ausgaben')}</button><button data-r="ein" class="${f.richtung === 'ein' ? 'on' : ''}">${t('einnahmen')}</button></div>
    <label class="switch"><input type="checkbox" id="uf-ob" ${f.ohne_beleg ? 'checked' : ''}><i></i>${t('ohne_beleg_2')}</label>
    <label class="switch"><input type="checkbox" id="uf-ok" ${f.ohne_kategorie ? 'checked' : ''}><i></i>${t('ohne_kategorie_2')}</label>
  </div>
  <div class="toolbar"><span class="muted small">${t('0_treffer_1_von_2', UMS.treffer, UMS.treffer > UMS.umsaetze.length ? ' (erste ' + UMS.umsaetze.length + t('angezeigt_filter_verfeinern') : '', UMS.gesamt)}</span><span class="sp"></span>
    <button id="bl-folder" class="secondary small" ${st.lokal ? '' : t('disabled_title_nur_am_mac')}>${t('belegordner_oeffnen')}</button>
    <button id="bl-export" class="secondary small">${t('belege_exportieren_zip')}</button>
    ${xlsxBtn('transactions', f.entitaet ? `data-bereich="${f.entitaet}"` : '')} ${xlsxBtn('receipts')}</div>`;
  if (S.sel.size) h += `<div class="banner info" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">${t('0_ausgewaehlt_1', S.sel.size, `<input type="text" id="bulk-cat" list="bulk-kats" placeholder="${t('kategorie')}" style="min-width:240px">${katList('bulk-kats')}<button id="bulk-cat-btn" class="small">${t('kategorie_zuweisen')}</button>`)}<button id="bulk-clear" class="small secondary">${t('auswahl_aufheben')}</button></div>`;
  h += `<div class="wrap"><table class="plain" id="ums-table"><thead><tr><th style="width:28px"><input type="checkbox" id="sel-all"></th><th>${t('datum')}</th><th>${t('konto_2')}</th><th>${t('name')}</th><th>${t('verwendungszweck')}</th><th class="num">${t('betrag')}</th><th>${t('kategorie')}</th><th class="num">${t('belege')}</th></tr></thead><tbody>`
    + UMS.umsaetze.map(u => `<tr class="clickable ${S.sel.has(u.id) ? 'sel' : ''}" data-id="${u.id}"><td><input type="checkbox" class="sel" ${S.sel.has(u.id) ? 'checked' : ''}></td><td class="small" style="white-space:nowrap">${FD(u.datum)}</td><td class="small">${esc(u.konto_name)}</td><td>${esc(u.name)}</td><td class="small muted" style="max-width:360px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(u.zweck)}</td><td class="num ${u.betrag < 0 ? 'neg' : 'pos'}">${F(u.betrag)}</td><td class="small" title="${u.quelle === 'regel' ? t('per_kontor_regel') : u.quelle === 'manuell' ? t('in_kontor_zugeordnet') : u.quelle === 'moneymoney' ? t('aus_moneymoney_2') : ''}">${u.kategorie ? esc(u.kategorie) + (u.quelle === 'regel' ? ' <span class="muted">R</span>' : u.quelle === 'manuell' ? ' <span class="muted">K</span>' : '') : `<span class="pill warn">${t('ohne')}</span>`}</td><td class="num">${u.belege ? `<span class="pill ok">${u.belege}</span>` : `<button class="ghost small add-beleg" title="${t('beleg_hinzufuegen')}">＋</button>`}</td></tr>`).join('')
    + '</tbody></table></div>';
  return h;
}
async function openDrawer(txId) {
  const u = UMS.umsaetze.find(x => x.id === txId); if (!u) return;
  S.drawerTx = txId;
  const [bl] = await Promise.all([api('/api/receipts?files=1'), KZ.kat ? Promise.resolve() : loadKat().catch(() => null)]);
  const mine = bl.eintraege.filter(e => e.tx_id === txId), free = bl.dateien.filter(d => !d.verknuepft);
  const st = S.STATUS;
  const d = $('#drawer');
  const QUELLE = {manuell: t('in_kontor_zugeordnet'), regel: t('per_kontor_regel'), moneymoney: t('aus_moneymoney_2'), '': ''};
  d.innerHTML = `<button class="close icon">✕</button><h2>${esc(u.name)}</h2>
    <div class="kv"><div>${t('datum')}</div><div>${FD(u.datum)}</div><div>${t('betrag')}</div><div class="${u.betrag < 0 ? 'neg' : 'pos'}" style="font-weight:600;color:var(--${u.betrag < 0 ? 'neg' : 'pos'})">${F(u.betrag)} €</div><div>${t('konto_2')}</div><div>${esc(u.konto_name)} · ${esc(BN(u.entitaet))}</div><div>${t('zweck')}</div><div>${esc(u.zweck) || '–'}</div><div>${t('kategorie')}</div><div>${esc(u.kategorie) || `<span class="pill warn">${t('ohne')}</span>`}${u.quelle ? ' <span class="small muted">· ' + QUELLE[u.quelle] + '</span>' : ''}</div><div>${t('status')}</div><div>${u.gebucht ? t('gebucht') : t('vorgemerkt')}${u.haken ? t('abgehakt') : ''}</div><div>${t('id')}</div><div class="mono small">${u.id}</div></div>
    <div class="row tight" style="margin-top:10px"><input type="text" id="dr-kat" list="dr-kats" value="${esc(u.kategorie || '')}" placeholder="${t('kategorie_in_kontor_neu_anlegen')}" style="min-width:240px;flex:1">${katList('dr-kats')}<label class="chk small"><input type="checkbox" id="dr-rule"> ${t('regel_fuer_0', esc((u.name || '').slice(0, 24)))}</label><button id="dr-cat-btn" class="small">${t('zuordnen')}</button></div>${mmWriteNote()}
    <h3>${t('belege_n', mine.length)}</h3>
    ${mine.map(e => `<div class="beleg" data-id="${e.id}"><span class="n" title="${esc(e.pfad)}">${e.extern ? `<span class="tag" title="${t('verknuepfung_zu_einer_datei_ausserhalb')}">${t('mac')}</span>` : ''}${esc(e.pfad.split('/').pop())}</span><span class="small muted">${e.extern ? (e.status === 'icloud' ? `<span class="pill warn">${t('icloud_nicht_geladen')}</span>` : e.status === 'fehlt' ? `<span class="pill err">${t('fehlt')}</span>` : '') : (e.groesse / 1024).toFixed(0) + ' KB'}</span><a href="/api/receipts/file?id=${e.id}" target="_blank" class="small">${t('ansehen')}</a>${st.lokal ? `<button class="ghost small bl-show" title="${t('im_finder_zeigen_2')}">${t('finder')}</button>` : ''}<button class="ghost small bl-note" title="${t('notiz')}">✎</button><button class="ghost small bl-del" title="${e.extern ? t('verknuepfung_entfernen_datei_bleibt') : t('zuordnung_entfernen')}">✕</button></div>${e.notiz ? `<div class="small muted" style="padding:0 0 6px">${esc(e.notiz)}</div>` : ''}`).join('') || `<div class="muted small">${t('noch_kein_beleg')}</div>`}
    <div class="drop" id="dr-drop" style="margin-top:12px">${t('datei_hierher_ziehen')}<br><button id="dr-pick" class="small" style="margin-top:8px">${t('datei_waehlen')}</button> <button id="dr-cam" class="small secondary" style="margin-top:8px">${t('foto_aufnehmen')}</button><div class="small muted" style="margin-top:6px">${t('pdf_bilder_e_mails_office')}</div></div>
    ${free.length ? `<h3>${t('vorhandene_datei_aus_dem_belegordner')}</h3><div class="row tight"><select id="dr-free" style="max-width:300px">${free.map(x => `<option value="${esc(x.pfad)}">${esc(x.pfad)}</option>`).join('')}</select><button id="dr-link" class="small secondary">${t('zuordnen')}</button></div>` : ''}
    <h3>${t('datei_auf_dem_mac_verknuepfen', hq('dokumente'))}</h3><div class="row tight"><input type="text" id="dr-ext" placeholder="${t('pfad_z_b_library_mobile')}" style="flex:1;min-width:220px">${st.lokal ? `<button id="dr-ext-pick" class="small secondary">${t('datei_waehlen_2')}</button>` : ''}<button id="dr-ext-link" class="small secondary">${t('verknuepfen')}</button></div><div class="small muted">${t('die_datei_bleibt_wo_sie')}</div>`;
  d.classList.add('open');
  $('.close', d).onclick = closeDrawer;
  $('#dr-pick', d).onclick = () => pickFiles(txId, false);
  $('#dr-cam', d).onclick = () => pickFiles(txId, true);
  const dz = $('#dr-drop', d);
  dz.ondragover = e => { e.preventDefault(); dz.classList.add('over'); }; dz.ondragleave = () => dz.classList.remove('over');
  dz.ondrop = async e => { e.preventDefault(); dz.classList.remove('over'); await uploadFiles(txId, e.dataTransfer.files); };
  const lk = $('#dr-link', d); if (lk) lk.onclick = async () => { try { await api('/api/receipts/link', {tx_id: txId, pfad: $('#dr-free', d).value}); toast(t('zugeordnet')); await refreshUms(txId); } catch (e) { toast(e.message, 5000); } };
  $$('.bl-del', d).forEach(b => b.onclick = async e => { const id = e.target.closest('.beleg').dataset.id, ent = mine.find(x => x.id === id); const del = ent && ent.extern ? false : confirm(t('zuordnung_entfernen_datei_auch_loesche')); try { await api('/api/receipts/remove', {id, datei_loeschen: del}); await refreshUms(txId); } catch (er) { toast(er.message, 5000); } });
  const ep = $('#dr-ext-pick', d); if (ep) ep.onclick = async () => { toast(t('dateiauswahl_am_mac_geoeffnet'), 4000); try { const r = await api('/api/file/choose', {art: 'datei', prompt: t('beleg_fuer') + u.name}); if (r.ok) $('#dr-ext', d).value = r.pfad; else toast(r.text); } catch (er) { toast(er.message, 5000); } };
  const el = $('#dr-ext-link', d); if (el) el.onclick = async () => { const pfad = $('#dr-ext', d).value.trim(); if (!pfad) return toast(t('pfad_fehlt')); try { await api('/api/receipts/link', {tx_id: txId, pfad, extern: true}); toast(t('verknuepft')); await refreshUms(txId); } catch (er) { toast(er.message, 6000); } };
  $$('.bl-note', d).forEach(b => b.onclick = async e => { const id = e.target.closest('.beleg').dataset.id, ent = mine.find(x => x.id === id); const n = prompt(t('notiz_zum_beleg'), ent.notiz || ''); if (n === null) return; await api('/api/receipts/update', {id, notiz: n}); await refreshUms(txId); });
  $$('.bl-show', d).forEach(b => b.onclick = async e => { const id = e.target.closest('.beleg').dataset.id, ent = mine.find(x => x.id === id); try { await api('/api/receipts/open', {pfad: ent.pfad}); } catch (er) { toast(er.message, 4000); } });
  const cb = $('#dr-cat-btn', d); if (cb) cb.onclick = async () => { const kat = $('#dr-kat', d).value.trim(); const extra = ($('#dr-rule', d).checked && kat) ? {regel: {name_enthaelt: u.name}} : {}; try { const r = await assignCats([txId], kat, extra); toast(kat ? assignMsg(r) : t('zuordnung_entfernt'), 5000); await loadAll(); await refreshUms(txId); } catch (e) { toast(e.message, 5000); } };
}
function closeDrawer() { $('#drawer').classList.remove('open'); S.drawerTx = null; }
async function belegeApi(path, body) {
  // Erster Beleg: Ordner nur nach Rueckfrage anlegen (oder anderen Ordner in den Einstellungen waehlen)
  try { return await api(path, body); }
  catch (e) {
    if (!(e.data && e.data.ordner_bestaetigen)) throw e;
    if (!confirm(t('belege_werden_im_ordner') + e.data.ordner + t('abgelegt_den_ordner_jetzt_anlegen'))) { location.hash = '#einstellungen'; throw new Error(t('err_kein_belegordner')); }
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
    if (f.size > 60 * 1024 * 1024) { toast(f.name + t('zu_gross_max_60_mb'), 5000); continue; }
    toast(t('lade') + f.name + ' …', 60000);
    try {
      const b64 = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1] || ''); r.onerror = rej; r.readAsDataURL(f); });
      await belegeApi('/api/receipts/upload', {tx_id: txId, datei_name: f.name, inhalt: b64});
      toast(f.name + ' abgelegt');
    } catch (e) { toast(t('fehler_3') + e.message, 6000); }
  }
  await refreshUms(txId);
}

// ---------------------------------------------------------------- Regeln
function acctOptions(selected, filter) {
  const sel = (selected || '').split('|')[0].trim();
  return `<option value="">${t('waehlen')}</option>` + S.KONTEN.filter(filter || (() => true)).map(k =>
    `<option value="${k.uuid} | ${esc(k.name)}" ${k.uuid === sel ? 'selected' : ''}>${' '.repeat(k.ebene * 3)}${esc(k.name)}${k.gruppe ? t('gruppe_suffix') : (k.manuell ? t('manuell_2') : '')}</option>`).join('')
    + (sel && !S.KONTEN.some(k => k.uuid === sel) ? `<option value="${esc(selected)}" selected>${t('0_nicht_gefunden', esc(selected))}</option>` : '');
}
const onlyManual = k => !k.gruppe && k.manuell, onlyGroups = k => k.gruppe, onlyLeaves = k => !k.gruppe;
function vRegeln() {
  const C = S.CFG;
  let h = `<div class="note">${t('regeln_schreiben_ausschliesslich_in_ma')}` + (S.KONTEN.length ? '' : ` <b>${t('noch_keine_konten_geladen_unter')}</b>`) + '</div>';
  h += `<h2>${t('darlehen')} <span class="x">${t('rate_erkennen_auf_dem_darlehenskonto')}</span></h2><div class="list" id="loans">`;
  (C.darlehen || []).forEach((l, i) => { h += loanForm(l, i); });
  h += `</div><div class="actions"><button id="add-loan" class="secondary">${t('darlehen_hinzufuegen')}</button></div>`;
  h += `<h2>${t('beteiligungen')} <span class="x">${t('wert_anteil_nettowert_einer_kontengrup')}</span></h2><div class="list" id="bets">`;
  (C.beteiligungen || []).forEach((b, i) => { h += mirrorForm(b, i, 'bet'); });
  h += `</div><div class="actions"><button id="add-bet" class="secondary">${t('beteiligung_hinzufuegen')}</button></div>`;
  h += `<h2>${t('saldo_spiegel')} <span class="x">${t('zielkonto_faktor_quellkonto_z_b')}</span></h2><div class="list" id="mirrors">`;
  (C.saldo_spiegel || []).forEach((b, i) => { h += mirrorForm(b, i, 'mirror'); });
  h += `</div><div class="actions"><button id="add-mirror" class="secondary">${t('spiegel_hinzufuegen')}</button><button id="save-rules">${t('speichern_und_pruefen')}</button></div><div id="findings" class="findings"></div>`;
  return h;
}
function loanForm(l, i) {
  const z = l.zins || {}, b = l.buchung || {}, e = l.erkennung || {};
  const satz = (z.satz || []).map(s => `${s.ab}: ${s.prozent}`).join('; ');
  return `<div class="item" data-i="${i}"><div class="grow"><div class="form">
    <label>${t('name')}</label><input type="text" class="f-name" value="${esc(l.name || '')}">
    <label>${t('aktiv')}</label><label class="chk"><input type="checkbox" class="f-aktiv" ${l.aktiv === false ? '' : 'checked'}></label>
    <label>${t('darlehenskonto_manuell_0', hq('darlehen_konto'))}</label><select class="f-konto">${acctOptions(l.darlehenskonto, onlyManual)}</select>
    <label>${t('quellkonto_zahlungen_0', hq('darlehen_quelle'))}</label><select class="f-quelle">${acctOptions((l.quellkonten || [])[0], onlyLeaves)}</select>
    <label>${t('gegen_iban_0', hq('darlehen_iban'))}</label><input type="text" class="f-iban" value="${esc(e.gegen_iban || '')}" placeholder="${t('de_iban_des_darlehensgebers_nehmers')}">
    <label>${t('oder_text_enthaelt')}</label><input type="text" class="f-text" value="${esc((e.text_enthaelt || []).join('; '))}" placeholder="${t('z_b_darlehen_mustermann_wenn')}">
    <label>${t('ausschliessen_wenn_text_enthaelt')}</label><input type="text" class="f-excl" value="${esc((e.ausschliessen_text || []).join('; '))}" placeholder="${t('z_b_nebenkosten_kaution')}">
    <label>${t('art')}</label><select class="f-art"><option value="verbindlichkeit" ${l.art !== 'forderung' ? 'selected' : ''}>${t('verbindlichkeit_ich_zahle')}</option><option value="forderung" ${l.art === 'forderung' ? 'selected' : ''}>${t('forderung_ich_erhalte')}</option></select>
    <label>${t('automatik_ab')}</label><input type="date" class="f-ab" value="${esc(l.ab_datum || '')}">
    <label>${t('zinsmodell_0', hq('zinsmodell'))}</label><select class="f-modell"><option value="jahresbasis" ${z.modell !== 'restschuld_monatlich' && z.satz ? 'selected' : ''}>${t('jahresbasis_satz_stand_31_12')}</option><option value="restschuld_monatlich" ${z.modell === 'restschuld_monatlich' ? 'selected' : ''}>${t('restschuld_monatlich_satz_12_stand')}</option><option value="" ${!z.satz ? 'selected' : ''}>${t('keine_zinsen_nur_spiegeln')}</option></select>
    <label>${t('zinssaetze_ab_0', hq('satz'))}</label><input type="text" class="f-satz" value="${esc(satz)}" placeholder="2025-11-20: 3,3; 2027-01-01: 3,0">
    <label>${t('zinsbuchung')}</label><select class="f-tag"><option value="mit_rate" ${z.buchungstag !== 'ultimo' ? 'selected' : ''}>${t('am_tag_der_rate_sonst')}</option><option value="ultimo" ${z.buchungstag === 'ultimo' ? 'selected' : ''}>${t('ultimo')}</option></select>
    <label>${t('jahresbasis_erzwingen_jahr_betrag_0', hq('basis_override'))}</label><input type="text" class="f-basis" value="${esc(Object.entries(z.basis_override || {}).map(([k, v]) => k + '=' + v).join('; '))}" placeholder="2026=160000">
    <label>${t('gegenpartei')}</label><input type="text" class="f-gp" value="${esc(b.gegenpartei || '')}">
    <label>${t('kategorie_tilgung')}</label><select class="f-kt">${catOptions(b.kategorie_tilgung)}</select>
    <label>${t('kategorie_zinsen')}</label><select class="f-kz">${catOptions(b.kategorie_zins)}</select>
  </div></div><button class="danger small del">${t('entfernen')}</button></div>`;
}
function mirrorForm(b, i, kind) {
  return `<div class="item" data-i="${i}" data-kind="${kind}"><div class="grow"><div class="form">
    <label>${t('name')}</label><input type="text" class="f-name" value="${esc(b.name || '')}">
    <label>${t('aktiv')}</label><label class="chk"><input type="checkbox" class="f-aktiv" ${b.aktiv === false ? '' : 'checked'}></label>
    <label>${t('zielkonto_manuell')}</label><select class="f-ziel">${acctOptions(b.zielkonto || b.beteiligungskonto, onlyManual)}</select>
    <label>${kind === 'bet' ? t('kontengruppe_wert') : t('quellkonto')} ${hq(kind === 'bet' ? 'beteiligung' : 'spiegel')}</label><select class="f-quelle">${acctOptions(kind === 'bet' ? b.gruppe : b.quellkonto, kind === 'bet' ? onlyGroups : onlyLeaves)}</select>
    <label>${kind === 'bet' ? t('anteil_01') : t('faktor_2')}</label><input type="number" step="0.0001" class="f-anteil" value="${kind === 'bet' ? (b.anteil ?? 0.5) : (b.faktor ?? -1)}">
    <label>${t('schwelle_2')}</label><input type="number" step="0.01" class="f-schwelle" value="${b.schwelle ?? 0.01}">
    <label>${t('gegenpartei_buchungstext')}</label><input type="text" class="f-gp" value="${esc((b.buchung || {}).gegenpartei || '')}" placeholder="${t('optional')}">
  </div></div><button class="danger small del">${t('entfernen')}</button></div>`;
}
function catOptions(selected) {
  const leaves = S.KATS.filter(k => !k.gruppe);
  return `<option value="">${t('keine_2')}</option>` + leaves.map(k => `<option value="${esc(k.name)}" ${k.name === selected ? 'selected' : ''}>${esc(k.pfad)}</option>`).join('') + (selected && !leaves.some(k => k.name === selected) ? `<option value="${esc(selected)}" selected>${t('0_nicht_in_moneymoney', esc(selected))}</option>` : '');
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
    S.CFG = r.config; if (((r.config.oberflaeche || {}).sprache || 'de') !== LANG) { setLang(r.config.oberflaeche.sprache); return true; }
    showFindings(findingsEl, probleme, t('gespeichert_2') + (S.KONTEN.length ? '' : t('noch_nicht_gegen_moneymoney_geprueft')), 'ok'); toast(t('gespeichert'));
    S.STATUS = await api('/api/status'); statusMini();
    return true;
  } catch (e) {
    if (e.data && e.data.befunde) { showFindings(findingsEl, e.data.befunde, t('nicht_gespeichert_fehler_beheben_oder'), 'fehler'); findingsEl.insertAdjacentHTML('beforeend', '<div class="actions"><button id="save-anyway" class="danger small">Trotzdem speichern</button></div>'); $('#save-anyway').addEventListener('click', () => saveConfig(cfg, findingsEl, true)); }
    else toast(t('fehler_3') + e.message, 5000);
    return false;
  }
}

// ---------------------------------------------------------------- Kategorien
const subTabs = (base, items) => `<div class="tabs">${items.map(([k, l]) => `<button data-next="#${base}${k ? '/' + k : ''}" class="${S.sub === k ? 'on' : ''}">${l}</button>`).join('')}</div>`;
async function vKategorien() {
  // Reiter: Zuordnen (offene Umsätze) · Auswahl (welche Kategorien Kontor nutzt) · Kategorien & Regeln · Kapitalfluss-Zuordnung
  const offen = ((S.DATA && S.DATA.kategorien || {}).gesamt || {}).ohne;
  const tabs = subTabs('kategorien', [['', t('zuordnen') + (offen ? ` (${offen})` : '')], ['auswahl', t('kat_auswahl')], ['regeln', t('kontor_kategorien_regeln')], ['kapitalfluss', t('kapitalfluss_zuordnung')]]);
  if (S.sub === 'auswahl') { await loadKat(); return tabs + vKategorienAuswahl(); }
  if (S.sub === 'regeln') { await loadKat(); return tabs + vKontorKategorien(); }
  if (S.sub === 'kapitalfluss') { await loadKat(); return tabs + vKapitalflussZuordnung(); }
  return tabs + await vZuordnen();
}
function vKategorienAuswahl() {
  // Je Kategorie aus MoneyMoney: eigene Zeile, zur Oberkategorie zusammenfassen oder in Kontor nicht verwenden
  const v = (KZ.kat || {}).verwendung || {}, n = (KZ.kat || {}).anzahl || {};
  const cats = S.KATS.filter(k => !k.standard);
  if (!cats.length) return `<div class="card"><div class="d">${t('noch_keine_kategorien_geladen_abgleich')}</div></div>`;
  const sum = p => Object.entries(n).reduce((s, [k, c]) => s + (k === p || k.startsWith(p + ' / ') ? c : 0), 0);    // mit Unterkategorien
  let h = `<div class="note">${t('kat_auswahl_note', hq('kat_auswahl'))}</div>
    <div class="toolbar"><button class="secondary small" id="ka-top">${t('nur_oberste_ebene')}</button><button class="secondary small" id="ka-alle">${t('alle_als_zeile')}</button><span class="sp"></span><button id="ka-save">${t('speichern')}</button></div>
    <div class="wrap auto"><table class="plain ka-table"><thead><tr><th>${t('kategorie_in_moneymoney')}</th><th class="num">${t('umsaetze_2')}</th><th>${t('in_kontor')}</th></tr></thead><tbody>`;
  for (const k of cats) {
    const p = k.pfad, root = !p.includes(' / '), cur = v[p] || 'zeile';
    const opts = [['zeile', t('eigene_zeile')], ...(root ? [] : [['zusammen', t('zur_oberkategorie')]]), ['ignorieren', t('nicht_verwenden')]];
    h += `<tr data-p="${esc(p)}"><td style="padding-left:${10 + 18 * (p.split(' / ').length - 1)}px">${k.gruppe ? `<b>${esc(k.name)}</b>` : esc(k.name)}</td><td class="num small">${sum(p) || ''}</td>
      <td><select class="ka-v">${opts.map(([val, l]) => `<option value="${val}" ${cur === val ? 'selected' : ''}>${l}</option>`).join('')}</select></td></tr>`;
  }
  return h + '</tbody></table></div>';
}
function bindKatAuswahl(main) {
  const rows = $$('.ka-table tr[data-p]', main); if (!rows.length) return;
  // Unterkategorien folgen einer Oberkategorie, die zusammengefasst oder nicht verwendet wird
  const upd = () => {
    const val = Object.fromEntries(rows.map(r => [r.dataset.p, $('.ka-v', r).value]));
    rows.forEach(r => {
      const parts = r.dataset.p.split(' / '); let inh = null;
      for (let i = 1; i < parts.length && !inh; i++) { const a = val[parts.slice(0, i).join(' / ')]; if (a && a !== 'zeile') inh = a; }
      const sel = $('.ka-v', r); r.classList.toggle('ka-inh', !!inh); sel.disabled = !!inh; sel.title = inh ? t('folgt_der_oberkategorie') : '';
    });
  };
  rows.forEach(r => $('.ka-v', r).addEventListener('change', upd)); upd();
  $('#ka-top', main).onclick = () => { rows.forEach(r => { const sel = $('.ka-v', r); if (r.dataset.p.split(' / ').length === 2 && sel.value === 'zeile') sel.value = 'zusammen'; }); upd(); };
  $('#ka-alle', main).onclick = () => { rows.forEach(r => { $('.ka-v', r).value = 'zeile'; }); upd(); };
  $('#ka-save', main).onclick = async () => {
    const verwendung = {}; rows.forEach(r => { const sel = $('.ka-v', r); if (!sel.disabled && sel.value !== 'zeile') verwendung[r.dataset.p] = sel.value; });
    try { const r = await api('/api/categories/usage', {verwendung}); toast(t('gespeichert')); KZ.kat = null; afterRebuild(r); route(); } catch (e) { toast(e.message, 6000); }
  };
}
function vKapitalflussZuordnung() {
  const kf = S.CFG.kapitalfluss || {}, zu = kf.kategorie_zuordnung || {}, zk = kf.kategorie_zu_konto || {}, umb = kf.umbuchungs_kategorien || ['Umbuchung'];
  const kontorTops = KZ.kat ? [...new Set(KZ.kat.baum.map(k => k.pfad.split(' / ')[0]))] : [];
  const tops = S.KATS.filter(k => k.ebene === 0).map(k => ({name: k.name, budget: k.budget}));
  for (const n of kontorTops) if (!tops.some(t => t.name === n)) tops.push({name: n, budget: null});
  let h = `<div class="note">${t('zuordnung_der_oberkategorien_kontor_un')}` + (tops.length ? '' : ` <b>${t('noch_keine_kategorien_geladen_abgleich')}</b>`) + '</div>';
  h += `<div class="wrap auto"><table class="plain"><thead><tr><th>${t('oberkategorie')}</th><th>${t('abschnitt')}</th><th>${t('kaeufe_fliessen_in_depot_anlage')}</th><th class="num">${t('budget_moneymoney')}</th></tr></thead><tbody>`;
  for (const t of tops) {
    const cur = zu[t.name] || '';
    h += `<tr data-cat="${esc(t.name)}"><td>${esc(t.name)}${umb.includes(t.name) ? `<span class="tag">${tx('tag_umbuchung')}</span>` : ''}</td><td><select class="k-sek"><option value="">${tx('automatisch')}</option>${[['Einnahmen', 'sek_einnahmen'], ['Ausgaben', 'sek_ausgaben'], ['Investitionen', 'sek_investitionen'], ['Finanzierung/Tilgung', 'sek_fin_tilgung'], ['Finanzierung/Zinsen', 'sek_fin_zinsen'], ['Ignorieren', 'sek_ignorieren']].map(([x, k]) => `<option value="${x}" ${cur === x ? 'selected' : ''}>${tx(k)}</option>`).join('')}</select></td><td><select class="k-depot">${acctOptions(zk[t.name], k => !k.gruppe && (k.depot || k.rolle === 'anlagen'))}</select></td><td class="num small muted">${t.budget ? F0(t.budget.amount) + ' / ' + esc(t.budget.period || '') : ''}</td></tr>`;
  }
  h += '</tbody></table></div>';
  h += `<div class="form" style="margin-top:12px"><label>${t('umbuchungs_kategorien')}</label><input type="text" id="k-umb" value="${esc(umb.join('; '))}"><label>${t('beteiligungsgruppen_einlagen_zaehlen_a')}</label><div>${[0, 1, 2].map(i => `<select class="k-bg">${acctOptions((kf.beteiligungs_gruppen || [])[i], onlyGroups)}</select>`).join(' ')}</div></div>`;
  h += `<div class="actions"><button id="save-kats">${t('speichern')}</button></div><div id="findings-k" class="findings"></div>`;
  const have = new Set(S.KATS.map(k => k.pfad));
  const rec = [
    ['Finanzierung', t('oberkategorie_fuer_zins_und_tilgungsbu')],
    ['Finanzierung / Zinsen', t('zinsbuchungen_der_darlehensregeln_dann')],
    ['Finanzierung / Tilgung', t('zahlungen_an_private_darlehensgeber')],
    ['Steuern', t('einkommensteuer_vorauszahlungen_und_na')],
    ['Einkommen / Gehalt', t('anlage_n')], ['Einkommen / Kapitalerträge', t('anlage_kap_zinsen_dividenden')],
    ['Einkommen / Ausschüttungen', t('entnahmen_ausschuettungen_aus_beteilig')],
    [(S.CFG.steuer && S.CFG.steuer.vermietung_kategorie) || 'Vermietung', t('oberkategorie_darunter_je_objekt_miete')],
  ].filter(([p]) => !have.has(p));
  if (rec.length && tops.length) h += `<h2>${t('empfohlene_ergaenzungen')} <span class="x">${t('in_moneymoney_anlegen_bestehende_buchu')}</span></h2><div class="wrap auto"><table class="plain"><thead><tr><th>${t('kategorie')}</th><th>${t('zweck')}</th></tr></thead><tbody>` + rec.map(([p, z]) => `<tr><td>${esc(p)}</td><td>${esc(z)}</td></tr>`).join('') + '</tbody></table></div>';
  return h;
}

// ---------------------------------------------------------------- Zuordnen (Kontor-Kategorien)
const KZ = {jahr: '', bereich: '', min: '', open: {}, kat: null, offen: null};
async function assignCats(ids, kat, extra = {}) {
  // In Kontor zuordnen; ist das Zurückschreiben an, setzt Kontor die Kategorie auch in MoneyMoney (vorher geprüft).
  // Steht dort schon eine andere (nicht von Kontor gesetzte) Kategorie: nachfragen – überschreiben oder nur in Kontor.
  const r = await api('/api/categories/assign', Object.assign({ids, kategorie: kat}, extra));
  const mm = r.mm || {}, f = mm.fremd || [];
  if (f.length) {
    const bsp = [...new Set(f.map(x => x.mm))].slice(0, 3).map(x => '„' + esc(x) + '“').join(', ');
    const v = await choose(tn('mm_fremd_frage', f.length, bsp, esc(kat)), [['ueberschreiben', t('in_moneymoney_ueberschreiben')], ['nur_kontor', t('nur_in_kontor'), 'secondary']]);
    if (v) {
      const r2 = (await api('/api/categories/assign', {ids: f.map(x => x.id), kategorie: kat, modus: v})).mm || {};
      mm.geschrieben += r2.geschrieben || 0; mm.nur_kontor = (mm.nur_kontor || 0) + (r2.nur_kontor || 0); mm.fehler += r2.fehler || 0;
    }
    mm.fremd = v ? [] : f;
  }
  return r;
}
function assignMsg(r) {
  // Rückmeldung: zugeordnet · in MoneyMoney · wartet auf Kategorie · nur in Kontor · abweichend
  const m = r.mm || {}, p = [t('0_zugeordnet', r.anzahl) + (r.regel ? t('regel_angelegt') : '')];
  if (m.geschrieben) p.push(t('0_in_moneymoney_gesetzt', m.geschrieben));
  if (m.wartet) p.push(t('0_warten_auf_kategorie', m.wartet));
  if (m.aus) p.push(t('nur_in_kontor_zurueckschreiben_aus'));
  if (m.fehler) p.push(t('0_in_moneymoney_abweichend', m.fehler));
  return p.join(' · ');
}
function mmWriteNote() {
  // Hinweis unter dem Zuordnen: wohin die Zuordnung geht
  const st = S.STATUS;
  return `<div class="small muted">${st.lokal && st.moneymoney.kategorisieren_erlaubt ? t('zuordnung_geht_nach_moneymoney') : st.lokal ? t('zuordnung_nur_in_kontor_aus', '<a href="#einstellungen">' + t('einstellungen') + '</a>') : t('zuordnung_nur_in_kontor_unterwegs')}</div>`;
}
async function loadKat() { KZ.kat = await api('/api/categories/kontor'); return KZ.kat; }
const katPaths = () => (KZ.kat ? KZ.kat.baum.map(k => k.pfad) : []);
const katList = id => `<datalist id="${id}">${katPaths().map(p => `<option value="${esc(p)}">`).join('')}</datalist>`;
async function vZuordnen() {
  if (!S.DATA) return noData;
  const [kat, off] = await Promise.all([loadKat(), api(`/api/categories/unassigned?year=${KZ.jahr}&area=${KZ.bereich}&min=${KZ.min}`)]);
  KZ.offen = off;
  const st = (S.DATA.kategorien || {}).gesamt || {}, years = Object.keys((S.DATA.kategorien || {}).jahre || {}).sort().reverse();
  let h = `<div class="toolbar"><select id="kz-bereich"><option value="">${t('alle_bereiche')}</option>${Object.keys(S.DATA.bereiche).map(k => `<option value="${k}" ${KZ.bereich === k ? 'selected' : ''}>${esc(BN(k))}</option>`).join('')}</select>
    <select id="kz-jahr"><option value="">${t('alle_jahre')}</option>${years.map(y => `<option ${KZ.jahr === y ? 'selected' : ''}>${y}</option>`).join('')}</select>
    <label class="chk small">${t('ab')} <input type="number" id="kz-min" value="${esc(KZ.min)}" placeholder="0" style="width:80px"> €</label>
    <span class="sp"></span><button id="kz-lernen" class="secondary small" title="${t('regeln_aus_allen_vorhandenen_zuordnung')}">${t('regeln_neu_lernen')}</button></div>
    <div class="note">${t('0_umsaetze_ohne_kategorie_1', off.offen, off.hinweis ? ' – ' + esc(off.hinweis) : '', off.gruppen_gesamt, st.manuell || 0, st.regel || 0, st.moneymoney || 0, st.ohne || 0, hq('zuordnen'))}</div>` + katList('kz-kats');
  if (!off.zurueckschreiben && S.STATUS.lokal) h += `<div class="banner info">${t('zurueckschreiben_ist_aus')} <button class="small" id="kz-mm-on">${t('einschalten')}</button></div>`;
  if ((off.wartend || []).length) h += `<div class="banner">${t('in_moneymoney_anlegen_wartend', off.wartend.map(w => `<b>${esc(w.kategorie.replace(/ \/ /g, ' \\ '))}</b> (${tn('n_umsaetze', w.anzahl, w.anzahl)})`).join(', '))}</div>`;
  if (!off.gruppen.length) return h + `<div class="card"><div class="v s">${t('nichts_offen_2')}</div><div class="d">${t('alle_umsaetze_haben_eine_kategorie')}</div></div>`;
  h += '<div class="list">';
  for (const g of off.gruppen) {
    const open = KZ.open[g.key];
    h += `<div class="item kz-group" data-key="${esc(g.key)}"><div class="grow">
      <div class="row tight"><b style="min-width:220px">${esc(g.name)}</b><span class="small muted">${esc(g.konto)}${g.iban ? ' · ' + esc(g.iban) : ''}</span><span class="tag">${g.anzahl}×</span><span class="num ${g.summe < 0 ? 'neg' : 'pos'}" style="font-weight:600">${F(g.summe)} €</span><span class="small muted">${FD(g.von)}${g.von !== g.bis ? ' – ' + FD(g.bis) : ''}</span><button class="ghost small kz-toggle">${open ? t('beispiele') : t('beispiele_2')}</button></div>
      ${open ? '<div class="small muted" style="margin:4px 0 6px">' + g.beispiele.map(b => `${FD(b.datum)} · ${F(b.betrag)} € · ${esc(b.zweck || '–')}`).join('<br>') + '</div>' : ''}
      <div class="row tight"><input type="text" class="kz-kat" list="kz-kats" value="${esc(g.vorschlag || '')}" placeholder="${t('kategorie_neu_anlegen_z_b')}" style="min-width:300px">${g.vorschlag ? `<span class="tag" title="${t('vorschlag_aus_regel')} ` + esc(g.regel || '') + `${t('vorschlag_2')}</span>` : ''}
        <label class="chk small"><input type="checkbox" class="kz-rule" checked> ${t('regel_fuer_0_2', g.iban ? t('diese_iban') : t('diesen_namen'))}</label>
        <button class="small kz-save">${t('zuordnen')}</button><button class="small secondary kz-umb" title="${t('uebertrag_zwischen_eigenen_konten')}">${t('tag_umbuchung')}</button></div></div></div>`;
  }
  return h + '</div>';
}
function bindZuordnen(main) {
  const bindF = (id, key) => { const el = $(id, main); if (el) el.addEventListener('change', e => { KZ[key] = e.target.value; route(); }); };
  bindF('#kz-bereich', 'bereich'); bindF('#kz-jahr', 'jahr'); bindF('#kz-min', 'min');
  const on = $('#kz-mm-on', main); if (on) on.addEventListener('click', async () => { try { await api('/api/categories/settings', {mm_schreiben: true}); S.CFG = await api('/api/config'); S.STATUS = await api('/api/status'); toast(t('zurueckschreiben_eingeschaltet')); route(); } catch (e) { toast(e.message, 6000); } });
  const ln = $('#kz-lernen', main); if (ln) ln.addEventListener('click', async () => { toast(t('lerne'), 10000); try { const r = await api('/api/categories/learn', {}); toast(`${t('0_regeln_aus_1_umsaetzen', r.gelernt.regeln, r.gelernt.muster, r.zugeordnet)}`, 6000); await loadAll(); route(); } catch (e) { toast(e.message, 6000); } });
  $$('.kz-toggle', main).forEach(b => b.addEventListener('click', e => { const k = e.target.closest('.kz-group').dataset.key; KZ.open[k] = !KZ.open[k]; route(); }));
  const assign = async (box, kat) => {
    const g = KZ.offen.gruppen.find(x => x.key === box.dataset.key); if (!g || !kat) return toast(t('kategorie_fehlt'));
    const extra = $('.kz-rule', box).checked ? {regel: g.iban ? {iban: g.iban} : {name_enthaelt: g.name}} : {};
    try { const r = await assignCats(g.ids, kat, extra); toast(assignMsg(r), 6000); await loadAll(); route(); } catch (e) { toast(e.message, 6000); }
  };
  $$('.kz-save', main).forEach(b => b.addEventListener('click', e => { const box = e.target.closest('.kz-group'); assign(box, $('.kz-kat', box).value.trim()); }));
  $$('.kz-umb', main).forEach(b => b.addEventListener('click', e => { const box = e.target.closest('.kz-group'); assign(box, 'Umbuchung'); }));
  $$('.kz-kat', main).forEach(i => i.addEventListener('keydown', e => { if (e.key === 'Enter') { const box = e.target.closest('.kz-group'); assign(box, e.target.value.trim()); } }));
}
function vKontorKategorien() {
  const kat = KZ.kat; if (!kat) return `<div class="note">${t('lade_2')}</div>`;
  const e = kat.einstellungen || {}, st = kat.statistik || {}, ges = st.gesamt || {};
  let h = `<div class="note">${t('kontor_fuehrt_eigene_kategorien_baum', hq('kontor_kategorien'))}</div>
  <div class="row tight" style="margin-bottom:10px"><label class="switch"><input type="checkbox" id="kk-aktiv" ${e.aktiv !== false ? 'checked' : ''}><i></i>${t('kontor_kategorien_aktiv')}</label><label class="switch"><input type="checkbox" id="kk-lernen" ${e.lernen !== false ? 'checked' : ''}><i></i>${t('bei_jedem_abgleich_regeln_nachlernen')}</label><label class="switch"><input type="checkbox" id="kk-mm" ${e.mm_ueberschreiben ? 'checked' : ''}><i></i>${t('regeln_auch_auf_moneymoney_kategorisie', hq('mm_ueberschreiben'))}</label>
    <span class="small muted">${t('0_kategorien_regeln_1_eigene', st.kategorien || 0, (st.regeln || {}).manuell || 0, (st.regeln || {}).gelernt || 0, st.gelernt_am ? ' (' + esc(st.gelernt_am) + ')' : '', ges.manuell || 0, ges.regel || 0, ges.moneymoney || 0, ges.ohne || 0)}</span></div>`;
  h += `<h2>${t('kategorien')} <span class="x">${kat.baum.length}</span></h2><div class="row tight" style="margin-bottom:6px"><input type="text" id="kk-neu" placeholder="${t('neue_kategorie_z_b_wohnen')}" style="min-width:320px"><button id="kk-add" class="small">${t('anlegen')}</button><button id="kk-mmsync" class="small secondary" title="${t('neue_kategorien_aus_moneymoney_in')}">${t('aus_moneymoney_ergaenzen')}</button></div>
    <div class="wrap auto" style="max-height:420px;overflow:auto"><table class="plain"><thead><tr><th>${t('kategorie')}</th><th>${t('quelle')}</th><th></th></tr></thead><tbody>${kat.baum.map(k => `<tr data-pfad="${esc(k.pfad)}"><td class="ind${Math.min(3, k.pfad.split(' / ').length - 1)}">${esc(k.name)}<span class="small muted"> · ${esc(k.pfad)}</span></td><td class="small">${k.quelle === 'moneymoney' ? 'MoneyMoney' : 'Kontor'}</td><td style="white-space:nowrap"><button class="ghost small kk-ren">${t('umbenennen')}</button><button class="ghost small kk-del">✕</button></td></tr>`).join('')}</tbody></table></div>`;
  h += `<h2>${t('regeln')} <span class="x">${t('eigene_zuerst_spezifischere_gewinnen_i')}</span></h2>
    <div class="row tight" style="margin-bottom:6px"><input type="text" id="kr-name" placeholder="${t('name_enthaelt_2')}" style="width:180px"><input type="text" id="kr-zweck" placeholder="${t('zweck_enthaelt_2')}" style="width:180px"><input type="text" id="kr-iban" placeholder="${t('gegen_iban')}" style="width:200px"><select id="kr-richtung"><option value="">${t('beide_richtungen')}</option><option value="aus">${t('ausgaben')}</option><option value="ein">${t('einnahmen')}</option></select><input type="text" id="kr-kat" list="kk-kats" placeholder="${t('kategorie')}" style="width:220px"><button id="kr-add" class="small">${t('regel_anlegen')}</button></div>${katList('kk-kats')}
    <div class="wrap auto" style="max-height:420px;overflow:auto"><table class="plain"><thead><tr><th>${t('bedingung')}</th><th>${t('kategorie')}</th><th>${t('quelle')}</th><th class="num">${t('treffer')}</th><th></th></tr></thead><tbody>${kat.regeln.map(r => `<tr data-id="${esc(r.id)}"><td class="small">${[r.iban ? 'IBAN ' + esc(r.iban) : '', r.name_ist ? t('name_2') + esc(r.name_ist) + '“' : '', r.name_enthaelt ? t('name_enthaelt') + esc(r.name_enthaelt) + '“' : '', r.zweck_enthaelt ? t('zweck_enthaelt') + esc(r.zweck_enthaelt) + '“' : '', r.richtung ? (r.richtung === 'aus' ? t('ausgaben') : t('einnahmen')) : ''].filter(Boolean).join(' · ')}</td><td>${esc(r.kategorie)}</td><td class="small">${r.quelle === 'manuell' ? t('eigene') : t('gelernt')}</td><td class="num small">${r.treffer ?? ''}</td><td><button class="ghost small kr-del">✕</button></td></tr>`).join('') || `<tr><td colspan="5" class="muted">${t('noch_keine_regeln_regeln_neu')}</td></tr>`}</tbody></table></div>`;
  return h;
}
function bindKontorKategorien(main) {
  const setEinst = async () => { try { await api('/api/categories/settings', {aktiv: $('#kk-aktiv').checked, lernen: $('#kk-lernen').checked, mm_ueberschreiben: $('#kk-mm').checked}); toast(t('gespeichert')); await loadAll(); } catch (e) { toast(e.message, 5000); } };
  for (const id of ['#kk-aktiv', '#kk-lernen', '#kk-mm']) { const el = $(id, main); if (el) el.addEventListener('change', setEinst); }
  const add = $('#kk-add', main); if (add) add.addEventListener('click', async () => { const p = $('#kk-neu').value.trim(); if (!p) return; try { await api('/api/categories/tree', {aktion: 'anlegen', pfad: p}); toast(t('angelegt')); await loadKat(); route(); } catch (e) { toast(e.message, 5000); } });
  const ms = $('#kk-mmsync', main); if (ms) ms.addEventListener('click', async () => { try { await api('/api/categories/tree', {aktion: 'mm_uebernehmen'}); await loadKat(); route(); } catch (e) { toast(e.message, 5000); } });
  $$('.kk-ren', main).forEach(b => b.addEventListener('click', async e => { const p = e.target.closest('tr').dataset.pfad; const n = prompt(t('neuer_pfad_verschieben_oberkategorie_a'), p); if (!n || n === p) return; try { await api('/api/categories/tree', {aktion: 'umbenennen', pfad: p, neu: n}); await loadKat(); await loadAll(); route(); } catch (er) { toast(er.message, 5000); } }));
  $$('.kk-del', main).forEach(b => b.addEventListener('click', async e => { const p = e.target.closest('tr').dataset.pfad; const ers = prompt('„' + p + t('loeschen_zuordnungen_und_regeln_umhaen'), ''); if (ers === null) return; try { await api('/api/categories/tree', {aktion: 'loeschen', pfad: p, ersatz: ers}); await loadKat(); await loadAll(); route(); } catch (er) { toast(er.message, 5000); } }));
  const ra = $('#kr-add', main); if (ra) ra.addEventListener('click', async () => { try { await api('/api/categories/rule', {regel: {name_enthaelt: $('#kr-name').value, zweck_enthaelt: $('#kr-zweck').value, iban: $('#kr-iban').value, richtung: $('#kr-richtung').value, kategorie: $('#kr-kat').value}}); toast(t('regel_angelegt_2')); await loadKat(); await loadAll(); route(); } catch (e) { toast(e.message, 6000); } });
  $$('.kr-del', main).forEach(b => b.addEventListener('click', async e => { const id = e.target.closest('tr').dataset.id; try { await api('/api/categories/rule', {loeschen: id}); await loadKat(); await loadAll(); route(); } catch (er) { toast(er.message, 5000); } }));
}

// ---------------------------------------------------------------- Einstellungen
async function vEinstellungen() {
  // Reiter: Allgemein · Zugang · Updates · Steuer · Sichern & Zuruecksetzen (Bereiche, Konten, Kategorien, Regeln: Einrichtung)
  const tabs = subTabs('einstellungen', [['', t('allgemein')], ['zugang', t('zugang')], ['updates', t('updates')], ['steuer', t('steuer')], ['sichern', t('sichern_zuruecksetzen')]]);
  const v = {zugang: vEinstellungenZugang, updates: vEinstellungenUpdates, steuer: vEinstellungenSteuer, sichern: vSicherung}[S.sub] || vEinstellungenAllgemein;
  return tabs + await v();
}
function vEinstellungenAllgemein() {
  const C = S.CFG, z = C.zeitplan || {}, b = C.bilanz || {}, bl = C.belege || {}, mm = C.moneymoney || {};
  let h = `<div class="note">${t('einstellungen_vs_einrichtung', '<a href="#einrichtung">' + t('einrichtung') + '</a>')}</div><h2>${t('betrieb')}</h2><div class="form">
    <label>${t('sprache_label')}</label><label class="chk"><select id="e-lang">${langOpts()}</select> <span class="small muted">${t('sprache_hinweis')}</span></label>
    <label>${t('testmodus_0', hq('probelauf'))}</label><label class="chk"><input type="checkbox" id="e-probelauf" ${C.probelauf ? 'checked' : ''}> ${t('buchungen_aus_regeln_nur_vorschlagen')}</label>
    <label>${t('automatischer_abgleich_0', hq('abgleich'))}</label><label class="chk"><input type="checkbox" id="e-auto" ${z.automatisch !== false ? 'checked' : ''}> ${t('alle_2')} <input type="number" id="e-intervall" min="5" value="${z.intervall_minuten ?? 30}" style="width:70px"> ${t('minuten_nur_wenn_moneymoney_laeuft')}</label>
    <label>${t('alles_neu_lesen_0', hq('voll_lesen'))}</label><label class="chk">${t('alle_2')} <input type="number" id="e-voll" min="1" value="${z.voll_lesen_stunden ?? 24}" style="width:70px"> ${t('stunden_bevorzugt_nachts')}</label>
    <label>${t('mitteilungen_macos')}</label><label class="chk"><input type="checkbox" id="e-mitt" ${C.mitteilungen !== false ? 'checked' : ''}> ${t('bei_buchungen_vorschlaegen_und_fehlern')}</label>
  </div>
  <h2>MoneyMoney</h2><div class="form">
    <label>${t('umsaetze_lesen_0', hq('monate_zurueck'))}</label><label class="chk">${t('die_letzten')} <input type="number" id="e-monate" min="0" value="${b.monate_zurueck ?? 0}" style="width:70px"> ${t('monate_0_alle')}</label>
    <label>${t('kategorisieren_erlauben_0', hq('mm_cat'))}</label><label class="chk"><input type="checkbox" id="e-mm-cat" ${mm.kategorisieren_erlauben ? 'checked' : ''}> ${t('umsaetzen_aus_kontor_eine_kategorie')}</label>
  </div>
  <h2>${t('belege')}</h2><div class="form">
    <label>${t('belegordner_0', hq('belege_ordner'))}</label><div><input type="text" id="e-bl-ordner" value="${esc(bl.ordner || '~/Documents/Kontor-Belege')}" style="width:100%"><div class="small muted">${bl.ordner_bestaetigt ? t('wird_beim_ersten_beleg_angelegt') : t('noch_nicht_angelegt_beim_ersten')}</div></div>
    <label>${t('unterordner_muster_0', hq('belege_sub'))}</label><input type="text" id="e-bl-sub" value="${esc(bl.unterordner || '{jahr}')}" placeholder="${t('jahr_jahr_entitaet_entitaet_jahr')}">
    <label>${t('verweis_in_moneymoney_0', hq('belege_kommentar'))}</label><label class="chk"><input type="checkbox" id="e-bl-comment" ${bl.kommentar_schreiben ? 'checked' : ''}> ${t('dateipfad_als_kommentar_an_den')}</label>
    <div class="full note">${t('belege_werden_als_normale_dateien_2')}</div>
  </div>
  <div class="actions"><button id="save-settings">${t('einstellungen_speichern')}</button></div><div id="findings-e" class="findings"></div>
`;
  return h;
}
function vEinstellungenSteuer() {
  const st = S.CFG.steuer || {}, loans = S.KONTEN.filter(k => !k.gruppe && k.rolle === 'verbindlichkeiten');
  return `<div class="note">${t('steuer_einstellungen_note')}</div><div class="form">
    <label>${t('vermietungs_oberkategorie')}</label><input type="text" id="e-verm" value="${esc(st.vermietung_kategorie || 'Vermietung')}">
    <div class="full"><h3>${t('darlehen_objekt')}</h3>${loans.length ? `<table class="plain objloans"><thead><tr><th>${t('darlehenskonto')}</th><th>${t('objekt_wie_in_der_kategorie')}</th></tr></thead><tbody>${loans.map(l => `<tr><td>${esc(l.name)}<div class="small muted">${esc(l.pfad.split(' / ').slice(0, -1).join(' / '))}</div></td><td><input type="text" class="e-obj" data-ref="${l.uuid} | ${esc(l.name)}" value="${esc((st.objekt_darlehen || {})[l.uuid + ' | ' + l.name] || Object.entries(st.objekt_darlehen || {}).find(([k]) => k.startsWith(l.uuid))?.[1] || '')}" placeholder="${t('objektname_wie_in_der_kategorie')}"></td></tr>`).join('')}</tbody></table>` : `<span class="muted small">${t('keine_darlehenskonten_erkannt')}</span>`}</div>
    <label>${t('kategorie_steuerposition')}</label><div class="list" id="positions">${Object.entries(st.positionen || {}).filter(([k]) => !k.startsWith('_')).map(([k, v]) => posRow(k, v)).join('')}<button id="add-pos" class="secondary small" style="align-self:flex-start;width:auto">${t('zuordnung_hinzufuegen')}</button></div>
  </div>
  <div class="actions"><button id="save-settings">${t('einstellungen_speichern')}</button></div><div id="findings-e" class="findings"></div>`;
}
async function vEinstellungenZugang() {
  // Am Mac (Sperre, Touch ID, Passwort) · Zugriff vom iPhone über Tailscale: Stand, Einrichtung, wer/wo/was, Feineinstellung
  const o = S.CFG.oberflaeche || {};
  let r = null; try { r = await api('/api/remote'); } catch (e) {}
  const ts = (r && r.tailscale) || {}, lokal = r ? r.lokal : S.STATUS.lokal;
  const ok = b => `<span class="dot ${b ? 'ok' : 'warn'}"></span>`;
  let h = `<h2>${t('zugriff_vom_iphone')} ${hq('fern')}</h2>`;
  if (r && r.aktiv) {
    h += `<div class="banner ${r.lauscht ? 'ok' : 'warn'}">${r.lauscht ? t('fern_an', `<b>${esc(r.url)}</b>`) : t('fern_an_wartet', esc(r.fehler || ''))}</div>
      <div class="row tight"><button class="secondary small" id="fz-copy" data-url="${esc(r.url)}">${t('link_kopieren')}</button>${lokal ? `<button class="danger small" id="fz-aus">${t('zugriff_ausschalten')}</button>` : ''}</div>
      <div class="kv" style="margin-top:12px"><div>${t('wer')}</div><div>${t('fern_wer', esc(ts.konto || '?'))}${(ts.geraete || []).length ? `<div class="small muted">${t('geraete_im_tailnet')}: ${ts.geraete.map(g => esc(g.name) + (g.os ? ' (' + esc(g.os) + ')' : '') + (g.online ? '' : ' · ' + t('offline_klein'))).join(', ')}</div>` : ''}</div>
        <div>${t('wo')}</div><div>${t('fern_wo')}</div>
        <div>${t('was')}</div><div>${r.nur_ansehen ? t('fern_was_lesen') : t('fern_was_bearbeiten')}</div>
        <div>${t('verschluesselung')}</div><div>${r.tls ? t('fern_tls', r.gueltig_bis ? FD(r.gueltig_bis) : '?') : t('fern_ohne_tls')}</div></div>`;
  } else {
    h += `<div class="banner info">${t('fern_aus')}</div><div class="note">${t('fern_warum')}</div>
      <ol class="steps">
        <li>${ok(ts.gefunden && ts.verbunden)} ${t('fern_schritt_mac')} ${ts.gefunden ? (ts.verbunden ? `<span class="small muted">${t('fern_verbunden_als', esc(ts.name || ''), esc(ts.konto || '?'))}</span>` : `<span class="small">${t('fern_nicht_verbunden')}</span>`) : `<a href="https://tailscale.com/download/mac" target="_blank" rel="noopener">${t('herunterladen')}</a>`}</li>
        <li>${ok((ts.geraete || []).some(g => /ios/i.test(g.os)))} ${t('fern_schritt_iphone')} <a href="https://apps.apple.com/app/tailscale/id1470499037" target="_blank" rel="noopener">App Store</a>${(ts.geraete || []).some(g => /ios/i.test(g.os)) ? ` <span class="small muted">${esc(ts.geraete.filter(g => /ios/i.test(g.os)).map(g => g.name).join(', '))}</span>` : ''}</li>
        <li>${ok(ts.https)} ${t('fern_schritt_https')} <a href="https://login.tailscale.com/admin/dns" target="_blank" rel="noopener">${t('tailscale_admin')}</a></li>
        <li>${lokal ? `<button id="fz-ein" ${ts.verbunden ? '' : 'disabled'}>${t('zugriff_einschalten')}</button>${ts.verbunden && !ts.https ? ` <button id="fz-ein-http" class="secondary small">${t('ohne_zertifikat_einschalten')}</button>` : ''}` : t('nur_am_mac')}</li>
        <li>${t('fern_schritt_oeffnen')}</li>
      </ol><div id="fz-msg" class="findings"></div>`;
  }
  h += `<div class="form" style="margin-top:14px">
    <label>${t('von_unterwegs')} ${hq('fern_was')}</label><label class="chk"><select id="fz-modus" ${lokal ? '' : 'disabled'}><option value="lesen" ${!r || r.nur_ansehen ? 'selected' : ''}>${t('nur_ansehen')}</option><option value="bearbeiten" ${r && !r.nur_ansehen ? 'selected' : ''}>${t('ansehen_und_bearbeiten')}</option></select></label>
    <label>${t('offline_ansicht_0', hq('offline'))}</label><label class="chk"><input type="checkbox" id="fz-offline" ${!r || r.offline_kopie ? 'checked' : ''} ${lokal ? '' : 'disabled'}> ${t('offline_kopie_erlauben')}</label>
  </div>`;
  h += `<div class="kv" style="margin-top:12px"><div>${t('auf_diesem_geraet')}</div><div id="sw-state">${navigator.serviceWorker && navigator.serviceWorker.controller ? t('aktiv_die_zuletzt_geladenen_daten') : (location.protocol === 'https:' || location.hostname === '127.0.0.1' ? t('wird_beim_naechsten_laden_aktiv') : t('nicht_moeglich_ueber_http_tailscale'))}</div></div>
    <div class="actions"><button id="sw-clear" class="secondary">${t('gespeicherte_daten_auf_diesem_geraet')}</button></div>`;
  h += `<h2>${t('am_mac')}</h2><div class="form">
    <label>${t('automatische_sperre')}</label><label class="chk">${t('nach_2')} <input type="number" id="e-sperre" min="1" value="${o.sperre_minuten ?? 15}" style="width:70px"> ${t('minuten_ohne_aktivitaet')}</label>
    <label>Touch ID ${hq('touchid')}</label><label class="chk"><input type="checkbox" id="e-touchid" ${o.touchid !== false ? 'checked' : ''} ${S.STATUS.touchid ? '' : 'disabled'}> ${t('am_mac_mit_touch_id', S.STATUS.touchid ? '' : t('an_diesem_geraet_nicht_verfuegbar'))}</label>
  </div>
  <details class="adv"><summary>${t('erweitert_adresse_port')}</summary><div class="form">
    <label>${t('adresse_0', hq('bind'))}</label><input type="text" id="e-bind" value="${esc(o.bind || '127.0.0.1')}" placeholder="${t('127_0_0_1_oder')}">
    <label>${t('port')} ${hq('port')}</label><input type="number" id="e-port" value="${o.port ?? 8765}" style="width:100px">
    <label>${t('tls_zertifikat_optional_0', hq('tls'))}</label><input type="text" id="e-cert" value="${esc(o.tls_cert || '')}" placeholder="/Pfad/zert.crt">
    <label>${t('tls_schluessel_optional')}</label><input type="text" id="e-key" value="${esc(o.tls_key || '')}" placeholder="/Pfad/zert.key">
    <div class="full note">${t('adresse_port_neustart')}</div>
  </div></details>
  <div class="actions"><button id="save-settings">${t('einstellungen_speichern')}</button></div><div id="findings-e" class="findings"></div>
  <h2>${t('passwort')}</h2><div class="form"><label>${t('altes_passwort')}</label><input type="password" id="pw-alt" autocomplete="current-password"><label>${t('neues_passwort')}</label><input type="password" id="pw-neu" autocomplete="new-password"></div><div class="actions"><button id="pw-save" class="secondary">${t('passwort_aendern')}</button></div>`;
  return h;
}
function bindZugang(main) {
  const msg = (txt, cls) => { const el = $('#fz-msg', main); if (el) showFindings(el, [], txt, cls); else toast(txt, 8000); };
  const restartWait = async () => {
    // Dienst startet mit der neuen Adresse neu: warten, bis er wieder antwortet, dann neu laden
    toast(t('kontor_startet_neu'), 15000);
    for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 1000)); try { const r = await fetch('/api/session', {credentials: 'same-origin'}); if (r.ok) { location.reload(); return; } } catch (e) {} }
    location.reload();
  };
  const act = async (aktion, extra = {}) => {
    try { const r = await api('/api/remote', Object.assign({aktion}, extra)); if (!r.ok) { msg(r.text, 'fehler'); return; } if (r.neustart) return restartWait(); S.CFG = await api('/api/config'); route(); }
    catch (e) { msg(e.message, 'fehler'); }
  };
  const on = $('#fz-ein', main); if (on) on.addEventListener('click', () => { on.disabled = true; on.classList.add('busy'); act('ein').finally(() => { on.disabled = false; on.classList.remove('busy'); }); });
  const onh = $('#fz-ein-http', main); if (onh) onh.addEventListener('click', () => { if (confirm(t('ohne_zertifikat_frage'))) act('ein_http'); });
  const off = $('#fz-aus', main); if (off) off.addEventListener('click', () => { if (confirm(t('zugriff_ausschalten_frage'))) act('aus'); });
  const cp = $('#fz-copy', main); if (cp) cp.addEventListener('click', async () => { try { await navigator.clipboard.writeText(cp.dataset.url); toast(t('link_kopiert_iphone'), 5000); } catch (e) { prompt(t('link'), cp.dataset.url); } });
  const md = $('#fz-modus', main); if (md) md.addEventListener('change', () => act('einstellungen', {fern_nur_ansehen: md.value === 'lesen'}));
  const of = $('#fz-offline', main); if (of) of.addEventListener('change', () => act('einstellungen', {offline_kopie: of.checked}));
}
function vEinstellungenUpdates() {
  const up = S.CFG.updates || {};
  return `<h2>${t('updates')}</h2><div class="form">
    <label>${t('automatisch_pruefen_0', hq('updates'))}</label><label class="chk"><select id="e-up-pruefen">${[['taeglich', t('taeglich')], ['woechentlich', t('woechentlich')], ['aus', t('nie')]].map(([v, l]) => `<option value="${v}" ${(up.pruefen || 'taeglich') === v ? 'selected' : ''}>${l}</option>`).join('')}</select> <span class="small muted">${t('nur_github_installieren_erst_nach_klick')}</span></label>
    <label>${t('quelle_github_0', hq('update_quelle'))}</label><input type="text" id="e-up-repo" value="https://github.com/${esc(up.repo || 'stecrz/Kontor')}">
  </div>
  <div class="actions"><button id="save-settings">${t('einstellungen_speichern')}</button></div><div id="findings-e" class="findings"></div>`;
}
function vEinstellungenDaten() {
  return `<h2>${t('daten')}</h2><div class="kv"><div>${t('datenordner')}</div><div>${esc(S.STATUS.ablage.ordner)}</div><div>${t('verschluesselung')}</div><div>${S.STATUS.ablage.verschluesselt ? t('aes_256_schluessel_im') + (S.STATUS.ablage.schluessel === 'schluesselbund' ? t('macos_schluesselbund') : t('dateisystem_0600')) : 'KEINE'}</div><div>${t('belegordner')}</div><div>${esc(S.STATUS.belege.ordner)}</div>
    <div>Time Machine ${hq('timemachine')}</div><div><span id="tm-state" class="muted">…</span> <button id="tm-toggle" class="secondary small hidden"></button></div>
    <div>${t('protokoll')}</div><div><a href="#protokoll">${t('protokoll_und_diagnose')}</a></div></div>`;
}
const posRow = (k, v) => `<div class="row tight pos-row"><input type="text" class="p-kat" value="${esc(k)}" placeholder="${t('kategorie_oder_oberkategorie')}"><input type="text" class="p-pos" value="${esc(v)}" placeholder="${t('z_b_sonderausgaben_vorsorge')}"><button class="danger small del-row">×</button></div>`;
function collectSettings() {
  // nur die Felder des sichtbaren Reiters; alles andere bleibt, wie es ist
  const cfg = JSON.parse(JSON.stringify(S.CFG));
  if ($('#e-probelauf')) {
    cfg.probelauf = $('#e-probelauf').checked; cfg.mitteilungen = $('#e-mitt').checked;
    cfg.zeitplan = { automatisch: $('#e-auto').checked, intervall_minuten: Math.max(5, parseInt($('#e-intervall').value) || 30), voll_lesen_stunden: Math.max(1, parseInt($('#e-voll').value) || 24) };
    cfg.bilanz = Object.assign(cfg.bilanz || {}, { monate_zurueck: parseInt($('#e-monate').value) || 0 });
    cfg.moneymoney = Object.assign(cfg.moneymoney || {}, { kategorisieren_erlauben: $('#e-mm-cat').checked });
    cfg.belege = Object.assign(cfg.belege || {}, { ordner: $('#e-bl-ordner').value.trim() || '~/Documents/Kontor-Belege', unterordner: $('#e-bl-sub').value.trim() || '{jahr}', kommentar_schreiben: $('#e-bl-comment').checked,
      ordner_bestaetigt: !!(cfg.belege || {}).ordner_bestaetigt || $('#e-bl-ordner').value.trim() !== ((S.CFG.belege || {}).ordner || '') });    // ein hier gewählter Ordner gilt als bestätigt
    cfg.oberflaeche = Object.assign(cfg.oberflaeche || {}, { sprache: $('#e-lang').value });
  }
  if ($('#e-verm')) cfg.steuer = Object.assign(cfg.steuer || {}, { vermietung_kategorie: $('#e-verm').value.trim() || 'Vermietung',
      objekt_darlehen: Object.fromEntries($$('.e-obj').map(i => [i.dataset.ref, i.value.trim()]).filter(([, v]) => v)),
      positionen: Object.fromEntries($$('.pos-row').map(r => [$('.p-kat', r).value.trim(), $('.p-pos', r).value.trim()]).filter(([k, v]) => k && v)) });
  if ($('#e-up-pruefen')) {
    // Quelle als GitHub-Adresse (https://github.com/inhaber/projekt); gespeichert wird inhaber/projekt
    const m = $('#e-up-repo').value.trim().match(/^(?:https?:\/\/(?:www\.)?github\.com\/)?([\w.-]+)\/([\w.-]+?)(?:\.git)?\/?$/i);
    if (!m) throw new Error(t('err_nur_github_adresse'));
    cfg.updates = { pruefen: $('#e-up-pruefen').value, repo: m[1] + '/' + m[2] };
  }
  if ($('#e-sperre')) cfg.oberflaeche = Object.assign(cfg.oberflaeche || {}, { sperre_minuten: Math.max(1, parseInt($('#e-sperre').value) || 15), touchid: $('#e-touchid').checked,
    bind: $('#e-bind').value.trim() || '127.0.0.1', port: parseInt($('#e-port').value) || 8765, tls_cert: $('#e-cert').value.trim(), tls_key: $('#e-key').value.trim() });
  return cfg;
}

// ---------------------------------------------------------------- Sicherung & Pakete
let PKG = null, PKG_UNRES = null;
function vSicherung() {
  // Sicherung (alles) · Einstellungspaket (zum Weitergeben) · Laden für beides über dieselbe Fläche · Zurücksetzen
  const C = S.CFG;
  return `<div class="cards two"><div class="card"><div class="l">${t('sicherung_h')}</div><div class="d">${t('sicherung_wofuer')}</div></div><div class="card"><div class="l">${t('einstellungspaket')}</div><div class="d">${t('paket_wofuer')}</div></div></div>
  <h2>${t('sicherung_h')}</h2><div class="note">${t('sicherung_text')}</div>
  ${S.STATUS.lokal ? `<div class="row tight"><input type="password" id="bk-pw" placeholder="${t('passwort_fuer_die_sicherung')}" autocomplete="new-password" style="width:230px"><input type="password" id="bk-pw2" placeholder="${t('ph_passwort_wiederholen')}" autocomplete="new-password" style="width:230px"><button id="bk-save" class="secondary">${t('sicherung_verschluesselt_herunterladen')}</button></div><div class="small muted">${t('sicherung_passwort_hinweis')}</div>` : `<div class="small muted">${t('nur_am_mac')}</div>`}
  <h2>${t('einstellungspaket')} ${hq('paket')}</h2><div class="note">${t('paket_text', `<code>${t('name_kontor_json')}</code>`)}</div>
  <div class="row tight"><label class="chk">${t('name')} <input type="text" id="pk-name" value="Kontor-Einstellungen"></label><button id="pk-export" class="secondary">${t('paket_herunterladen')}</button></div>
  <div class="small muted">${t('aktuell_0_darlehen_1_beteiligungen', (C.darlehen || []).length, (C.beteiligungen || []).length, (C.saldo_spiegel || []).length, Object.keys((C.kapitalfluss || {}).kategorie_zuordnung || {}).length)}</div>
  <h2>${t('datei_laden')}</h2><div class="drop" id="pk-drop">${t('sicherung_hierher_ziehen')}<br><button id="pk-pick" class="small" style="margin-top:8px">${t('datei_waehlen')}</button></div><div id="pk-preview"></div>
  ${vEinstellungenDaten()}
  <h2>${t('zuruecksetzen_h')}</h2><div class="note">${t('zuruecksetzen_text')}</div>
  <div class="row tight"><input type="password" id="rs-pw" placeholder="${t('passwort_zur_bestaetigung')}" autocomplete="current-password" style="width:220px"><label class="chk"><input type="checkbox" id="rs-pw-reset"> ${t('passwort_ebenfalls_zuruecksetzen_einri')}</label><button id="rs-go" class="danger" ${S.STATUS.lokal ? '' : t('disabled_title_nur_am_mac')}>${t('programm_zuruecksetzen')}</button></div><div id="rs-report" class="findings"></div>`;
}
function pkgPreview() {
  const el = $('#pk-preview'); if (!PKG) { el.innerHTML = ''; return; }
  const c = PKG.config || {};
  let h = `<div class="card" style="margin-top:12px"><h3>${esc(PKG.name || t('paket'))} <span class="muted">${t('version_0_1', esc(PKG.version || '?'), esc(PKG.erstellt || ''))}</span></h3>
    <div class="small">${t('0_darlehen_1_beteiligungen_2', (c.darlehen || []).length, (c.beteiligungen || []).length, (c.saldo_spiegel || []).length, Object.keys((c.kapitalfluss || {}).kategorie_zuordnung || {}).length, Object.keys((c.steuer || {}).positionen || {}).length, PKG.plan ? t('planung_enthalten') : '')}</div>
    <div class="row tight" style="margin-top:8px"><div class="seg" id="pk-mode"><button data-m="ergaenzen" class="on">${t('ergaenzen_regeln_hinzufuegen_zuordnung')}</button><button data-m="ersetzen">${t('ersetzen_vorhandene_regeln_verwerfen')}</button></div>${PKG.plan ? `<label class="chk"><input type="checkbox" id="pk-withplan"> ${t('planung_uebernehmen')}</label>` : ''}<button id="pk-import" class="small">${t('uebernehmen')}</button></div>`;
  if (PKG_UNRES && PKG_UNRES.length) {
    h += `<h3 style="margin-top:12px">${t('nicht_gefundene_konten_zuordnen')}</h3><div class="list">` + PKG_UNRES.map((u, i) => `<div class="row tight"><span style="min-width:280px"><b>${esc(u.label)}</b> <span class="small muted">(${esc(u.feld)})</span></span><select class="pk-map" data-ref="${esc(u.ref)}">${acctOptions('')}</select></div>`).join('') + `</div><div class="row tight"><button id="pk-import2" class="small">${t('mit_zuordnung_uebernehmen')}</button><button id="pk-force" class="small secondary">${t('ohne_zuordnung_uebernehmen_namen_bleib')}</button></div>`;
  }
  el.innerHTML = h + '<div id="pk-report" class="findings"></div></div>';
  let mode = 'ergaenzen';
  $$('#pk-mode button').forEach(b => b.onclick = () => { $$('#pk-mode button').forEach(x => x.classList.remove('on')); b.classList.add('on'); mode = b.dataset.m; });
  const doImport = async (mapping, force) => {
    try {
      const r = await api('/api/package/import', {paket: PKG, modus: mode, zuordnung: mapping || {}, trotzdem: !!force, mit_plan: !!($('#pk-withplan') && $('#pk-withplan').checked)});
      if (!r.ok) { PKG_UNRES = r.unaufgeloest; pkgPreview(); showFindings($('#pk-report'), [], r.hinweis + t('n_offen', r.unaufgeloest.length), 'warnung'); return; }
      S.CFG = r.config; PKG_UNRES = null; showFindings($('#pk-report'), r.befunde, t('uebernommen_2') + r.bericht.join(' · '), 'ok'); toast(t('paket_uebernommen'));
    } catch (e) { showFindings($('#pk-report'), [], e.message, 'fehler'); }
  };
  $('#pk-import').onclick = () => doImport({}, false);
  const i2 = $('#pk-import2'); if (i2) i2.onclick = () => doImport(Object.fromEntries($$('.pk-map').map(s => [s.dataset.ref, s.value]).filter(([, v]) => v)), false);
  const i3 = $('#pk-force'); if (i3) i3.onclick = () => doImport(Object.fromEntries($$('.pk-map').map(s => [s.dataset.ref, s.value]).filter(([, v]) => v)), true);
}
async function readPkgFile(file) {
  try {
    const obj = JSON.parse(await file.text());
    if (obj.kontor_sicherung_verschluesselt) {
      const pw = await askPassword(t('sicherung_laden_frage', esc(obj.erstellt || '?'), esc(obj.version || '?')));
      if (!pw) return;
      const r = await api('/api/backup/restore', {sicherung: obj, passwort: pw});
      S.CFG = r.config; toast(t('sicherung_geladen') + r.teile.join(', '), 6000); await loadAll(); route(); return;
    }
    if (obj.kontor_sicherung) {
      const teile = [t('einstellungen'), obj.plan ? t('planung') : '', obj.kategorien ? t('kategorien') : '', obj.historie ? t('verlauf_2') : '', obj.belege ? t('belegindex') : ''].filter(Boolean).join(', ');
      if (!confirm(t('sicherung_vom') + (obj.erstellt || '?') + ' (' + t('version') + ' ' + (obj.version || '?') + t('wiederherstellen_ersetzt') + teile + '.')) return;
      const r = await api('/api/backup/restore', {sicherung: obj});
      S.CFG = r.config; toast(t('sicherung_geladen') + r.teile.join(', '), 6000); await loadAll(); route(); return;
    }
    PKG = obj; if (!PKG.config) { if (PKG.darlehen || PKG.bilanz) PKG = {kontor_paket: 1, name: file.name, config: PKG}; else throw new Error(t('err_kein_paket')); } PKG_UNRES = null; pkgPreview(); }
  catch (e) { toast(t('datei_unlesbar') + e.message, 5000); }
}

// ---------------------------------------------------------------- Updates
function clHtml(md) {
  // CHANGELOG (Markdown-Ausschnitt): Versionen als Ueberschrift, Punkte als Liste, `Code`
  const inl = s => esc(s).replace(/`([^`]+)`/g, '<code>$1</code>');
  let h = '', open = false;
  for (const line of md.split('\n')) {
    const v = line.match(/^##\s+(\S+)(?:\s+\((\d{4}-\d{2}-\d{2})\))?/), li = line.match(/^\s*[-*]\s+(.*)/);
    if (v) { if (open) h += '</ul>'; open = false; h += `<h3>${esc(v[1])}${v[2] ? `<span class="vdate">${t('vom_0', FD(v[2]))}</span>` : ''}</h3>`; }
    else if (li) { if (!open) h += '<ul>'; open = true; h += `<li>${inl(li[1])}</li>`; }
    else if (line.trim() && !line.startsWith('# ')) { if (open) h += '</ul>'; open = false; h += `<p>${inl(line)}</p>`; }
  }
  return `<div class="cl">${h}${open ? '</ul>' : ''}</div>`;
}
async function vUpdates() {
  const r = await api('/api/update/status'), st = S.STATUS, info = r.info;
  let h = `<div class="cards"><div class="card"><div class="l">${t('installiert')}</div><div class="v">${esc(r.version)}${r.datum ? `<span class="vdate">${t('vom_0', FD(r.datum))}</span>` : ''}</div><div class="d">${t('programmordner_wird_beim_update_ersetz')}</div></div>
    <div class="card"><div class="l">${t('verfuegbar_3')}</div><div class="v">${info ? (info.fehler ? '<span class="pill err">?</span>' : esc(info.verfuegbar || '–') + (info.datum ? `<span class="vdate">${t('vom_0', FD(info.datum))}</span>` : '')) : '–'}</div><div class="d">${info ? (info.fehler ? esc(info.fehler) : (info.neuer ? `<span class="pill ok">${t('neuer_als_installiert')}</span>` : t('kontor_ist_aktuell')) + t('quelle_2') + esc(info.quelle || '')) : t('noch_nicht_geprueft')}${r.geprueft ? t('geprueft') + new Date(r.geprueft * 1000).toLocaleString(LOCALE) : ''}</div></div></div>
    <div class="note">${t('automatisch_pruefen_status', {taeglich: t('taeglich'), woechentlich: t('woechentlich'), aus: t('nie')}[(S.CFG.updates || {}).pruefen || 'taeglich'])} <a href="#einstellungen/updates">${t('aendern')}</a></div>
    <div class="actions"><button id="up-check" class="secondary">${t('jetzt_pruefen')}</button><button id="up-install" ${info && info.neuer && st.lokal ? '' : 'disabled'}>${t('update_installieren_und_dienst_neu')}</button></div>
    ${info && info.notizen && info.neuer ? `<h2>${t('neu_in_0', esc(info.verfuegbar))}</h2>${clHtml(info.notizen)}` : ''}
    ${r.changelog ? `<details class="changelog"><summary>${t('alle_aenderungen')}</summary>${clHtml(r.changelog)}</details>` : ''}
    <div class="note">${t('die_pruefung_fragt_nur_github', esc((S.CFG.updates || {}).repo || 'stecrz/Kontor'))} <code>.alt</code>${t('und_der_dienst_neu_gestartet')} <code>${t('git_pull')}</code>${t('die_seite_laedt_danach_neu')} <code>bash &lt;(curl -fsSL https://raw.githubusercontent.com/${esc((S.CFG.updates || {}).repo || 'stecrz/Kontor')}/main/get.sh)</code> ${t('im_terminal_installiert_und_aktualisie')}</div>`;
  return h;
}

// ---------------------------------------------------------------- Protokoll / Hilfe
async function vProtokoll() {
  const r = await api('/api/log?n=500');
  const ordner = (S.STATUS && S.STATUS.ablage && S.STATUS.ablage.ordner) || t('library_application_support_kontor');
  return `<div class="toolbar"><button id="log-refresh" class="secondary small">${t('aktualisieren')}</button><button id="diag2" class="secondary small">${t('diagnosedatei_maskiert')}</button><button id="diag3" class="secondary small">${t('diagnosedatei_mit_kontonamen')}</button>${hq('diagnose')}${S.STATUS && S.STATUS.lokal ? `<button id="log-show" class="secondary small">${t('im_finder_zeigen')}</button>` : ''}</div>
    <div class="note">${t('datei')} <code>${esc(ordner)}/kontor.log</code> ${t('klartext_rotiert_bei_5_mb')} <code>${t('dienst_err_log')}</code> ${t('fuer_abstuerze_des_dienstes_zur')} <code>${t('library_application_support_kontor')}</code>.</div><pre class="log">` + esc(r.zeilen.join('\n')) + '</pre>';
}
function vHilfe() {
  return `<div class="help">
  <h2>${t('was_macht_moneymoney_was_macht')}</h2>
  <table class="plain"><thead><tr><th>MoneyMoney</th><th>Kontor</th></tr></thead><tbody>
  <tr><td>${t('holt_umsaetze_und_salden_von')}</td><td>${t('liest_diese_daten_ueber_die')}</td></tr>
  <tr><td>${t('kategorisiert_umsaetze_von_hand_oder')}</td><td>${t('wertet_die_kategorien_aus_kapitalfluss')}</td></tr>
  <tr><td>${t('fuehrt_offline_konten_manuell_darlehen')}</td><td>${t('bucht_nach_deinen_regeln_in')} <b>${t('genau_diese_offline_konten')}</b>${t('darlehensraten_spiegeln_zinsen_berechn')}</td></tr>
  <tr><td>${t('ruft_konten_bei_den_banken')}</td><td>${t('verwendet_was_moneymoney_hat_und')}</td></tr>
  <tr><td>${t('hat_keine_bilanz_planungs_steuer')}</td><td>${t('bilanz_je_bereich_nach_positionen')}</td></tr>
  </tbody></table>
  <h2>${t('bereiche_positionen_verlauf')}</h2>
  <ul><li><b>${t('bereich')}</b> ${t('frei_zusammengestellte_konten_privat_j')}</li>
  <li><b>${t('position')}</b> ${t('zeile_in_der_bilanz_liquiditaet')}</li>
  <li><b>${t('verlauf_2')}</b> ${t('woher_die_monatsstaende_kommen_aus')}</li>
  <li><b>${t('konten_bestaetigen')}</b>${t('bereich_position_und_verlauf_jedes')}</li>
  <li><b>${t('ausgeblendete_konten')}</b>${t('anzeige_nach_aktivitaet_blendet_konten')}</li></ul>
  <h2>${t('immobilien')}</h2>
  <ul><li>${t('je_objekt_mehrere_kalkulationen_szenar')}</li>
  <li>${t('darlehen_annuitaet_feste_rate_tilgungs')}</li>
  <li>${t('indexmiete_erhoehung_zum_jahresbeginn_2')}</li>
  <li>${t('steuer_ergebnis_miete_kosten_abziehbar')}</li>
  <li>${t('verknuepfung_mit_moneymoney_vermietung')}</li></ul>
  <h2>${t('kategorien')}</h2>
  <ul><li>${t('kontor_fuehrt_eigene_kategorien_menue')}</li>
  <li>${t('regeln_lernt_kontor_aus_den')}</li>
  <li>${t('zuordnen_zeigt_alle_umsaetze_ohne')}</li>
  <li>${t('ohne_kategorien_funktionieren_bilanz_v')}</li>
  <li>${t('optional_schreibt_kontor_eine_zuordnun')}</li></ul>
  <h2>${t('planung_ereignisse')}</h2>
  <p>${t('umschichtung_betrag_wandert_von_von')}</p>
  <h2>${t('berechtigungen_die_macos_abfragt')}</h2>
  <ul><li><b>${t('automation_moneymoney')}</b> ${t('beim_ersten_verbindung_pruefen_oder')}</li>
  <li><b>${t('automation_system_events')}</b> ${t('datei_waehlen_oeffnet_den_macos')}</li>
  <li><b>${t('schluesselbund')}</b>${t('der_schluessel_fuer_die_verschluesselt')}</li></ul>
  <h2>${t('protokoll_und_fehlersuche')}</h2>
  <p>${t('das_protokoll_liegt_als_klartext')} <code>${t('library_application_support_kontor_kon')}</code> ${t('finder_gehe_zu_ordner_daneben')} <code>${t('dienst_err_log')}</code>${t('seite_protokoll_zeigt_die_letzten')}</p>
  <h2>${t('iphone_und_offline_ansicht')}</h2>
  <p>${t('tailscale_auf_mac_und_iphone')} <code>${t('python3_kontor_kontor_py_tls')}</code>${t('holt_ein_zertifikat_fuer_den')}</p>
  <h2>${t('sicherung_und_zuruecksetzen')}</h2>
  <p>${t('einstellungen_sicherung_herunterladen')}</p>
  <h2>${t('sicherheit')}</h2>
  <ul><li>${t('die_oberflaeche_ist_nur_auf')}</li>
  <li>${t('alle_daten_im_datenordner_sind')}</li>
  <li>${t('keine_verbindung_zu_externen_servern')}</li>
  <li>${t('passwort_touch_id_automatische_sperre')}</li>
  <li>${t('das_protokoll_enthaelt_keine_ibans')}</li></ul>
  <h2>${t('typische_meldungen')}</h2>
  <ul><li><b>${t('moneymoney_laeuft_nicht_datenbank_gesp')}</b> ${t('moneymoney_oeffnen_und_entsperren_kont')}</li>
  <li><b>${t('keine_berechtigung')}</b> ${t('systemeinstellungen_datenschutz_amp_si')}</li>
  <li><b>${t('konto_nicht_gefunden')}</b> ${t('ein_in_einer_regel_verwendetes')}</li>
  <li><b>${t('pruefzeile_0')}</b> ${t('eine_vermoegensaenderung_ist_nicht_erk')}</li>
  <li><b>${t('keine_passende_zahlung')}</b> ${t('die_darlehensregel_findet_die_rate')}</li>
  <li><b>${t('kontostaende_vor_fortgeschrieben')}</b> ${t('fuer_ein_konto_mit_verlaufsquelle')}</li>
  <li><b>${t('datei_liegt_in_icloud')}</b> ${t('die_verknuepfte_datei_ist_nur')}</li></ul>
  <h2>${t('kommandozeile')}</h2>
  <p><code>${t('python3_kontor_py_check')}</code> ${t('konfiguration_pruefen')} <code>${t('run_dry_run')}</code> · <code>${t('accounts')}</code> ${t('kontenbaum_mit_uuids')} <code>${t('package_export')}</code> / <code>${t('package_import_datei')}</code> · <code>${t('diagnostics')}</code> · <code>${t('update_install')}</code> · <code>${t('install')}</code> ${t('dienst_einrichten_jederzeit_wiederholb')}</p>
  </div>`;
}

// ---------------------------------------------------------------- Steuerung
const TITLES = {uebersicht: t('uebersicht'), bilanz: t('bilanz'), kapitalfluss: t('kapitalfluss'), planung: t('planung'), buchungen: t('buchungen'), steuer: t('steuer'), immobilien: t('immobilien'), umsaetze: t('umsaetze_belege'), einrichtung: t('einrichtung'), regeln: t('regeln'), kategorien: t('kategorien'), einstellungen: t('einstellungen'), synchronisierung: t('synchronisierung'), updates: t('updates'), protokoll: t('protokoll'), hilfe: t('hilfe')};
const SUBTITLES = {};
async function route() {
  if (DIRTY.on && location.hash !== DIRTY.hash) {
    if (!confirm(t('ungespeicherte_aenderungen_verwerfen'))) { history.replaceState(null, '', DIRTY.hash || '#uebersicht'); return; }
    DIRTY.on = false;
  }
  const raw = (location.hash || '#uebersicht').slice(1), [path, qs] = raw.split('?'), [tab, sub] = path.split('/');
  const y0 = window.scrollY;
  if (SCROLL.key) SCROLL.pos[SCROLL.key] = y0;                 // Position des bisherigen Reiters merken
  S.tab = TITLES[tab] ? tab : 'uebersicht'; S.sub = sub || '';
  const key = S.tab + '/' + S.sub, sameTab = key === SCROLL.key;
  if (qs && S.tab === 'umsaetze') { const p = new URLSearchParams(qs); S.uf.ohne_kategorie = p.get('ohne_kategorie') === '1'; S.uf.ohne_beleg = p.get('ohne_beleg') === '1'; if (p.get('jahr')) S.uf.jahr = p.get('jahr'); if (p.get('entitaet')) S.uf.entitaet = p.get('entitaet'); history.replaceState(null, '', '#umsaetze'); }
  $$('#nav a').forEach(a => a.classList.toggle('on', a.getAttribute('href') === '#' + S.tab));
  $('#page-title').textContent = SUBTITLES[S.tab + '/' + S.sub] || (S.tab === 'immobilien' && S.sub ? t('immobilie') : TITLES[S.tab]);
  $('#bereich-seg').classList.toggle('hidden', !(S.DATA && Object.keys(S.DATA.bereiche || {}).length > 1 && ['uebersicht', 'bilanz', 'kapitalfluss', 'planung'].includes(S.tab)));
  $('.side').classList.remove('open');
  if (S.tab !== 'umsaetze') closeDrawer();
  const main = $('#main');
  const myRoute = ++ROUTE_SEQ;
  const slow = setTimeout(() => { if (ROUTE_SEQ === myRoute) main.innerHTML = `<div class="loading"><span class="spin"></span>${t('0_wird_geladen', esc(TITLES[S.tab] || ''))}<div class="note">${t('der_dienst_antwortet_noch_nicht')}</div></div>`; }, 400);
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
    else if (S.tab === 'umsaetze') h = await vUmsaetze();
    else if (S.tab === 'regeln') h = vRegeln();
    else if (S.tab === 'kategorien') h = await vKategorien();
    else if (S.tab === 'einstellungen') h = await vEinstellungen();
    else if (S.tab === 'synchronisierung') h = await vSync();
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
    if (S.tab === 'kategorien') { bindZuordnen(main); bindKontorKategorien(main); bindKatAuswahl(main); }
    if (S.tab === 'einstellungen' && S.sub === 'zugang') bindZugang(main);
  } catch (e) { clearTimeout(slow); if (ROUTE_SEQ === myRoute && e.message !== 'nicht angemeldet') main.innerHTML = `<div class="banner err">${esc(e.message)} <button class="small secondary" onclick="route()">${t('erneut_versuchen')}</button></div>`; }
}
let ROUTE_SEQ = 0;
const SCROLL = {key: '', pos: {}};
// Ungespeicherte Aenderungen: Formulare auf Seiten mit Speichern-Knopf melden Aenderungen; Wegnavigieren fragt nach
const DIRTY = {on: false, hash: location.hash};
const GUARDED = ['einrichtung/bereiche', 'einrichtung/konten', 'einstellungen', 'einstellungen/zugang', 'einstellungen/updates', 'einstellungen/steuer', 'regeln'];
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
      if (!(await waitRebuild(t('auswertung_wird_mit_den_gespeicherten')))) return;
      await loadAll();
      location.hash = b.dataset.savenext;
    } finally { b.disabled = false; }
  }));
}
async function waitRebuild(title) {
  // Ladeanzeige mit Fortschritt, bis die Auswertung im Hintergrund fertig ist. Laufende Streifen und Sekundenzähler zeigen,
  // dass gearbeitet wird; zwischen zwei Meldungen rückt der Balken langsam weiter (nie über die nächste Etappe hinaus)
  const ov = document.createElement('div'); ov.className = 'busy-ov';
  ov.innerHTML = `<div class="box"><div class="t">${esc(title)} …</div><div class="bar"><i style="width:3%"></i></div><div class="s small muted"><span class="st">${t('startet')}</span><span class="el"></span></div></div>`;
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
        if (b.fehler) { toast(t('auswertung_konnte_nicht_aktualisiert_w') + b.fehler, 8000); return false; }
        clearInterval(tick); $('.bar i', ov).style.width = '100%'; await new Promise(r => setTimeout(r, 200));
        BER.stand = b.stand || ''; return true;
      }
      const f = b.fortschritt || {};
      if ((f.anteil || 0) > P.ziel) { P.ziel = f.anteil; P.zeige = Math.max(P.zeige, P.ziel); }
      $('.st', ov).textContent = (f.schritt || t('laeuft')) + ' · ' + Math.round(P.ziel * 100) + ' %';
    }
    toast(t('die_auswertung_dauert_ungewoehnlich_la'), 8000); return true;
  } finally { clearInterval(tick); ov.remove(); }
}
// Speichern je Einrichtungsschritt (true = gespeichert)
const SAVE = {
  bereiche: async () => {
    const f = $('#findings-b'), cfg = collectBereiche();
    if (!cfg.bereiche.length) { showFindings(f, [], t('mindestens_ein_bereich_ist_noetig'), 'fehler'); return false; }
    if (cfg.bereiche.some(b => !b.name)) { showFindings(f, [], t('jeder_bereich_braucht_einen_namen'), 'fehler'); return false; }
    if (cfg.bereiche.some(b => !b.konten.length)) { showFindings(f, [], t('jeder_bereich_braucht_mindestens_ein'), 'fehler'); return false; }
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
  if (['bilanz', 'kapitalfluss', 'planung'].includes(S.tab)) $$('.wrap', main).forEach(w => {
    snapTable(w);
    const c = $('th[data-cur]', w);
    if (c && w.scrollWidth > w.clientWidth) w.scrollLeft = snapLeft(w, colX(w, c) + c.offsetWidth - w.clientWidth * (planOn() ? 0.62 : 1));
  });
  if (S.tab === 'bilanz') bindBilanzChart(main);
  const vs = $('#vorschlag-an', main); if (vs) vs.addEventListener('change', e => { S.vorschlag = e.target.checked; route(); });
  $$('[data-goto]', main).forEach(c => c.addEventListener('click', e => { if (!e.target.closest('a, button, input, select')) location.hash = c.dataset.goto; }));
  $$('[data-xlsx]', main).forEach(b => b.addEventListener('click', () => download(b.dataset.xlsx === 'property' ? `/api/export/property.xlsx?id=${encodeURIComponent(b.dataset.immo || '')}&calculation=${encodeURIComponent(b.dataset.kalk || '')}` : `/api/export/${b.dataset.xlsx}.xlsx?area=${encodeURIComponent(b.dataset.bereich || S.bereich || '')}&mode=${S.modus === 'jahre' ? 'years' : 'months'}`)));

  // Einrichtung
  const wc = $('#w-check', main); if (wc) wc.addEventListener('click', async () => {
    wc.classList.add('busy'); wc.disabled = true; const busy = $('#w-busy'); if (busy) busy.classList.remove('hidden'); $('#w-findings').innerHTML = '';
    const stop = readProgress();
    let r; try { r = await api('/api/check', {}); } catch (e) { stop(); wc.classList.remove('busy'); wc.disabled = false; if (busy) busy.classList.add('hidden'); showFindings($('#w-findings'), [], e.message, 'fehler'); return; }
    stop();
    if (!r.verfuegbar) { wc.classList.remove('busy'); wc.disabled = false; if (busy) busy.classList.add('hidden'); showFindings($('#w-findings'), [], r.text, 'fehler'); return; }
    S.KONTEN = r.konten; S.KATS = r.kategorien || S.KATS; await route(); showFindings($('#w-findings'), r.befunde, t('verbindung_steht') + r.konten.length + t('konten_gelesen'), 'ok'); });
  const wr = $('#w-report', main); if (wr) wr.addEventListener('click', () => rebuildReport(true));
  const wl = $('#w-lang', main); if (wl) wl.addEventListener('change', async () => { if (wl.value === LANG) return; try { await api('/api/language', {sprache: wl.value}); setLang(wl.value); } catch (e) { wl.value = LANG; toast(e.message, 5000); } });
  const abr = $('#add-bereich', main); if (abr) { bindBereichKonten(main); abr.addEventListener('click', () => { $('#bereiche').insertAdjacentHTML('beforeend', bereichForm({name: t('neuer_bereich'), id: '', konten: [], haupt: false}, $$('#bereiche .item').length)); bindDel(main); bindBereichKonten($('#bereiche .item:last-child')); bereichMvState(); }); }
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
  $$('.k-hist', main).forEach(b => b.addEventListener('click', async e => { const btn = e.target; btn.classList.add('busy'); try { const tr = btn.closest('tr'), sel = $('.k-verlauf', tr); await openHistDrawer(tr.dataset.uuid, sel ? sel.value : null); } catch (er) { toast(t('verlauf_konnte_nicht_geladen_werden') + er.message, 6000); } finally { btn.classList.remove('busy'); } }));
  const hp = $('#hi-pick', main); if (hp) hp.addEventListener('click', () => { const inp = $('#file-input'); inp.value = ''; inp.setAttribute('accept', '.csv,.txt,.xlsx,.xlsm'); inp.removeAttribute('capture'); inp.onchange = () => { if (inp.files[0]) histImportPreview(inp.files[0]); }; inp.click(); });
  const hd = $('#hi-drop', main); if (hd) { hd.addEventListener('dragover', e => { e.preventDefault(); hd.classList.add('over'); }); hd.addEventListener('dragleave', () => hd.classList.remove('over')); hd.addEventListener('drop', e => { e.preventDefault(); hd.classList.remove('over'); if (e.dataTransfer.files[0]) histImportPreview(e.dataTransfer.files[0]); }); if (HI) renderHistImport(); }
  const mz = $('#mmh-zeigen', main); if (mz) mz.addEventListener('click', async () => { try { await api('/api/history/mm-reveal', {}); } catch (e) { toast(e.message, 6000); } });
  const md = $('#mmh-drop', main); if (md) {
    const send = async file => {
      // Datei (verschlüsselt) direkt als Bytes an den Dienst auf diesem Mac; nichts davon wird gespeichert
      const res = $('#mmh-res', main); if (!file) return;
      if (MMH.busy) return; MMH.busy = true; md.classList.add('busy'); res.innerHTML = `<div class="working"><span class="spin"></span>${t('datei_wird_uebergeben')}</div>`;
      try {
        const r = await fetch('/api/history/mm-import', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/octet-stream', 'X-CSRF-Token': S.csrf, 'X-Kontor-Net': 'direct'}, body: file});
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.fehler || (t('fehler') + r.status));
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
  const sf = $('#sync-full', main); if (sf) sf.addEventListener('click', async () => { sf.classList.add('busy'); try { await syncNow(true); } finally { sf.classList.remove('busy'); } });
  $$('.ab-chk', main).forEach(cb => cb.addEventListener('change', async () => {
    try { await api('/api/sync', {konto: cb.closest('tr').dataset.uuid, abgerufen: cb.checked}); S.STATUS = await api('/api/status'); statusMini(); route(); }
    catch (e) { toast(e.message, 5000); cb.checked = !cb.checked; }
  }));
  const ksi = $('#k-show-inactive', main); if (ksi) ksi.addEventListener('change', e => $$('tr.inactive', main).forEach(tr => tr.style.display = e.target.checked ? '' : 'none'));
  $$('.k-show', main).forEach(sel => sel.addEventListener('change', () => { const tr = sel.closest('tr'); tr.classList.toggle('inactive', kontoHidden(sel.value, tr.dataset.auto === '1')); }));
  $$('.acct-table select[data-vor]', main).forEach(sel => sel.addEventListener('change', () => {
    sel.classList.toggle('vorschlag', sel.value === sel.dataset.vor);
  }));
  const kin = $('#k-inaktiv', main); if (kin) kin.addEventListener('input', () => $$('tr[data-grenze]', main).forEach(tr => {   // ausgegraut sofort neu
    tr.dataset.auto = autoHidden(tr.dataset.grenze, kin.value) ? '1' : '0';
    const on = kontoHidden($('.k-show', tr).value, tr.dataset.auto === '1'); tr.classList.toggle('inactive', on);
    if (!$('#k-show-inactive', main).checked) tr.style.display = on ? 'none' : '';
  }));

  // Bilanz
  $$('tr.acct[data-id]', main).forEach(tr => tr.addEventListener('click', () => openHistDrawer(tr.dataset.id)));
  $$('tr.transit', main).forEach(tr => tr.addEventListener('click', openTransitDrawer));

  // Planung
  $$('.edit .save', main).forEach(b => b.addEventListener('click', async e => { const box = e.target.closest('.edit'); await plan({zeile: box.dataset.key, methode: $('.meth', box).value, betrag: $('.betrag', box).value, steigerung: $('.steig', box).value}); }));
  $$('.reset-row', main).forEach(b => b.addEventListener('click', async e => { await plan({zeile: e.target.dataset.key, alle_ueberschreibungen_loeschen: true}); }));
  $$('td.plan.editable', main).forEach(td => td.addEventListener('dblclick', () => {
    if ($('input', td)) return;
    const key = td.closest('tr').dataset.key, m = td.dataset.month, old = td.firstChild.textContent.replace(/\./g, '').replace(',', '.');
    td.innerHTML = `<input type="text" value="${esc(old === '–' ? '' : old)}" style="width:90px;text-align:right;padding:1px 4px" title="${t('leer_vorschlag_verwenden')}">`;
    const inp = $('input', td); inp.focus(); inp.select();
    let done = false; const fin = async save => { if (done) return; done = true; if (save) await plan({zeile: key, monat: m, wert: inp.value}); else route(); };
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') fin(true); if (e.key === 'Escape') fin(false); }); inp.addEventListener('blur', () => fin(true));
  }));
  const ps = $('#p_save', main); if (ps) ps.addEventListener('click', () => plan({parameter: {horizont_monate: +$('#p_horizont').value, standard_methode: $('#p_methode').value, inflation_prozent_pa: +$('#p_infl').value, steigerung_einnahmen_prozent_pa: +$('#p_se').value, steigerung_ausgaben_prozent_pa: $('#p_sa').value === '' ? '' : +$('#p_sa').value, rendite_prozent_pa: +$('#p_rendite').value}}));
  const pr = $('#p_reset', main); if (pr) pr.addEventListener('click', () => { if (confirm(t('alle_planeinstellungen_und_ueberschrei') + BN() + t('loeschen_2'))) plan({zuruecksetzen: true}); });
  $$('.save-loan', main).forEach(b => b.addEventListener('click', e => { const tr = e.target.closest('tr'); plan({darlehen: {[tr.dataset.loan]: {zins_prozent_pa: $('.lz', tr).value, modell: $('.lm', tr).value, zahlung: $('.lp', tr).value}}}); }));
  $$('.save-wert', main).forEach(b => b.addEventListener('click', e => { const tr = e.target.closest('tr'); const p = $('.wp', tr).value, bs = $('.wb', tr).value, br = $('.wbr', tr).value, an = $('.wa', tr).value; plan({wertentwicklung: {[tr.dataset.acct]: (p === '' && bs === '' && !br) ? null : {prozent_pa: p, basis: bs, bereich: br, anteil: an}}}); }));
  $$('.ev-save', main).forEach(b => b.addEventListener('click', e => { const tr = e.target.closest('.ev-row'); const ev = {id: tr.dataset.id || undefined, text: $('.ev-text', tr).value, art: $('.ev-art', tr).value, betrag: $('.ev-betrag', tr).value, monat: $('.ev-monat', tr).value, wiederholung: $('.ev-wdh', tr).value, bis: $('.ev-bis', tr).value, von: $('.ev-von', tr).value, nach: $('.ev-nach', tr).value, aktiv: $('.ev-aktiv', tr).checked}; if (!ev.text.trim()) return toast(t('bezeichnung_fehlt')); if (!ev.betrag) return toast(t('betrag_fehlt')); plan({ereignis: ev}); }));
  $$('.ev-del', main).forEach(b => b.addEventListener('click', e => { const tr = e.target.closest('.ev-row'); if (confirm(t('ereignis_loeschen'))) plan({ereignis: {id: tr.dataset.id, loeschen: true}}); }));

  // Buchungen
  const rd = $('#run-dry', main); if (rd) rd.addEventListener('click', () => startRun(true));
  const rl = $('#run-live', main); if (rl) rl.addEventListener('click', () => { if (confirm(t('jetzt_buchen_buchungen_werden_jetzt'))) startRun(false); });
  const rr = $('#run-report', main); if (rr) rr.addEventListener('click', async () => { toast(t('bericht_wird_erstellt'), 20000); const r = await api('/api/report', {}); if (!r.ok) toast(r.text || t('moneymoney_nicht_verfuegbar'), 5000); await loadAll(); route(); });

  // Steuer
  const sj = $('#st-jahr', main); if (sj) sj.addEventListener('change', e => { S.steuerJahr = e.target.value; route(); });
  const se = $('#st-ent', main); if (se) se.addEventListener('change', e => { S.steuerEnt = e.target.value; route(); });
  const sb = $('#st-belege', main); if (sb) sb.addEventListener('click', async () => { try { const r = await belegeApi('/api/receipts/export', {jahr: S.steuerJahr, entitaet: S.steuerEnt}); toast(t('export_erstellt') + r.datei, 8000); } catch (e) { toast(e.message, 6000); } });
  const afa = $('#afa-save', main); if (afa) afa.addEventListener('click', async () => {
    const cfg = JSON.parse(JSON.stringify(S.CFG)); cfg.steuer = cfg.steuer || {}; cfg.steuer.afa = cfg.steuer.afa || {};
    $$('.afa', main).forEach(i => { const o = i.dataset.obj; cfg.steuer.afa[o] = typeof cfg.steuer.afa[o] === 'object' && cfg.steuer.afa[o] ? cfg.steuer.afa[o] : {}; if (i.value === '') delete cfg.steuer.afa[o][S.steuerJahr]; else cfg.steuer.afa[o][S.steuerJahr] = parseFloat(i.value); });
    await saveConfig(cfg, document.createElement('div')); toast(t('afa_gespeichert_wirkt_nach_dem'));
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
  const bk = $('#bulk-cat-btn', main); if (bk) bk.addEventListener('click', async () => { const kat = $('#bulk-cat').value.trim(); if (!kat) return toast(t('kategorie_waehlen')); if (!confirm(S.sel.size + t('umsaetzen_die_kategorie') + kat + t('zuweisen'))) return; try { const r = await assignCats([...S.sel], kat, {warten: true}); toast(assignMsg(r), 6000); S.sel.clear(); await loadAll(); route(); } catch (e) { toast(e.message, 6000); } });
  const bf = $('#bl-folder', main); if (bf) bf.addEventListener('click', async () => { try { await belegeApi('/api/receipts/open', {}); } catch (e) { toast(e.message, 5000); } });
  const be = $('#bl-export', main); if (be) be.addEventListener('click', async () => { const jahr = prompt(t('jahr_leer_alle'), uf.jahr || new Date().getFullYear()); if (jahr === null) return; try { const r = await belegeApi('/api/receipts/export', {jahr, entitaet: uf.entitaet}); toast(t('export_erstellt') + r.datei, 9000); } catch (e) { toast(e.message, 6000); } });

  // Regeln
  const al = $('#add-loan', main); if (al) al.addEventListener('click', () => { $('#loans').insertAdjacentHTML('beforeend', loanForm({name: t('neues_darlehen'), ab_datum: new Date().toISOString().slice(0, 10), zins: {modell: 'jahresbasis', satz: [], buchungstag: 'mit_rate'}, buchung: {kategorie_tilgung: 'Umbuchung'}}, $$('#loans .item').length)); bindDel(main); });
  const ab = $('#add-bet', main); if (ab) ab.addEventListener('click', () => { $('#bets').insertAdjacentHTML('beforeend', mirrorForm({name: t('neue_beteiligung'), anteil: 0.5}, $$('#bets .item').length, 'bet')); bindDel(main); });
  const am = $('#add-mirror', main); if (am) am.addEventListener('click', () => { $('#mirrors').insertAdjacentHTML('beforeend', mirrorForm({name: t('neuer_spiegel'), faktor: -1}, $$('#mirrors .item').length, 'mirror')); bindDel(main); });
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
  const ss = $('#save-settings', main); if (ss) ss.addEventListener('click', () => { try { saveConfig(collectSettings(), $('#findings-e')); } catch (e) { toast(e.message, 6000); } });
  const cb = $('#check-btn', main); if (cb) cb.addEventListener('click', async () => { toast(t('pruefe')); const r = await api('/api/check', {}); if (!r.verfuegbar) { showFindings($('#findings-e'), [], r.text, 'fehler'); return; } S.KONTEN = r.konten; S.KATS = r.kategorien || S.KATS; showFindings($('#findings-e'), r.befunde, t('geprueft_gegen_den_aktuellen_stand') + r.konten.length + t('konten_klammer_zu'), 'ok'); });
  const ap = $('#add-pos', main); if (ap) ap.addEventListener('click', e => { e.target.insertAdjacentHTML('beforebegin', posRow('', '')); bindDel(main); });
  const pw = $('#pw-save', main); if (pw) pw.addEventListener('click', async () => { try { await api('/api/password', {alt: $('#pw-alt').value, neu: $('#pw-neu').value}); toast(t('passwort_geaendert')); $('#pw-alt').value = $('#pw-neu').value = ''; } catch (e) { toast(e.message, 4000); } });
  const tms = $('#tm-state', main);
  if (tms) {
    // Time Machine: aktuellen Stand zeigen, ein Knopf schaltet um
    const show = st => { tms.textContent = {gesichert: t('tm_gesichert'), ausgeschlossen: t('tm_ausgeschlossen')}[st] || t('unbekannt'); const b = $('#tm-toggle', main); b.classList.toggle('hidden', !(st in {gesichert: 1, ausgeschlossen: 1}) || !S.STATUS.lokal); b.textContent = st === 'ausgeschlossen' ? t('wieder_sichern') : t('ausschliessen'); b.dataset.st = st; };
    api('/api/timemachine').then(r => show(r.status)).catch(() => show('unbekannt'));
    $('#tm-toggle', main).addEventListener('click', async e => { const aus = e.target.dataset.st !== 'ausgeschlossen'; if (aus && !confirm(t('tm_ausschliessen_frage'))) return; const r = await api('/api/timemachine-exclusion', {ausschliessen: aus}); if (!r.ok) toast(t('fehler_3') + r.text, 5000); show(r.status); });
  }
  for (const [id, url] of [['#diag2', '/api/diagnostics'], ['#diag3', '/api/diagnostics?names=1']]) { const d = $(id, main); if (d) d.addEventListener('click', () => download(url)); }
  const bks = $('#bk-save', main); if (bks) bks.addEventListener('click', async () => {
    const pw = $('#bk-pw', main).value; if (pw.length < 8) return toast(t('sicherungspasswort_mind_8'), 5000); if (pw !== $('#bk-pw2', main).value) return toast(t('passwoerter_ungleich'), 5000);
    try { const r = await api('/api/backup', {passwort: pw}); saveJson(r, `Kontor-Sicherung-${new Date().toISOString().slice(0, 10)}.kontor-sicherung.json`); $('#bk-pw', main).value = $('#bk-pw2', main).value = ''; toast(t('sicherung_erstellt'), 5000); } catch (e) { toast(e.message, 6000); }
  });
  const swc = $('#sw-clear', main); if (swc) swc.addEventListener('click', async () => { try { const ks = await caches.keys(); await Promise.all(ks.filter(k => k === 'kontor-data').map(k => caches.delete(k))); toast(t('gespeicherte_daten_geloescht')); } catch (e) { toast(t('nicht_moeglich') + e.message, 4000); } });
  const rs = $('#rs-go', main); if (rs) rs.addEventListener('click', async () => {
    const pw = $('#rs-pw').value, withPw = $('#rs-pw-reset').checked;
    if (!pw) return showFindings($('#rs-report'), [], t('passwort_eingeben'), 'fehler');
    if (!confirm(t('wirklich_alle_kontor_daten_auf') + (withPw ? t('und_das_passwort_zuruecksetzen') : '') + t('belegdateien_und_protokoll_bleiben_vor'))) return;
    try { const r = await api('/api/reset', {passwort: pw, mit_passwort: withPw}); toast(t('zurueckgesetzt_neustart_der_oberflaech'), 4000); setTimeout(() => location.reload(), 1200); }
    catch (e) { showFindings($('#rs-report'), [], e.message, 'fehler'); } });

  // Pakete
  const pe = $('#pk-export', main); if (pe) pe.addEventListener('click', () => download(`/api/package/export?name=${encodeURIComponent($('#pk-name').value || 'Kontor-Einstellungen')}`));
  const pp = $('#pk-pick', main); if (pp) pp.addEventListener('click', () => { const inp = $('#file-input'); inp.value = ''; inp.setAttribute('accept', '.json'); inp.removeAttribute('capture'); inp.onchange = () => { if (inp.files[0]) readPkgFile(inp.files[0]); }; inp.click(); });
  const pd = $('#pk-drop', main); if (pd) { pd.addEventListener('dragover', e => { e.preventDefault(); pd.classList.add('over'); }); pd.addEventListener('dragleave', () => pd.classList.remove('over')); pd.addEventListener('drop', e => { e.preventDefault(); pd.classList.remove('over'); if (e.dataTransfer.files[0]) readPkgFile(e.dataTransfer.files[0]); }); if (PKG) pkgPreview(); }

  // Updates
  const uc = $('#up-check', main); if (uc) uc.addEventListener('click', async () => { toast(t('pruefe')); await api('/api/update/check', {}); S.STATUS = await api('/api/status'); route(); });
  const ui = $('#up-install', main); if (ui) ui.addEventListener('click', async () => { if (!confirm(t('update_installieren_und_dienst_neu_2'))) return; toast(t('update_wird_installiert'), 30000); try { const r = await api('/api/update/install', {}); toast(r.text, 8000); if (r.ok && r.neustart) setTimeout(() => location.reload(), 6000); } catch (e) { toast(e.message, 8000); } });
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
  toast(fresh ? t('moneymoney_wird_gelesen_auswertung_wir') : t('auswertung_wird_im_hintergrund_aktuali'), fresh ? 60000 : 4000);
  try {
    let r = fresh ? await api('/api/report', {}) : await api('/api/report/rebuild', {});
    if (!r.ok && fresh) r = await api('/api/report/rebuild', {});
    if (!r.ok) { toast(r.text || t('moneymoney_nicht_verfuegbar_bericht_sp'), 7000); await loadAll(); route(); return false; }
    if (r.ok === 'angefordert') { await pollStatus(); return true; }
  } catch (e) { toast(e.message, 7000); return false; }
  await loadAll(); route(); toast(t('auswertung_aktualisiert')); return true;
}
async function plan(body) {
  try { await api('/api/plan', Object.assign({bereich: S.bereich}, body)); S.DATA = await api('/api/dataset'); route(); toast(t('plan_gespeichert')); }
  catch (e) { toast(t('fehler_3') + e.message, 4000); }
}
async function syncNow(voll) {
  // Wie der automatische Abgleich, nur sofort: MoneyMoney lesen, Regeln anwenden (Testmodus laut Einstellung), Auswertung bauen.
  // voll: alle Umsaetze lesen statt nur der letzten drei Monate
  if (SYNC.busy) return;
  SYNC.busy = true; statusMini();
  try {
    try { await api('/api/run', voll ? {force: false, voll: true} : {force: false}); }
    catch (e) { if (!/läuft bereits/.test(e.message)) throw e; }
    let tries = 0;
    do { await new Promise(r => setTimeout(r, tries ? 1500 : 800)); S.STATUS = await api('/api/status'); statusMini(); } while (S.STATUS.dienst.laeuft && tries++ < 200);
    const r = S.STATUS.letztes_ergebnis || {};
    await loadAll(); route();
    const n = (r.vorschlaege || []).length;
    const msg = r.status === 'unveraendert' ? t('synchronisiert_keine_aenderung_in_mone')
      : r.status === 'ok' ? t('synchronisiert') + (r.geschrieben ? ' – ' + r.geschrieben + ' gebucht' : '') + (r.probelauf && n ? ' – ' + n + t('buchungsvorschlaege_testmodus') : '') + ((r.warnungen || []).length ? ' – ' + r.warnungen.length + t('hinweise_unter_buchungen') : '')
      : (r.text || r.fehler || t('synchronisiert'));
    toast(msg, r.status === 'nicht_verfuegbar' || r.status === 'fehler' ? 7000 : 4500);
  } catch (e) { toast(t('synchronisieren_fehlgeschlagen') + e.message, 6000); }
  finally { SYNC.busy = false; statusMini(); }
}
async function startRun(dry) {
  try { await api('/api/run', {probelauf: dry, force: true}); toast(dry ? t('abgleich_gestartet_test') : t('abgleich_mit_buchung_gestartet')); } catch (e) { toast(e.message, 4000); return; }
  let tries = 0;
  const poll = async () => { S.STATUS = await api('/api/status'); statusMini(); if (S.STATUS.dienst.laeuft && tries++ < 150) return setTimeout(poll, 2000); await loadAll(); route(); const r = S.STATUS.letztes_ergebnis; toast(r && r.text ? r.text : t('abgleich_beendet'), 6000); };
  setTimeout(poll, 1500);
}

window.addEventListener('hashchange', route);
document.addEventListener('click', e => { const b = e.target.closest('#modus-seg button'); if (b) { S.modus = b.dataset.m; route(); } });
document.addEventListener('change', e => { const id = e.target.id; if (id === 'planan') { S.plan = e.target.checked; route(); } else if (id === 'realan') { S.real = e.target.checked; route(); } else if (id === 'alle-zeilen') { S.alle = e.target.checked; route(); } });
$('#menu-btn').addEventListener('click', () => $('.side').classList.toggle('open'));
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });
// Klick neben das Seitenfenster schliesst es (bei ungespeicherten Eingaben erst nach Rueckfrage)
document.addEventListener('pointerdown', e => {
  const dr = $('#drawer'); if (!dr.classList.contains('open') || dr.contains(e.target) || e.target.closest('#toast, .dlg-back')) return;
  if (drawerDirty() && !confirm(t('ungespeicherte_aenderungen_verwerfen'))) return;
  closeDrawer();
});
try { const s = JSON.parse(localStorage.getItem('kontor.ui') || '{}'); Object.assign(S, {modus: s.modus === 'jahre' ? 'jahre' : 'monate', plan: s.plan !== false, real: !!s.real, bereich: s.bereich || null}); } catch (e) {}
let SNAP_T = null;
window.addEventListener('resize', () => { clearTimeout(SNAP_T); SNAP_T = setTimeout(() => { if (['bilanz', 'kapitalfluss', 'planung'].includes(S.tab)) $$('#main .wrap.snap').forEach(w => { const l = w.scrollLeft; snapTable(w); w.scrollLeft = snapLeft(w, l); }); }, 150); });
window.addEventListener('beforeunload', () => { try { localStorage.setItem('kontor.ui', JSON.stringify({modus: S.modus, plan: S.plan, real: S.real, bereich: S.bereich})); } catch (e) {} });
setInterval(async () => { if (S.csrf && !document.hidden && !OFFLINE.mode) { try { await pollStatus(); } catch (e) {} } }, 30000);
// Zurück im Fenster (z. B. nach MoneyMoney): sofort nachsehen statt bis zu 30 s einen alten Stand zu zeigen
document.addEventListener('visibilitychange', () => { if (!document.hidden && S.csrf && !OFFLINE.mode) pollStatus().catch(() => {}); });
applyStatic();
checkSession();
