// Kontor Service Worker: Offline-Ansicht fuer das iPhone (PWA). Braucht https oder 127.0.0.1.
// - App-Dateien werden beim Installieren zwischengespeichert.
// - Lesende API-Antworten (Bericht, Konfiguration, Konten, Umsaetze ...) werden nach jedem erfolgreichen Abruf gespeichert;
//   ist der Mac nicht erreichbar, kommt die gespeicherte Antwort mit dem Kennzeichen X-Kontor-Offline.
// - Sitzung, Protokoll, Exporte, Belegdateien werden nie gespeichert; Schreibzugriffe gehen nur zum Mac.
const VERSION = '__VERSION__';
const SHELL = 'kontor-shell-' + VERSION;
const DATA = 'kontor-data';
const SHELL_FILES = ['/', '/app.js', '/app.css', '/icon.svg', '/manifest.webmanifest'];
const NO_CACHE = ['/api/session', '/api/log', '/api/update/', '/api/belege/datei', '/api/export/', '/api/diagnose', '/api/paket/export', '/api/sicherung', '/api/touchid'];
const TIMEOUT_MS = 7000;

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('kontor-shell-') && k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

function withTimeout(req, ms) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  return fetch(req, {signal: ctl.signal}).finally(() => clearTimeout(t));
}
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

self.addEventListener('fetch', e => {
  const req = e.request;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (req.method !== 'GET') {
    e.respondWith(fetch(req).catch(() => offlineJson({fehler: 'Offline – der Mac ist nicht erreichbar; die gespeicherte Ansicht kann nur gelesen werden.', offline: true})));
    return;
  }
  if (url.pathname.startsWith('/api/')) {
    if (NO_CACHE.some(p => url.pathname.startsWith(p))) {
      e.respondWith(withTimeout(req, url.pathname === '/api/session' ? 5000 : 30000).catch(() =>
        url.pathname === '/api/session' ? offlineJson({angemeldet: false, offline: true, version: VERSION}, 200) : offlineJson({fehler: 'Offline – nicht verfügbar.', offline: true})));
      return;
    }
    e.respondWith((async () => {
      try {
        const resp = await withTimeout(req, TIMEOUT_MS);
        if (resp.ok) { const c = await caches.open(DATA); c.put(req, await stamp(resp)); }
        return resp;
      } catch (err) {
        const c = await caches.open(DATA);
        const hit = await c.match(req);
        if (hit) return markOffline(hit);
        return offlineJson({fehler: 'Offline – dafür liegen keine gespeicherten Daten vor.', offline: true});
      }
    })());
    return;
  }
  // App-Dateien: Netz zuerst, sonst Cache; Seitenaufrufe fallen auf / zurueck
  e.respondWith((async () => {
    try {
      const resp = await withTimeout(req, TIMEOUT_MS);
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
