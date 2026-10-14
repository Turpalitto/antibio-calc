'use strict';
/**
 * Behavioural harness for sw.js (the offline service worker of the calculator).
 *
 * Runs the real sw.js inside a `vm` context with a fake ServiceWorkerGlobalScope:
 * in-memory CacheStorage, a scripted `fetch`, scope-relative `Request`, real
 * `Response`/`URL`. Each scenario boots a FRESH worker (fresh listeners and
 * caches), dispatches `install` / `activate` / `fetch` events and records what
 * the worker did. Output: one JSON object on stdout, consumed by
 * clinical_engine/tests/test_service_worker.py.
 *
 * Usage: node sw_harness.js <path/to/sw.js>
 */

const fs = require('fs');
const vm = require('vm');

const SCOPE = 'http://127.0.0.1:8080/';
const source = fs.readFileSync(process.argv[2], 'utf-8');

// ---- fakes -------------------------------------------------------------------

function absolute(input) {
  const raw = typeof input === 'string' ? input : input.url;
  return new URL(raw, SCOPE).href;
}

class FakeRequest {
  constructor(input, init = {}) {
    this.url = absolute(input);
    this.method = (init.method || (typeof input === 'object' && input.method) || 'GET').toUpperCase();
    this.mode = init.mode || (typeof input === 'object' && input.mode) || 'cors';
    this.cache = init.cache || 'default';
  }
}

class FakeCache {
  constructor() {
    this.store = new Map();
  }
  async add(request) {
    const response = await globalFetch(request);
    if (!response || !response.ok) {
      throw new TypeError('cache.add: response status not ok (' + (response && response.status) + ')');
    }
    await this.put(request, response);
  }
  async put(request, response) {
    this.store.set(absolute(request), { status: response.status, body: await response.clone().text() });
  }
  async match(request) {
    const hit = this.store.get(absolute(request));
    if (!hit) return undefined;
    return new Response(hit.body, { status: hit.status, headers: { 'X-From-Cache': '1' } });
  }
  async keys() {
    return [...this.store.keys()];
  }
}

class FakeCacheStorage {
  constructor() {
    this.caches = new Map();
  }
  async open(name) {
    if (!this.caches.has(name)) this.caches.set(name, new FakeCache());
    return this.caches.get(name);
  }
  async keys() {
    return [...this.caches.keys()];
  }
  async delete(name) {
    return this.caches.delete(name);
  }
  async has(name) {
    return this.caches.has(name);
  }
}

// The scripted network: scenario sets `network.handler(url, request)`.
const network = { handler: null, calls: [] };
async function globalFetch(input) {
  const url = absolute(input);
  network.calls.push({ url, cache: typeof input === 'object' && input.cache ? input.cache : 'default' });
  if (!network.handler) throw new TypeError('fetch failed (no network in this scenario)');
  return network.handler(url, input);
}

function ok(body, extra = {}) {
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/plain' }, ...extra });
}
function status(code) {
  return new Response('status ' + code, { status: code });
}
function offline() {
  throw new TypeError('fetch failed (offline)');
}

// ---- worker boot --------------------------------------------------------------

function bootWorker() {
  const listeners = {};
  const state = { skipWaiting: 0, claim: 0 };
  const self = {
    location: new URL('sw.js', SCOPE),
    addEventListener(type, fn) {
      (listeners[type] = listeners[type] || []).push(fn);
    },
    skipWaiting() {
      state.skipWaiting += 1;
      return Promise.resolve();
    },
    clients: {
      claim() {
        state.claim += 1;
        return Promise.resolve();
      },
    },
  };
  const caches = new FakeCacheStorage();
  const sandbox = {
    self,
    caches,
    fetch: globalFetch,
    Request: FakeRequest,
    Response,
    URL,
    console,
    Promise,
    Error,
    TypeError,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: 'sw.js' });

  const consts = vm.runInContext(
    '({ CACHE_VERSION, CACHE_NAME, SHELL_URL, PRECACHE_URLS, ENGINE_PREFIXES })',
    sandbox
  );

  async function dispatch(type, event) {
    const waits = [];
    event.waitUntil = (p) => waits.push(p);
    for (const fn of listeners[type] || []) fn(event);
    await Promise.all(waits);
  }

  async function dispatchFetch(request) {
    let responded = null;
    const event = { request, respondWith: (p) => (responded = Promise.resolve(p)) };
    for (const fn of listeners.fetch || []) fn(event);
    if (!responded) return { intercepted: false };
    const response = await responded;
    return {
      intercepted: true,
      status: response.status,
      body: await response.clone().text(),
      contentType: response.headers.get('Content-Type'),
      fromCache: response.headers.get('X-From-Cache') === '1',
    };
  }

  return { listeners, state, caches, consts, dispatch, dispatchFetch };
}

