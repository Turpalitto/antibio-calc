'use strict';
/**
 * ANTIBIO — local static server + live clinical-engine proxy.
 *
 * Design constraints
 * ------------------
 *  * Offline-first single-page calculator. Everything the app needs is a static
 *    file inside this directory; the calculator DB is embedded into
 *    `antibiotic_calc.html` at build time, so no API call is required to dose.
 *  * Loopback only by default. The physician-mode endpoints are loopback-only by
 *    policy, so the server must not be reachable from the LAN unless the operator
 *    explicitly sets HOST.
 *
 * Serves (read-only, from this directory only)
 *   /                       -> antibiotic_calc.html (the app shell)
 *   /antibiotic_calc.html   the app shell
 *   /sw.js                  service worker; must be served from the app root
 *   /manifest.webmanifest   PWA manifest
 *   /icons/*.png            PWA icons
 *
 * Never served
 *   * any request path containing ".." (checked after percent-decoding, so
 *     `%2e%2e%2f` is rejected too);
 *   * any dot-path — `.env`, `.git/`, and the gitignored
 *     `.local/personal_physician/` owner-token store are unreachable;
 *   * any root file outside the explicit ROOT_FILES allowlist (audit C-3,
 *     2026-10-14: `package.json`, `REPOSITORY_MANIFEST.json`, `server.js`,
 *     `sw.js` sources of other builds, … are not app assets) — only `icons/` and
 *     `vendor/` subtrees are servable, and only with an allowed extension;
 *   * any method other than GET / HEAD on a static path (405). Proxied engine
 *     requests keep their own method (the personal workflow is POST-heavy).
 *
 * Proxied (live, never cached, never read from disk)
 *   /v1/* and /v2/*  ->  ENGINE_BASE_URL, default http://127.0.0.1:8000
 *   (the FastAPI engine, `uvicorn clinical_engine.api.app:app`).
 *   sw.js deliberately never caches these paths, so the browser always observes
 *   the real engine status. When the engine is unreachable the proxy answers
 *   502 with a JSON body explaining why — it never falls back to the app shell,
 *   which would make the client parse 680 KB of HTML as a JSON API response.
 *
 *   Loopback peer policy (audit C-1, 2026-10-14). The engine's physician-mode
 *   endpoints trust the *peer address* (loopback only). A proxy that forwards
 *   LAN requests from 127.0.0.1 would silently defeat that gate, so the proxy
 *   itself refuses non-loopback peers with 403 PROXY_LOOPBACK_ONLY unless the
 *   operator opts in with ENGINE_PROXY_ALLOW_LAN=1 (and then the engine still
 *   sees X-Forwarded-For). Request bodies are capped at ENGINE_MAX_BODY_BYTES
 *   (413 PAYLOAD_TOO_LARGE) so the engine never has to buffer an unbounded body.
 *
 * Environment
 *   PORT                   (default 8080)
 *   HOST                   (default 127.0.0.1) — set to 0.0.0.0 to expose on the LAN
 *   ENGINE_BASE_URL        (default http://<ENGINE_HOST>:<ENGINE_PORT>)
 *   ENGINE_HOST            (default 127.0.0.1)   ENGINE_PORT (default 8000)
 *   ENGINE_TIMEOUT_MS      (default 20000)
 *   ENGINE_PROXY_ALLOW_LAN (default unset) — "1" forwards engine calls from LAN peers
 *   ENGINE_MAX_BODY_BYTES  (default 1048576) — proxied request body cap
 */

const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');

const ROOT = path.resolve(__dirname);
const DEFAULT_DOCUMENT = '/antibiotic_calc.html';
const PROXY_PREFIXES = ['/v1/', '/v2/'];
const ALLOWED_METHODS = new Set(['GET', 'HEAD']);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.ttf': 'font/ttf',
};
const ALLOWED_EXTENSIONS = new Set(Object.keys(MIME));

