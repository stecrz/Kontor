// Kontor Service Worker: Offline-Ansicht fuer das iPhone (PWA). Braucht https oder 127.0.0.1.
// - App-Dateien werden beim Installieren zwischengespeichert.
// - Lesende API-Antworten (Bericht, Konfiguration, Konten, Umsaetze ...) werden nach jedem erfolgreichen Abruf gespeichert;
//   ist der Mac nicht erreichbar, kommt die gespeicherte Antwort mit dem Kennzeichen X-Kontor-Offline.
// - Sitzung, Protokoll, Exporte, Belegdateien werden nie gespeichert; Schreibzugriffe gehen nur zum Mac.
// Steuerung durch die App ueber den Anfrage-Header X-Kontor-Net:
//   direct = nur Netz, ohne Zeitlimit (am Mac selbst, und als Gegenprobe bei "langsam oder weg?")
//   cache  = erst Speicher, dann Netz (Offline-Modus: Seiten sofort anzeigen)
//   (leer) = Netz mit Zeitlimit, bei Ausfall Speicher
const VERSION = '__VERSION__';
const SHELL = 'kontor-shell-' + VERSION;
const DATA = 'kontor-data';
const SHELL_FILES = ['/', '/i18n.js', '/app.js', '/app.css', '/icon.svg', '/icon-180.png', '/manifest.webmanifest'];
const NO_CACHE = ['/api/session', '/api/log', '/api/update/', '/api/receipts/file', '/api/export/', '/api/diagnostics', '/api/package/export', '/api/backup', '/api/touchid'];
let lastNetOk = 0;          // letzte erfolgreiche Netzantwort: kurz danach gilt ein grosszuegiges Zeitlimit (Server langsam ≠ weg)

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('kontor-shell-') && k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

function withTimeout(req, ms) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  return fetch(req, {signal: ctl.signal}).then(r => { lastNetOk = Date.now(); return r; }).finally(() => clearTimeout(t));
}
function netTimeout() { return Date.now() - lastNetOk < 90000 ? 60000 : 8000; }
function offlineJson(obj, status) {
  return new Response(JSON.stringify(obj), {status: status || 503, headers: {'Content-Type': 'application/json; charset=utf-8', 'X-Kontor-Offline': '1'}});
}
async function stamp(resp) {
  // Kopie mit Zeitstempel speichern (Header werden beim Lesen aus dem Cache mitgeliefert)
  const h = new Headers(resp.headers); h.set('X-Kontor-Cached-At', new Date().toISOString());
  const body = await resp.clone().arrayBuffer();
  return new Response(body, {status: resp.status, statusText: resp.statusText, headers: h});
}
function markOffline(resp) {
  const h = new Headers(resp.headers); h.set('X-Kontor-Offline', '1');
  return resp.arrayBuffer().then(b => new Response(b, {status: resp.status, headers: h}));
}
async function remember(req, resp) {
  if (resp && resp.ok) { try { const c = await caches.open(DATA); await c.put(req, await stamp(resp)); } catch (e) {} }
  return resp;
}
async function fromCache(req) {
  const c = await caches.open(DATA);
  const hit = await c.match(req, {ignoreVary: true});
  return hit ? markOffline(hit) : null;
}

self.addEventListener('fetch', e => {
  const req = e.request;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (req.method !== 'GET') {
    e.respondWith(fetch(req).then(r => { lastNetOk = Date.now(); return r; }).catch(() =>
      offlineJson({fehler: 'Offline – der Mac ist nicht erreichbar; die gespeicherte Ansicht kann nur gelesen werden.', offline: true})));
    return;
  }
  const mode = req.headers.get('X-Kontor-Net') || '';
  if (url.pathname.startsWith('/api/')) {
    if (NO_CACHE.some(p => url.pathname.startsWith(p))) {
      if (mode === 'direct') { e.respondWith(fetch(req).then(r => { lastNetOk = Date.now(); return r; })); return; }
      e.respondWith(withTimeout(req, url.pathname === '/api/session' ? 5000 : 30000).catch(() =>
        url.pathname === '/api/session' ? offlineJson({angemeldet: false, offline: true, version: VERSION}, 200) : offlineJson({fehler: 'Offline – nicht verfügbar.', offline: true})));
      return;
    }
    const key = req.url;          // Schluessel ist die Adresse (Steuer-Header gehoeren nicht dazu)
    if (mode === 'direct') { e.respondWith(fetch(req).then(r => { lastNetOk = Date.now(); return remember(key, r); })); return; }
    e.respondWith((async () => {
      if (mode === 'cache') {
        const hit = await fromCache(key);
        if (hit) return hit;
      }
      try {
        const resp = await withTimeout(req, mode === 'cache' ? 8000 : netTimeout());
        return await remember(key, resp);
      } catch (err) {
        return (await fromCache(key)) || offlineJson({fehler: 'Offline – dafür liegen keine gespeicherten Daten vor.', offline: true});
      }
    })());
    return;
  }
  // App-Dateien: Netz zuerst, sonst Cache; Seitenaufrufe fallen auf / zurueck
  e.respondWith((async () => {
    try {
      const resp = await withTimeout(req, 6000);
      if (resp.ok) { const c = await caches.open(SHELL); c.put(req, resp.clone()); }
      return resp;
    } catch (err) {
      const c = await caches.open(SHELL);
      return (await c.match(req)) || (req.mode === 'navigate' ? c.match('/') : null) || new Response('Offline', {status: 503});
    }
  })());
});
self.addEventListener('message', e => {
  if (e.data === 'clear-data') e.waitUntil(caches.delete(DATA));
});
