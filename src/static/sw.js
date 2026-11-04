/* App shell + bounded offline page cache. Live API state is never cached. */
const VERSION = "v2";
const SHELL_CACHE = "jh-shell-" + VERSION;
const RUNTIME_CACHE = "jh-runtime-" + VERSION;
const SHELL_ASSETS = [
  "/static/app.css", "/static/vendor/alpine.min.js", "/static/js/app.js",
  "/static/js/profile.js", "/static/js/onboarding.js", "/static/fonts/inter-var.woff2",
  "/static/favicon.svg", "/static/manifest.webmanifest", "/static/icons/icon-192.png",
  "/static/icons/icon-512.png", "/static/icons/icon-maskable-512.png", "/offline",
];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(SHELL_CACHE).then(cache => cache.addAll(SHELL_ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys
    .filter(key => key.startsWith("jh-") && key !== SHELL_CACHE && key !== RUNTIME_CACHE)
    .map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/health" || url.pathname === "/static/sw.js") return;
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(caches.match(request).then(cached => cached || fetch(request).then(async response => {
      if (response.ok) await (await caches.open(SHELL_CACHE)).put(request, response.clone());
      return response;
    })));
    return;
  }
  if (request.mode !== "navigate") return;
  event.respondWith(fetch(request).then(async response => {
    if (response.ok && !response.redirected) {
      const cache = await caches.open(RUNTIME_CACHE);
      await cache.put(request, response.clone());
      const keys = await cache.keys();
      for (const old of keys.slice(0, Math.max(0, keys.length - 50))) await cache.delete(old);
    }
    return response;
  }).catch(async () => (await caches.match(request)) || (await caches.match("/offline")) || Response.error()));
});
