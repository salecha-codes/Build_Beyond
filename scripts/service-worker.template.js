const CACHE = 'crop-health-__CACHE_VERSION__';
const FILES = __PRECACHE_LIST__;
const root = self.registration.scope;
const absolute = (file) => new URL(file, root).href;
self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      // Limit concurrent downloads so model/runtime precaching works on slower links.
      for (let index = 0; index < FILES.length; index += 6) {
        await Promise.all(
          FILES.slice(index, index + 6).map((file) =>
            cache.add(new Request(absolute(file), { cache: 'reload' })),
          ),
        );
      }
      await self.skipWaiting();
    })(),
  );
});
self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const oldCaches = (await caches.keys()).filter((key) => key.startsWith('crop-health-') && key !== CACHE);
      await Promise.all(
        oldCaches.map((key) => caches.delete(key)),
      );
      await self.clients.claim();
      for (const client of await self.clients.matchAll())
        client.postMessage({ type: 'CROP_OFFLINE_READY', version: CACHE });
      // Older pages do not know about the leaf-check output. Reload once when
      // replacing their offline bundle so stale JS cannot bypass new checks.
      if (oldCaches.length) for (const client of await self.clients.matchAll({ type: 'window' }))
        // Navigation may wait for activation; awaiting it here would deadlock.
        void client.navigate(client.url).catch(() => undefined);
    })(),
  );
});
self.addEventListener('message', (event) => {
  if (event.data?.type === 'CROP_OFFLINE_STATUS')
    event.source?.postMessage({ type: 'CROP_OFFLINE_READY', version: CACHE });
});
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET' || !event.request.url.startsWith(root)) return;
  if (event.request.url.includes('/api/')) return;
  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE);
      const cached = await cache.match(event.request, { ignoreSearch: true });
      if (event.request.mode === 'navigate') {
        try { return await fetch(new Request(event.request, { cache: 'no-cache' })); }
        catch { if (cached) return cached; }
      }
      if (cached) return cached;
      try {
        return await fetch(event.request);
      } catch (error) {
        if (event.request.mode === 'navigate') {
          const shell = await cache.match(absolute('index.html'));
          if (shell) return shell;
        }
        throw error;
      }
    })(),
  );
});
