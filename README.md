# Offline Crop Health — Build Beyond ’26

Android application and interactive browser preview for **PS 4.1**, built for Team Debuggers. The white/lavender/purple screens follow the supplied Figma screenshots. Both clients execute the same bundled MobileNetV4 model locally.

## Repository structure

| Directory | Responsibility |
|---|---|
| [`frontend/`](frontend/) | React/TypeScript browser preview, screens, local inference, offline cache and browser storage |
| [`backend/`](backend/README.md) | Node preview host and health endpoint; no photo uploads or remote diagnosis |
| [`models/`](models/README.md) | Canonical ONNX model, class order, metadata, policy, checksum and model card, shared by Android and web |
| [`database/`](database/README.md) | Actual Android Room/SQLite schema and browser IndexedDB schema/documentation |
| [`android/`](android/) | Native Kotlin/Compose app, CameraX, application logic, Room and ONNX Runtime Android |
| [`ml/`](ml/README.md) | Dataset acquisition, training, calibration, export and recorded results |
| [`content/`](content/README.md) | Bilingual content and reproducible offline audio generation |
| [`contracts/`](contracts/) | Stable 17-class taxonomy and independent preprocessing fixtures |
| [`scripts/`](scripts/) | Shared-asset synchronization and offline web packaging |
| [`docs/`](docs/) | Architecture, setup, demonstration and validation records |

See [repository architecture](docs/REPOSITORY_STRUCTURE.md) for the request/data flow. A central database is unnecessary: browser history stays in IndexedDB and Android history stays in Room/SQLite.

## Run the browser preview

Use Node.js 22 or newer:

```sh
npm ci
npm run build
npm start
```

Open `http://localhost:3000`. For development, run `npm run dev` and open `http://localhost:5173`.

The first browser visit downloads the model, WASM runtime, content and audio. Wait for **Offline ready** before disconnecting. The service worker then supports offline reload and local inference. Browser and Android histories are separate device-local stores. Browser performance is not a native-phone benchmark.

## What is implemented

- Camera capture and gallery import with bounded decoding and EXIF orientation.
- Local **MobileNetV4-Conv-Small** inference through ONNX Runtime, with 17 tomato, potato, and maize condition labels.
- Photo-quality checks, real ranked scores, and explicit uncertain results.
- Three questions about observed symptoms, producing a user-reported concern level.
- English, Kannada and Hindi interface and general precautions, with **90 bundled neural-voice audio clips**: AI4Bharat Indic-TTS for Kannada and Piper for English/Hindi. Playback requires no speech API, installed language pack or phone TTS model. The selected language is remembered locally.
- Room-backed Android history and IndexedDB-backed browser history, with crop filters and targeted deletion.
- Offline help and model status. The installed Android app requests camera permission and has **no Internet permission**; the browser downloads assets on its first visit.

The target is Android 7.0+ on 3–4 GB RAM phones. Actual ARM-phone memory, latency, camera behavior, and Kannada pronunciation still require a physical-device check.

## Model status

The bundled V4 model is executable and trained from scratch; pretrained weights were unavailable through this environment’s network. It has 2,514,801 parameters, 17 logits, and a 960-dimensional embedding. The FP32 ONNX file is 10,032,309 bytes.

The selected epoch 14 achieved **60.45% accuracy / 0.5902 macro F1 on 536 source-validation images** after 15 total training epochs. Training used a bounded 2,152-image subset of the acquired PlantVillage data. These are source-validation results, not field accuracy or a held-out test result for this artifact. Complete physical-leaf independence is not established.

**Diagnosis validation remains false.** The app retains the model’s actual scores and routes results to uncertainty; it does not turn these experimental scores into a confirmed disease or pesticide prescription. The symptom questionnaire is separate from model confidence. Guidance is general observation advice, pending agricultural and language review.

Artifact identity: `mnv4-conv-small-supervised_from_scratch-d157e7c84013`.

SHA-256: `d157e7c8401319a700039de467caba6728b7bdbf35b4cdae1818757cf0ba7e3c`.

## Build and try it

See [Android build instructions](docs/BUILD_ANDROID.md). On this prepared cloud workspace:

```sh
/workspace/tools/android-build :app:assembleDebug :app:assembleDebugAndroidTest :app:testDebugUnitTest
```

Phone outputs are in `android/app/build/outputs/apk/debug/`: use `app-arm64-v8a-debug.apk` for most current Android phones, or `app-armeabi-v7a-debug.apk` for a 32-bit device. `app-universal-debug.apk` contains all supported ABIs. These are debug-signed prototype builds.

For a demonstration, enable airplane mode, open the app, choose the crop, scan or import a clear leaf photo, and run the assessment. Review its actual model scores and uncertain wording. Complete the symptom questions, play English/Kannada/Hindi audio, save the observation, and reopen it from History. The production app starts with empty history.

## Validation and project references

- [Executed checks and device evidence](docs/REVIEW2_VALIDATION.md)
- [Current architecture and tools](docs/ARCHITECTURE.md)
- [Current model receipts](ml/reports/review2_continued/STATUS.md)
- [Offline content and audio generation](content/README.md)
- [ML acquisition, training, and export](ml/README.md)
- [Product scope](docs/PRODUCT_SCOPE.md)
- [Dataset audit](docs/DATASET_AUDIT.md)
- [Review 1 presentation notes](docs/REVIEW_1.md)

Earlier planning documents describe intended release gates; the Review 2 validation record and current model receipts state what has actually been executed.
