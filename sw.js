const CACHE = 'crop-health-14dd5e1e6836c7cd';
const FILES = ["assets/audio/en/maize_common_rust.ogg","assets/audio/en/maize_gray_leaf_spot.ogg","assets/audio/en/maize_healthy.ogg","assets/audio/en/maize_northern_leaf_blight.ogg","assets/audio/en/potato_early_blight.ogg","assets/audio/en/potato_healthy.ogg","assets/audio/en/potato_late_blight.ogg","assets/audio/en/prompt_check_expert.ogg","assets/audio/en/prompt_concern_coverage.ogg","assets/audio/en/prompt_concern_expert.ogg","assets/audio/en/prompt_concern_observe.ogg","assets/audio/en/prompt_concern_plants.ogg","assets/audio/en/prompt_concern_spreading.ogg","assets/audio/en/prompt_crop_mismatch.ogg","assets/audio/en/prompt_healthy.ogg","assets/audio/en/prompt_model_prototype.ogg","assets/audio/en/prompt_model_unavailable.ogg","assets/audio/en/prompt_offline.ogg","assets/audio/en/prompt_retake.ogg","assets/audio/en/prompt_uncertain.ogg","assets/audio/en/tomato_bacterial_spot.ogg","assets/audio/en/tomato_early_blight.ogg","assets/audio/en/tomato_healthy.ogg","assets/audio/en/tomato_late_blight.ogg","assets/audio/en/tomato_leaf_mold.ogg","assets/audio/en/tomato_mosaic_virus.ogg","assets/audio/en/tomato_septoria_leaf_spot.ogg","assets/audio/en/tomato_spider_mites.ogg","assets/audio/en/tomato_target_spot.ogg","assets/audio/en/tomato_yellow_leaf_curl_virus.ogg","assets/audio/hi/maize_common_rust.ogg","assets/audio/hi/maize_gray_leaf_spot.ogg","assets/audio/hi/maize_healthy.ogg","assets/audio/hi/maize_northern_leaf_blight.ogg","assets/audio/hi/potato_early_blight.ogg","assets/audio/hi/potato_healthy.ogg","assets/audio/hi/potato_late_blight.ogg","assets/audio/hi/prompt_check_expert.ogg","assets/audio/hi/prompt_concern_coverage.ogg","assets/audio/hi/prompt_concern_expert.ogg","assets/audio/hi/prompt_concern_observe.ogg","assets/audio/hi/prompt_concern_plants.ogg","assets/audio/hi/prompt_concern_spreading.ogg","assets/audio/hi/prompt_crop_mismatch.ogg","assets/audio/hi/prompt_healthy.ogg","assets/audio/hi/prompt_model_prototype.ogg","assets/audio/hi/prompt_model_unavailable.ogg","assets/audio/hi/prompt_offline.ogg","assets/audio/hi/prompt_retake.ogg","assets/audio/hi/prompt_uncertain.ogg","assets/audio/hi/tomato_bacterial_spot.ogg","assets/audio/hi/tomato_early_blight.ogg","assets/audio/hi/tomato_healthy.ogg","assets/audio/hi/tomato_late_blight.ogg","assets/audio/hi/tomato_leaf_mold.ogg","assets/audio/hi/tomato_mosaic_virus.ogg","assets/audio/hi/tomato_septoria_leaf_spot.ogg","assets/audio/hi/tomato_spider_mites.ogg","assets/audio/hi/tomato_target_spot.ogg","assets/audio/hi/tomato_yellow_leaf_curl_virus.ogg","assets/audio/kn/maize_common_rust.ogg","assets/audio/kn/maize_gray_leaf_spot.ogg","assets/audio/kn/maize_healthy.ogg","assets/audio/kn/maize_northern_leaf_blight.ogg","assets/audio/kn/potato_early_blight.ogg","assets/audio/kn/potato_healthy.ogg","assets/audio/kn/potato_late_blight.ogg","assets/audio/kn/prompt_check_expert.ogg","assets/audio/kn/prompt_concern_coverage.ogg","assets/audio/kn/prompt_concern_expert.ogg","assets/audio/kn/prompt_concern_observe.ogg","assets/audio/kn/prompt_concern_plants.ogg","assets/audio/kn/prompt_concern_spreading.ogg","assets/audio/kn/prompt_crop_mismatch.ogg","assets/audio/kn/prompt_healthy.ogg","assets/audio/kn/prompt_model_prototype.ogg","assets/audio/kn/prompt_model_unavailable.ogg","assets/audio/kn/prompt_offline.ogg","assets/audio/kn/prompt_retake.ogg","assets/audio/kn/prompt_uncertain.ogg","assets/audio/kn/tomato_bacterial_spot.ogg","assets/audio/kn/tomato_early_blight.ogg","assets/audio/kn/tomato_healthy.ogg","assets/audio/kn/tomato_late_blight.ogg","assets/audio/kn/tomato_leaf_mold.ogg","assets/audio/kn/tomato_mosaic_virus.ogg","assets/audio/kn/tomato_septoria_leaf_spot.ogg","assets/audio/kn/tomato_spider_mites.ogg","assets/audio/kn/tomato_target_spot.ogg","assets/audio/kn/tomato_yellow_leaf_curl_virus.ogg","assets/content/audio_manifest.json","assets/content/catalog.json","assets/content/hindi_ui.json","assets/index-D0oXNk2e.js","assets/index-qfGVXGjL.css","assets/model/MODEL_CARD.md","assets/model/crop_model.onnx","assets/model/decision_policy.json","assets/model/embedding_centroids.json","assets/model/export_receipt.json","assets/model/labels.json","assets/model/model_metadata.json","assets/model/source_evaluation.json","assets/ort-wasm-simd-threaded-BFiwp6Xy.mjs","assets/ort-wasm-simd-threaded-CxTQ5xH-.wasm","favicon.svg","index.html"];
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
      await Promise.all(
        (await caches.keys())
          .filter((key) => key.startsWith('crop-health-') && key !== CACHE)
          .map((key) => caches.delete(key)),
      );
      await self.clients.claim();
      for (const client of await self.clients.matchAll())
        client.postMessage({ type: 'CROP_OFFLINE_READY', version: CACHE });
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
