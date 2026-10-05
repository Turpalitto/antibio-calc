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
 *   * any path outside the app root and `icons/`;
 *   * any extension outside ALLOWED_EXTENSIONS;
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
 * Environment
 *   PORT               (default 8080)
 *   HOST               (default 127.0.0.1) — set to 0.0.0.0 to expose on the LAN
 *   ENGINE_BASE_URL    (default http://<ENGINE_HOST>:<ENGINE_PORT>)
 *   ENGINE_HOST        (default 127.0.0.1)   ENGINE_PORT (default 8000)
 *   ENGINE_TIMEOUT_MS  (default 20000)
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

  const file = path.resolve(ROOT, '.' + path.posix.normalize(pathname));
  // Containment: strictly inside ROOT, never ROOT itself and never a sibling
  // whose name merely starts with ROOT's name.
  if (file !== ROOT && !file.startsWith(ROOT + path.sep)) {
    return { status: 403, code: 'OUTSIDE_ROOT' };
  }
  // Directory allowlist: only the flat app root, icons/ and the self-hosted
  // asset tree vendor/ (Tailwind/Font Awesome/fonts, audit S-3) are servable.
  const segments = path.relative(ROOT, file).split(path.sep);
  if (segments.length > 1 && segments[0] !== 'icons' && segments[0] !== 'vendor') {
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
  // Only the path+query of the incoming request is reused. The upstream origin is
  // always ENGINE_BASE_URL, so an absolute-form request target
  // (`GET http://elsewhere/v2/x`) cannot turn this proxy into an open relay.
  const incoming = new URL(req.url, 'http://incoming.invalid');
  const target = new URL(incoming.pathname + incoming.search, ENGINE_BASE_URL);
  const headers = {};
  for (const [name, value] of Object.entries(req.headers)) {
    if (!HOP_BY_HOP.has(name.toLowerCase())) headers[name] = value;
  }

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

server.listen(PORT, HOST, () => {
  console.log(
    `ANTIBIO serving ${ROOT} at http://${HOST}:${PORT} (engine proxy ${PROXY_PREFIXES.join(', ')} -> ${ENGINE_BASE_URL})`
  );
});
