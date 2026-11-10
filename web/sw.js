// Kontor Service Worker: Offline-Ansicht fuer das iPhone (PWA). Braucht https oder 127.0.0.1.
// - App-Dateien werden beim Installieren zwischengespeichert.
// - Lesende API-Antworten (Bericht, Konfiguration, Konten, Umsaetze ...) werden nach jedem erfolgreichen Abruf gespeichert --
//   nur verschluesselt: je Antwort ein neuer AES-Schluessel, dieser mit dem oeffentlichen Schluessel des Geraets verschluesselt
//   (RSA-OAEP). Den privaten Schluessel gibt es auf dem Geraet nur mit dem Kontor-Passwort verschluesselt; entschluesselt wird
//   in der Seite nach der Anmeldung. Ohne Schluesselpaar wird nichts gespeichert (nie Klartext).
//   Ist der Mac nicht erreichbar, kommt die gespeicherte Antwort mit den Kennzeichen X-Kontor-Offline und X-Kontor-Enc.
// - Sitzung, Protokoll, Exporte, Belegdateien werden nie gespeichert; Schreibzugriffe gehen nur zum Mac.
// Steuerung durch die App ueber den Anfrage-Header X-Kontor-Net:
//   direct = nur Netz, ohne Zeitlimit (am Mac selbst, und als Gegenprobe bei "langsam oder weg?")
//   cache  = erst Speicher, dann Netz (Offline-Modus: Seiten sofort anzeigen)
//   (leer) = Netz mit Zeitlimit, bei Ausfall Speicher
const VERSION = '__VERSION__';
const SHELL = 'kontor-shell-' + VERSION;
const DATA = 'kontor-data-enc';            // the copy before 3.12.12 ('kontor-data') was plain text: deleted on activation
const SHELL_FILES = ['/', '/i18n.js', '/app.js', '/app.css', '/icon.svg', '/icon-180.png', '/manifest.webmanifest'];
const NO_CACHE = ['/api/session', '/api/log', '/api/update/', '/api/receipts/file', '/api/export/', '/api/diagnostics', '/api/package/export', '/api/backup', '/api/touchid'];
let lastNetOk = 0;          // letzte erfolgreiche Netzantwort: kurz danach gilt ein grosszuegiges Zeitlimit (Server langsam ≠ weg)

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => (k.startsWith('kontor-shell-') && k !== SHELL) || k === 'kontor-data').map(k => caches.delete(k)))).then(() => self.clients.claim()));
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
function markOffline(resp) {
  const h = new Headers(resp.headers); h.set('X-Kontor-Offline', '1');
  return resp.arrayBuffer().then(b => new Response(b, {status: resp.status, headers: h}));
}
// the device's public key (from IndexedDB, written by the page at a password sign-in)
let PUB = null;
function idbGet(key) {
  return new Promise(res => {
    try {
      const o = indexedDB.open('kontor-off', 1);
      o.onupgradeneeded = () => o.result.createObjectStore('k');
      o.onerror = () => res(null);
      o.onsuccess = () => { try { const g = o.result.transaction('k').objectStore('k').get(key); g.onsuccess = () => res(g.result || null); g.onerror = () => res(null); } catch (e) { res(null); } };
    } catch (e) { res(null); }
  });
}
async function pubKey() {
  if (PUB) return PUB;
  const rec = await idbGet('pair'); if (!rec || !rec.spki) return null;
  PUB = await crypto.subtle.importKey('spki', rec.spki, {name: 'RSA-OAEP', hash: 'SHA-256'}, false, ['encrypt']);
  return PUB;
}
async function sealed(resp) {
  // the body encrypted: [length of the wrapped key (2 bytes)][wrapped AES key][IV (12)][AES-GCM cipher text]
  const pub = await pubKey(); if (!pub) return null;
  const body = await resp.clone().arrayBuffer();
  const aes = await crypto.subtle.generateKey({name: 'AES-GCM', length: 256}, true, ['encrypt']);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({name: 'AES-GCM', iv}, aes, body);
  const wk = new Uint8Array(await crypto.subtle.encrypt({name: 'RSA-OAEP'}, pub, await crypto.subtle.exportKey('raw', aes)));
  const out = new Uint8Array(2 + wk.length + 12 + ct.byteLength);
  out[0] = wk.length >> 8; out[1] = wk.length & 255; out.set(wk, 2); out.set(iv, 2 + wk.length); out.set(new Uint8Array(ct), 14 + wk.length);
  const h = new Headers({'Content-Type': 'application/octet-stream', 'X-Kontor-Enc': '1', 'X-Kontor-Cached-At': new Date().toISOString()});
  return new Response(out, {status: resp.status, statusText: resp.statusText, headers: h});
}
async function remember(req, resp) {
  if (resp && resp.ok) { try { const s = await sealed(resp); if (s) { const c = await caches.open(DATA); await c.put(req, s); } } catch (e) {} }
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
      return (await c.match(req, {ignoreSearch: true})) || (req.mode === 'navigate' ? c.match('/') : null) || new Response('Offline', {status: 503});      // the files carry their version in the address
    }
  })());
});
self.addEventListener('message', e => {
  if (e.data === 'clear-data') { PUB = null; e.waitUntil(caches.delete(DATA)); }
  if (e.data === 'key-changed') { PUB = null; e.waitUntil(caches.delete(DATA)); }      // a new key pair: the old copy cannot be opened any more
});
