// ANTIBIO Offline Service Worker
//
// PURPOSE
//   Make the calculator shell (one HTML document) available offline. Nothing
//   else is cached: there is no second page, no bundle, no API client cache.
//
// SERVED FROM CACHE (offline copies, all precached at install):
//   ./antibiotic_calc.html    the app shell + embedded clinical DB
//   ./manifest.webmanifest    PWA manifest
//   ./icons/icon-192.png      PWA icons
//   ./icons/icon-512.png
//
// DELIBERATELY NEVER CACHED / NEVER INTERCEPTED:
//   /v1/*  and /v2/*  — the clinical engine endpoints proxied live by server.js
//   (personal-physician owner registration, attestation ledger, recommendations).
//   They are per-user, credentialed (`credentials: 'same-origin'`) and frequently
//   return 401/403/409. Caching them would leak one owner's responses into another
//   session and would let a stale 200 mask a revoked token.
//   Non-GET requests (every POST/PUT/DELETE the app makes) are not intercepted at
//   all, and any future third-party (cross-origin) asset is never touched — there
//   are none left: Tailwind, Font Awesome and Google Fonts are self-hosted under
//   ./vendor since audit fix S-3 (2026-10-05) and are precached like the shell.
//
// OFFLINE FALLBACK
//   Only a *navigation* request falls back to the cached shell. An API request
//   that fails stays failed: it is never answered with 680 KB of HTML, which the
//   app would try to parse as JSON.
//
// CACHE VERSIONING
//   CACHE_VERSION must be bumped whenever antibiotic_calc.html, the manifest, an
//   icon or any ./vendor asset changes. Bumping it creates a new cache,
//   `activate` deletes every other cache, and the next install precaches fresh
//   copies. Without the bump a rebuilt artifact would keep being served from the
//   stale cache forever.

const CACHE_VERSION = 'v4';
const CACHE_NAME = `antibio-shell-${CACHE_VERSION}`;
const SHELL_URL = './antibiotic_calc.html';
const PRECACHE_URLS = [
  SHELL_URL,
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  // self-hosted third-party assets (S-3): the shell is unusable offline without them
  './vendor/tailwind.js',
  './vendor/css/all.min.css',
  './vendor/css/fonts.css',
  './vendor/webfonts/fa-solid-900.woff2',
  './vendor/webfonts/fa-regular-400.woff2',
  './vendor/webfonts/fa-brands-400.woff2',
  './vendor/fonts/LDIoaomQNQcsA88c7O9yZ4KMCoOg4Ko20yygg_vb.woff2',
  './vendor/fonts/LDIoaomQNQcsA88c7O9yZ4KMCoOg4Ko40yygg_vbd-E.woff2',
  './vendor/fonts/LDIoaomQNQcsA88c7O9yZ4KMCoOg4Ko50yygg_vbd-E.woff2',
  './vendor/fonts/LDIoaomQNQcsA88c7O9yZ4KMCoOg4Ko70yygg_vbd-E.woff2',
];
const ENGINE_PREFIXES = ['/v1/', '/v2/'];

function isEngineRequest(url) {
  return ENGINE_PREFIXES.some((prefix) => url.pathname === prefix.slice(0, -1) || url.pathname.startsWith(prefix));
}

async function precache() {
  const cache = await caches.open(CACHE_NAME);
  // Precached one by one: a single missing optional asset must not fail the whole
  // install and leave the app with no offline shell at all.
  await Promise.all(
    PRECACHE_URLS.map((url) =>
      cache.add(new Request(url, { cache: 'reload' })).catch(() => {
        /* optional asset */
      })
    )
  );
  if (!(await cache.match(SHELL_URL))) {
    throw new Error('antibio: app shell failed to precache, offline mode unavailable');
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(precache().then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

async function networkFirstShell(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      cache.put(SHELL_URL, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await cache.match(SHELL_URL);
    if (cached) {
      return cached;
    }
    return new Response('ANTIBIO offline: the calculator shell is not cached yet.', {
      status: 503,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    });
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then((response) => {
      if (response && response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => null);
  if (cached) {
    return cached;
  }
  const response = await network;
  if (response) {
    return response;
  }
  return new Response('ANTIBIO offline: asset unavailable.', {
    status: 504,
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') {
    return; // live engine writes
  }
  let url;
  try {
    url = new URL(request.url);
  } catch (error) {
    return;
  }
  if (url.origin !== self.location.origin) {
    return; // third-party assets: network only
  }
  if (isEngineRequest(url)) {
    return; // live engine reads: never cached, never faked
  }
  if (request.mode === 'navigate') {
    event.respondWith(networkFirstShell(request));
    return;
  }
  event.respondWith(staleWhileRevalidate(request));
});
