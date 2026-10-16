/*  Service Worker — caches the app shell for offline use.
    API responses are never cached; only static assets. */

const CACHE_NAME = 'aifitness-shell-v3';
const SHELL_URLS = [
  '/static/index.html',
  '/static/manifest.json',
  '/static/icon.svg',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/icon-maskable-512.png',
  '/static/apple-touch-icon-180.png',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(SHELL_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Only handle GET requests for static assets
  if (event.request.method !== 'GET' || !url.pathname.startsWith('/static/')) {
    return;
  }

  // Network-first: try the network, update cache, fall back to cache
  event.respondWith(
    fetch(event.request)
      .then(response => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