async function cacheSnapshot(caches, name) {
  const cache = await caches.open(name);
  const entries = {};
  for (const [url, hit] of cache.store) entries[url.replace(SCOPE, './')] = hit.body;
  return entries;
}

// ---- scenarios ---------------------------------------------------------------

const scenarios = {};

scenarios.install_precaches_everything = async () => {
  const w = bootWorker();
  network.handler = (url) => ok('asset:' + url);
  await w.dispatch('install', {});
  const snapshot = await cacheSnapshot(w.caches, w.consts.CACHE_NAME);
  return {
    cacheName: w.consts.CACHE_NAME,
    cacheVersion: w.consts.CACHE_VERSION,
    precacheUrls: w.consts.PRECACHE_URLS,
    cachedUrls: Object.keys(snapshot).sort(),
    skipWaiting: w.state.skipWaiting,
    shellCached: Object.prototype.hasOwnProperty.call(snapshot, w.consts.SHELL_URL),
    requestCacheModes: [...new Set(network.calls.map((c) => c.cache))],
  };
};

scenarios.install_survives_a_missing_optional_asset = async () => {
  const w = bootWorker();
  network.handler = (url) => (url.endsWith('/vendor/webfonts/fa-brands-400.woff2') ? status(404) : ok('asset'));
  let error = null;
  try {
    await w.dispatch('install', {});
  } catch (e) {
    error = String(e.message);
  }
  const snapshot = await cacheSnapshot(w.caches, w.consts.CACHE_NAME);
  return {
    error,
    shellCached: Object.prototype.hasOwnProperty.call(snapshot, w.consts.SHELL_URL),
    missingCached: Object.prototype.hasOwnProperty.call(snapshot, './vendor/webfonts/fa-brands-400.woff2'),
    cachedCount: Object.keys(snapshot).length,
    skipWaiting: w.state.skipWaiting,
  };
};

scenarios.install_fails_without_the_shell = async () => {
  const w = bootWorker();
  network.handler = (url) => (url.endsWith('/antibiotic_calc.html') ? offline() : ok('asset'));
  let error = null;
  try {
    await w.dispatch('install', {});
  } catch (e) {
    error = String(e.message);
  }
  return { error, skipWaiting: w.state.skipWaiting };
};

scenarios.activate_deletes_every_other_cache = async () => {
  const w = bootWorker();
  await w.caches.open('build-000000000000');
  await w.caches.open('antibio-v4');
  await w.caches.open(w.consts.CACHE_NAME);
  await w.dispatch('activate', {});
  return { remaining: await w.caches.keys(), claim: w.state.claim };
};

scenarios.fetch_routing = async () => {
  const w = bootWorker();
  network.handler = () => ok('net');
  const probe = async (url, init) => (await w.dispatchFetch(new FakeRequest(url, init))).intercepted;
  return {
    post_same_origin: await probe('./antibiotic_calc.html', { method: 'POST' }),
    put_engine: await probe('/v2/personal/owner', { method: 'PUT' }),
    cross_origin_get: await probe('https://cdn.example.com/tailwind.js'),
    engine_v1: await probe('/v1/recommend'),
    engine_v1_exact: await probe('/v1'),
    engine_v2_nested_query: await probe('/v2/personal/attestations?limit=5'),
    engine_navigation: await probe('/v2/personal', { mode: 'navigate' }),
    lookalike_v10: await probe('/v10/x'),
    shell_navigation: await probe('/', { mode: 'navigate' }),
    vendor_asset: await probe('./vendor/app.css'),
    icon_asset: await probe('./icons/icon-192.png'),
  };
};

