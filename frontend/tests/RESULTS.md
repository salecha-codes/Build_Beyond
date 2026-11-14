# Executed browser QA

On 2026-11-14, Chromium ran **nine checks successfully** against the production server at `http://127.0.0.1:3000/`, in 5.14 seconds. The tested service-worker cache was `crop-health-a5a3aaded32d1440`, containing 73 local assets.

- Real file selection executed MobileNetV4 through ONNX Runtime WASM. All 17 scores were finite and normalized; outputs were `[1,17]` and `[1,960]` and matched the expected model hash.
- The UI kept the actual result explicitly uncertain/unvalidated. The example's top candidates were healthy-looking 40.9% and Septoria leaf spot 17.7%; these are model outputs, not an accuracy claim.
- All three symptom answers, Kannada content and actual bundled audio playback worked. Audio had finite duration and advancing playback time.
- IndexedDB stored the actual photo, score, model version and observation concern; reopening restored the saved result. Only the QA record was deleted.
- With the browser network disabled, service-worker reload, history access, repeated real inference and Kannada audio playback all worked.
- Mobile and desktop layouts had no horizontal overflow. Both independent Python preprocessing fixtures matched every one of their 150,528 values with **zero** maximum, mean and p99 error (strict absolute tolerance 1e-5).

No JavaScript page exceptions occurred. The run logged a missing favicon and a benign ONNX host CPU-vendor warning. The favicon was subsequently added.

**Build boundary:** this evidence precedes the final favicon, relative deployment-base and source-formatting changes. The final build and `/Build_Beyond/` prefix have not received another full browser run; testing stopped when the user requested fast delivery. The current runner contains prepared checks for those paths and clean resource loading. Do not describe them as executed.

Headless playback/decoding does not establish audible speech quality. These browser results do not establish Android phone latency, RAM, field accuracy, or agricultural/Kannada content review.

Screenshots from the executed run:

- [Desktop Home](screenshots/desktop-home.png)
- [Actual model result](screenshots/mobile-real-result.png)
- [Kannada guidance](screenshots/mobile-kannada-guidance.png)
- [Network-disabled actual inference](screenshots/mobile-offline-real-inference.png)

Raw task-workspace evidence is in `/workspace/web-preview-qa/summary.json`, `real-wasm-inference.json`, `browser-preprocessing.json`, and `offline-cache.json`. The model SHA-256 is `d157e7c8401319a700039de467caba6728b7bdbf35b4cdae1818757cf0ba7e3c`.
