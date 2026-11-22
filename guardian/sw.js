// Sinh bởi tools/build_guardian_page.py. Chỉ để trang người giám hộ mở được khi mất mạng; không chạm vào localStorage.
const CACHE = "chotto-guardian-9x29Z48hEuR8";
self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.add(new Request('./', {cache: 'reload'}))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET' || request.mode !== 'navigate') return;
  event.respondWith(caches.open(CACHE).then(async (cache) => {
    const cached = await cache.match('./', {ignoreSearch: true});
    const refresh = fetch(request).then((response) => { if (response.ok) cache.put('./', response.clone()); return response; });
    if (cached) { refresh.catch(() => undefined); return cached; }
    return refresh;
  }));
});