scenarios.navigation_online_refreshes_the_cached_shell = async () => {
  const w = bootWorker();
  network.handler = () => ok('shell-v1');
  await w.dispatch('install', {});
  network.handler = () => ok('shell-v2', { headers: { 'Content-Type': 'text/html' } });
  const result = await w.dispatchFetch(new FakeRequest('/', { mode: 'navigate' }));
  const snapshot = await cacheSnapshot(w.caches, w.consts.CACHE_NAME);
  return { result, cachedShell: snapshot[w.consts.SHELL_URL] };
};

scenarios.navigation_server_error_is_passed_through_and_not_cached = async () => {
  const w = bootWorker();
  network.handler = () => ok('shell-v1');
  await w.dispatch('install', {});
  network.handler = () => status(500);
  const result = await w.dispatchFetch(new FakeRequest('/antibiotic_calc.html', { mode: 'navigate' }));
  const snapshot = await cacheSnapshot(w.caches, w.consts.CACHE_NAME);
  return { result, cachedShell: snapshot[w.consts.SHELL_URL] };
};

scenarios.navigation_offline_serves_the_cached_shell = async () => {
  const w = bootWorker();
  network.handler = () => ok('shell-v1');
  await w.dispatch('install', {});
  network.handler = offline;
  // any navigation (deep link, query string) falls back to the single shell
  const result = await w.dispatchFetch(new FakeRequest('/?from=homescreen', { mode: 'navigate' }));
  return { result };
};

scenarios.navigation_offline_without_cache_is_503 = async () => {
  const w = bootWorker();
  network.handler = offline;
  const result = await w.dispatchFetch(new FakeRequest('/', { mode: 'navigate' }));
  return { result };
};

scenarios.asset_stale_while_revalidate = async () => {
  const w = bootWorker();
  network.handler = () => ok('css-v1');
  await w.dispatch('install', {});
  let resolveNetwork;
  const gate = new Promise((r) => (resolveNetwork = r));
  network.handler = () => gate.then(() => ok('css-v2'));
  const result = await w.dispatchFetch(new FakeRequest('./vendor/app.css'));
  const before = (await cacheSnapshot(w.caches, w.consts.CACHE_NAME))['./vendor/app.css'];
  resolveNetwork();
  await new Promise((r) => setTimeout(r, 10));
  const after = (await cacheSnapshot(w.caches, w.consts.CACHE_NAME))['./vendor/app.css'];
  return { result, before, after };
};

scenarios.asset_uncached_online_is_fetched_and_cached = async () => {
  const w = bootWorker();
  network.handler = () => ok('font-bytes');
  const result = await w.dispatchFetch(new FakeRequest('./vendor/fonts/extra.woff2'));
  await new Promise((r) => setTimeout(r, 10));
  const snapshot = await cacheSnapshot(w.caches, w.consts.CACHE_NAME);
  return { result, cached: snapshot['./vendor/fonts/extra.woff2'] };
};

scenarios.asset_uncached_offline_is_504 = async () => {
  const w = bootWorker();
  network.handler = offline;
  const result = await w.dispatchFetch(new FakeRequest('./vendor/app.css'));
  return { result };
};

scenarios.asset_error_status_is_not_cached = async () => {
  const w = bootWorker();
  network.handler = () => status(404);
  const result = await w.dispatchFetch(new FakeRequest('./vendor/missing.css'));
  await new Promise((r) => setTimeout(r, 10));
  const snapshot = await cacheSnapshot(w.caches, w.consts.CACHE_NAME);
  return { result, cachedCount: Object.keys(snapshot).length };
};

// ---- run ----------------------------------------------------------------------

(async () => {
  const out = {};
  for (const [name, fn] of Object.entries(scenarios)) {
    network.handler = null;
    network.calls = [];
    try {
      out[name] = await fn();
    } catch (e) {
      out[name] = { harnessError: String((e && e.stack) || e) };
    }
  }
  process.stdout.write(JSON.stringify(out));
})();
