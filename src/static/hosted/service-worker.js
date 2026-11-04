'use strict';
const CACHE = 'jobhunt-hosted-shell-v3';
const ASSETS = [
  '/offline', '/static/hosted/style.css?v=3', '/static/hosted/app.js?v=3',
  '/static/fonts/inter-var.woff2', '/static/hosted/icons/icon-192.png',
  '/static/hosted/icons/icon-512.png', '/manifest.webmanifest'
];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)));
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter(name => name.startsWith('jobhunt-hosted-') && name !== CACHE).map(name => caches.delete(name)));
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/')) return;
  if (request.mode === 'navigate') {
    // No private HTML is written to a cache. The fallback has no account context.
    event.respondWith(fetch(request).catch(() => caches.match('/offline')));
    return;
  }
  if (url.pathname.startsWith('/static/hosted/') || url.pathname.startsWith('/static/fonts/') || url.pathname === '/manifest.webmanifest') {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE);
      const stored = await cache.match(request);
      if (stored) return stored;
      const response = await fetch(request);
      if (response.ok && response.type === 'basic') await cache.put(request, response.clone());
      return response;
    })());
  }
});
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});
