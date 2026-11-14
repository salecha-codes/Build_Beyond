# Browser QA

The browser suite uses real model assets and a real leaf fixture. It never seeds production diagnoses or exposes a production debug hook.

Run after the parent finishes the production frontend build and starts the production server (planned port 3000):

```sh
QA_BASE_URL=http://127.0.0.1:3000 node frontend/tests/browser-qa.cjs
```

Playwright is pinned by the repository lockfile as a root development dependency. On a fresh machine run `npm ci` and `npx playwright install chromium` from the repository root. Use `CHROMIUM_PATH` to select a browser; otherwise the runner uses `/usr/bin/chromium` when present, then Playwright's installed Chromium. Artifacts default to `frontend/test-results` (ignored); override `QA_ARTIFACTS` when needed. `npm run test:web` also runs the suite after the production server is ready.

Coverage (see [executed results and build boundaries](RESULTS.md)):

1. Mobile and desktop layouts have usable controls, no horizontal overflow, real empty history, and screenshots.
2. A pinned PlantVillage leaf travels through the actual gallery/file input and browser ONNX WASM inference. Output stays explicitly uncertain while policy is unvalidated.
3. A separate test-only browser harness calls the same inference module and checks all 17 finite scores, model SHA/version, real WASM execution and output shapes. Independent preprocessing fixtures check all tensor values.
4. Explicit symptom answers, Kannada content, bundled audio decode, and local history save/reopen/delete work.
5. After service-worker activation and required assets are cached, network is disabled and the app reloads and repeats inference/history access offline. No CDN/runtime backend dependency is accepted as offline proof.

Production UI/offline checks and the isolated inference harness use separate browser contexts. Playwright routing in the harness must not disable the HTTP cache or alter service-worker behavior in the production UI context. Browser execution/memory does not establish Android phone performance, and headless audio decoding does not establish audible speech quality.