const PORT = Number(process.env.PORT || 8080);
const HOST = process.env.HOST || '127.0.0.1';
const ENGINE_BASE_URL = (
  process.env.ENGINE_BASE_URL ||
  `http://${process.env.ENGINE_HOST || '127.0.0.1'}:${process.env.ENGINE_PORT || 8000}`
).replace(/\/+$/, '');
const ENGINE_TIMEOUT_MS = Number(process.env.ENGINE_TIMEOUT_MS || 20000);
const ENGINE_CLIENT =
  ENGINE_BASE_URL.startsWith('https:') ? https : http;
const ENGINE_PROXY_ALLOW_LAN = process.env.ENGINE_PROXY_ALLOW_LAN === '1';
const ENGINE_MAX_BODY_BYTES = Number(process.env.ENGINE_MAX_BODY_BYTES || 1024 * 1024);

/** Root-level files the app shell actually needs. Everything else at the root is refused. */
const ROOT_FILES = new Set([
  '/antibiotic_calc.html',
  '/sw.js',
  '/manifest.webmanifest',
  '/favicon.ico',
]);
/** Subtrees that may be served (with an allowed extension). */
const ALLOWED_DIRS = new Set(['icons', 'vendor']);

/** True for IPv4/IPv6 loopback peers, including IPv4-mapped IPv6 form. */
function isLoopbackAddress(address) {
  if (!address) return false;
  const a = String(address).toLowerCase();
  if (a === '::1' || a === 'localhost') return true;
  const v4 = a.startsWith('::ffff:') ? a.slice(7) : a;
  return /^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(v4);
}

/**
 * Restrictive CSP. The app legitimately needs inline <script>/<style> (all of its
 * logic is inline). Every external asset (Tailwind, Font Awesome, Google Fonts)
 * is self-hosted under ./vendor — no third-party origins are needed anymore
 * (audit S-3, 2026-10-05): a compromised CDN can no longer execute script or
 * read the page (PHI in sessionStorage) from this origin.
 */
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self' data:",
  "img-src 'self' data: https://cr.minzdrav.gov.ru",
  "connect-src 'self'",
  "worker-src 'self'",
  "manifest-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join('; ');

const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'X-Frame-Options': 'DENY',
};

