const CACHE = 'burgschule-speiseplan-v2';
const CORE = [
  './', './index.html', './styles.css', './app.mjs', './date-utils.mjs',
  './impressum.html', './datenschutz.html', './manifest.webmanifest', './data/menu.json',
  './icons/icon.svg', './icons/icon-192.png', './icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(CORE)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (event) => {
  event.waitUntil(Promise.all([
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))),
    self.clients.claim(),
  ]));
});
self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const path = new URL(request.url).pathname;
    const isData = path.endsWith('/data/menu.json');
    const legal = path.endsWith('/impressum.html') || path.endsWith('/datenschutz.html');
    const key = request.mode === 'navigate'
      ? (legal ? new URL(path, self.location.origin).href : new URL('./index.html', self.registration.scope).href)
      : request.url;
    try {
      const response = await fetch(request);
      if (response.ok) await cache.put(key, response.clone());
      return response;
    } catch (error) {
      const stored = await cache.match(key);
      if (!stored) throw error;
      if (isData) {
        const headers = new Headers(stored.headers);
        headers.set('X-Offline-Copy', 'yes');
        return new Response(await stored.blob(), { status: stored.status, headers });
      }
      return stored;
    }
  })());
});