/** Headers for engine responses: upstream value first, our own as a floor. */
function forwardedSecurityHeaders() {
  return { 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer' };
}

function sendError(res, status, code, detail, extraHeaders) {
  const body = JSON.stringify({ error: code, detail: detail || null });
  res.writeHead(status, {
    ...SECURITY_HEADERS,
    ...(extraHeaders || {}),
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Cache-Control': 'no-store',
  });
  res.end(res.req && res.req.method === 'HEAD' ? undefined : body);
}

function isProxyPath(pathname) {
  return PROXY_PREFIXES.some((prefix) => pathname === prefix.slice(0, -1) || pathname.startsWith(prefix));
}

/**
 * Map a request path to an absolute file path inside ROOT.
 * Returns `{ status, file }`; `status` is 400 (malformed) or 403 (refused).
 */
function resolveStaticFile(rawUrl) {
  let parsed;
  try {
    parsed = new URL(rawUrl, 'http://localhost');
  } catch (_) {
    return { status: 400, code: 'MALFORMED_URL' };
  }

  let pathname;
  try {
    pathname = decodeURIComponent(parsed.pathname);
  } catch (_) {
    return { status: 400, code: 'MALFORMED_ENCODING' };
  }
  if (pathname.includes('\0')) {
    return { status: 400, code: 'MALFORMED_ENCODING' };
  }
  if (pathname === '/' || pathname === '') {
    pathname = DEFAULT_DOCUMENT;
  }
  // Rejected before resolution so that no normalisation is trusted to collapse
  // them; `path.resolve` would happily walk out of ROOT.
  if (pathname.includes('..')) {
    return { status: 403, code: 'PATH_TRAVERSAL' };
  }
  // Dot-paths hold secrets (.env, .git/, .local/personal_physician/).
  if (pathname.split('/').some((segment) => segment.startsWith('.'))) {
    return { status: 403, code: 'FORBIDDEN_PATH' };
  }
  if (!ALLOWED_EXTENSIONS.has(path.extname(pathname).toLowerCase())) {
    return { status: 403, code: 'FORBIDDEN_EXTENSION' };
  }

  const normalized = path.posix.normalize(pathname);
  const file = path.resolve(ROOT, '.' + normalized);
  // Containment: strictly inside ROOT, never ROOT itself and never a sibling
  // whose name merely starts with ROOT's name.
  if (file !== ROOT && !file.startsWith(ROOT + path.sep)) {
    return { status: 403, code: 'OUTSIDE_ROOT' };
  }
  // Allowlist: an explicit set of root files, plus the icons/ and self-hosted
  // vendor/ subtrees (Tailwind/Font Awesome/fonts, audit S-3). A repository
  // checkout holds many more .json/.js/.html files than the app needs.
  const segments = path.relative(ROOT, file).split(path.sep);
  if (segments.length === 1) {
    if (!ROOT_FILES.has(normalized)) return { status: 403, code: 'FORBIDDEN_PATH' };
  } else if (!ALLOWED_DIRS.has(segments[0])) {
    return { status: 403, code: 'FORBIDDEN_PATH' };
  }
  return { status: 200, file };
}

function serveStatic(req, res, file) {
  // realpath first: a symlink inside ROOT must not become a way out of ROOT.
  fs.realpath(file, (realErr, realFile) => {
    if (realErr) {
      const missing = realErr.code === 'ENOENT' || realErr.code === 'EISDIR';
      sendError(res, missing ? 404 : 500, missing ? 'NOT_FOUND' : 'READ_FAILED', realErr.code);
      return;
    }
    if (!realFile.startsWith(ROOT + path.sep)) {
      sendError(res, 403, 'SYMLINK_ESCAPE', 'the resolved path is outside the app root');
      return;
    }
    fs.readFile(realFile, (err, data) => {
      if (err) {
        const missing = err.code === 'ENOENT' || err.code === 'EISDIR';
        sendError(res, missing ? 404 : 500, missing ? 'NOT_FOUND' : 'READ_FAILED', err.code);
        return;
      }
      const ext = path.extname(realFile).toLowerCase();
      const headers = {
        ...SECURITY_HEADERS,
        'Content-Type': MIME[ext] || 'application/octet-stream',
        'Content-Length': data.length,
        'Cache-Control': 'no-cache',
      };
      if (ext === '.html') {
        headers['Content-Security-Policy'] = CSP;
      }
      res.writeHead(200, headers);
      res.end(req.method === 'HEAD' ? undefined : data);
    });
  });
}

const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
  'host',
  'content-length',
]);

function proxyToEngine(req, res) {
  // The engine's physician-mode gate trusts the peer address. Forwarding a LAN
  // request from 127.0.0.1 would launder it into a loopback request, so the
  // proxy enforces the same peer policy unless the operator opted in.
  const peer = req.socket && req.socket.remoteAddress;
  if (!ENGINE_PROXY_ALLOW_LAN && !isLoopbackAddress(peer)) {
    sendError(
      res,
      403,
      'PROXY_LOOPBACK_ONLY',
      'engine endpoints are proxied for loopback clients only; set ENGINE_PROXY_ALLOW_LAN=1 to forward LAN peers'
    );
    req.resume();
    return;
  }
  const declared = Number(req.headers['content-length'] || 0);
  if (declared > ENGINE_MAX_BODY_BYTES) {
    sendError(res, 413, 'PAYLOAD_TOO_LARGE', `request body exceeds ${ENGINE_MAX_BODY_BYTES} bytes`);
    req.resume();
    return;
  }
  // Only the path+query of the incoming request is reused. The upstream origin is
  // always ENGINE_BASE_URL, so an absolute-form request target
  // (`GET http://elsewhere/v2/x`) cannot turn this proxy into an open relay.
  const incoming = new URL(req.url, 'http://incoming.invalid');
  const target = new URL(incoming.pathname + incoming.search, ENGINE_BASE_URL);
  const headers = {};
  for (const [name, value] of Object.entries(req.headers)) {
    if (!HOP_BY_HOP.has(name.toLowerCase())) headers[name] = value;
  }
  // The engine must be able to tell a forwarded peer from a true loopback client.
  headers['x-forwarded-for'] = peer ? (req.headers['x-forwarded-for'] ? `${req.headers['x-forwarded-for']}, ${peer}` : String(peer)) : (req.headers['x-forwarded-for'] || 'unknown');

  const upstream = ENGINE_CLIENT.request(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port || (target.protocol === 'https:' ? 443 : 80),
      method: req.method,
      path: target.pathname + target.search,
      headers,
    },
    (engineRes) => {
      const out = { ...forwardedSecurityHeaders() };
      for (const [name, value] of Object.entries(engineRes.headers)) {
        if (!HOP_BY_HOP.has(name.toLowerCase())) out[name] = value;
      }
      res.writeHead(engineRes.statusCode || 502, out);
      engineRes.pipe(res);
    }
  );

  upstream.setTimeout(ENGINE_TIMEOUT_MS, () => {
    upstream.destroy(Object.assign(new Error('engine timeout'), { code: 'ETIMEDOUT' }));
  });
  upstream.on('error', (err) => {
    if (res.headersSent) {
      res.destroy();
      return;
    }
    sendError(
      res,
      502,
      'ENGINE_UNAVAILABLE',
      `clinical engine at ${ENGINE_BASE_URL} is not reachable (${err.code || err.message}); ` +
        'start it with: uvicorn clinical_engine.api.app:app --port 8000'
    );
  });

  // Streaming cap: a chunked body (no Content-Length) is still bounded.
  let received = 0;
  req.on('data', (chunk) => {
    received += chunk.length;
    if (received > ENGINE_MAX_BODY_BYTES) {
      upstream.destroy();
      if (!res.headersSent) {
        sendError(res, 413, 'PAYLOAD_TOO_LARGE', `request body exceeds ${ENGINE_MAX_BODY_BYTES} bytes`);
      } else {
        res.destroy();
      }
      req.destroy();
    }
  });
  req.on('error', () => upstream.destroy());
  req.pipe(upstream);
}

const server = http.createServer((req, res) => {
  let pathname = '/';
  try {
    pathname = new URL(req.url || '/', 'http://localhost').pathname;
  } catch (_) {
    sendError(res, 400, 'MALFORMED_URL');
    return;
  }

  // Engine endpoints are forwarded with their own method and body (the personal
  // workflow is POST-heavy); the method allowlist below guards *static* serving
  // only, because a static file server has no business accepting a write.
  if (isProxyPath(pathname)) {
    proxyToEngine(req, res);
    return;
  }

  if (!ALLOWED_METHODS.has(req.method || 'GET')) {
    sendError(res, 405, 'METHOD_NOT_ALLOWED', 'only GET and HEAD are supported', { Allow: 'GET, HEAD' });
    return;
  }

  const resolved = resolveStaticFile(req.url || '/');
  if (resolved.status !== 200) {
    sendError(
      res,
      resolved.status,
      resolved.code,
      resolved.status === 404 ? 'no such file' : 'the request path was refused'
    );
    return;
  }

  serveStatic(req, res, resolved.file);
});

server.on('clientError', (err, socket) => {
  if (socket.writable) {
    socket.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n');
  }
});

module.exports = { resolveStaticFile, isLoopbackAddress, isProxyPath, ROOT_FILES, ALLOWED_DIRS };

if (require.main === module) {
  server.listen(PORT, HOST, () => {
    console.log(
      `ANTIBIO serving ${ROOT} at http://${HOST}:${PORT} (engine proxy ${PROXY_PREFIXES.join(', ')} -> ${ENGINE_BASE_URL}` +
        `; LAN peers ${ENGINE_PROXY_ALLOW_LAN ? 'FORWARDED (ENGINE_PROXY_ALLOW_LAN=1)' : 'refused'}; body cap ${ENGINE_MAX_BODY_BYTES} B)`
    );
  });
}
