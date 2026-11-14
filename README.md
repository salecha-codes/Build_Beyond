# Offline Crop Health — Build Beyond ’26

Android application and interactive browser preview for **PS 4.1**, built for Team Debuggers. The white/lavender/purple screens follow the supplied Figma screenshots. Both clients execute the same bundled MobileNet model locally.

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
- Local **MobileNetV3-Large** inference through ONNX Runtime, with 17 tomato, potato, and maize condition labels.
- Photo-quality checks, real ranked scores, and explicit uncertain results.
- Three questions about observed symptoms, producing a user-reported concern level.
- English, Kannada and Hindi interface and general precautions, with **90 bundled neural-voice audio clips**: AI4Bharat Indic-TTS for Kannada and Piper for English/Hindi. Playback requires no speech API, installed language pack or phone TTS model. The selected language is remembered locally.
- Room-backed Android history and IndexedDB-backed browser history, with crop filters and targeted deletion.
- Offline help and model status. The installed Android app requests camera permission and has **no Internet permission**; the browser downloads assets on its first visit.

The target is Android 7.0+ on 3–4 GB RAM phones. Actual ARM-phone memory, latency, camera behavior, and Kannada pronunciation still require a physical-device check.

## Leaf input check

The model first checks whether the photo looks like a leaf. Rejected object photos return a retake request with **no disease name or score**. The leaf head shares the same offline backbone and adds about15KB.

A frozen threshold rejected125/125 held-out object/animal test photos, including computer mouse, hamster, cat, laptop and monitor. It retained76/80 field leaf photos and all31 correctly classified field cases, preserving38.75% end-to-end field accuracy on the reused benchmark. Source end-to-end accuracy after leaf rejection is91.94%. These are sample measurements, not universal guarantees; other plant leaves may still pass. See [leaf-check receipts](ml/reports/leaf_guard/) for data/protocols and limitations. Test photos are not bundled in the app.

## Model status

The current model is **MobileNetV3-Large**, using official ImageNet-pretrained visual features and a trained17-class disease head with TRAIN-only feature standardization embedded in ONNX. It replaces MobileNetV4 after tuning and frozen evaluation showed a stronger field result. The exact FP32 ONNX graph is11,965,503bytes and outputs17logits plus960visual features.

| Same frozen comparison | Images | V4 accuracy | Current V3 accuracy |
|---|---:|---:|---:|
| PlantVillage source | 3,674 | 94.67% | 92.11% |
| PlantDoc field-like | 80 | 22.50% | 38.75% |

Field recognition improves by16.25percentage points (18→31correct of80). **Field accuracy is still limited.** This80-photo set was already used for V4; it is a reused comparison benchmark, not newly blind independent data. Source accuracy must not be presented as field accuracy. External labels are mostly unreviewed.

Source accepted precision is96.47% at87.02%coverage. Field accepted precision is50.00% at47.50%coverage. Field validation and condition-specific advice remain false. Both apps show the actual predicted condition, with low-confidence or crop-mismatch labels when applicable; numeric gates and global17-class score semantics remain intact.

SHA-256: `3332b5634fcb1a8bea17317a0a9db4d6e44f9c0da24e7b03718b3ced5d6b2d1e`.

See [current training/evaluation receipts](ml/reports/field_upgrade_v3/) and [model card](models/assets/model/MODEL_CARD.md). Earlier V4 reports remain historical.

## Build and try it

See [Android build instructions](docs/BUILD_ANDROID.md). On this prepared cloud workspace:

```sh
/workspace/tools/android-build :app:assembleDebug :app:assembleDebugAndroidTest :app:testDebugUnitTest
```

Phone outputs are in `android/app/build/outputs/apk/debug/`: use `app-arm64-v8a-debug.apk` for most current Android phones, or `app-armeabi-v7a-debug.apk` for a 32-bit device. `app-universal-debug.apk` contains all supported ABIs. These are debug-signed prototype builds.

For a demonstration, enable airplane mode, open the app, choose the crop, scan or import a clear leaf photo, and run the assessment. Review its actual model match or uncertain result. Complete the symptom questions, play English/Kannada/Hindi audio, save the observation, and reopen it from History. The production app starts with empty history.

## Validation and project references

- [Executed checks and device evidence](docs/REVIEW2_VALIDATION.md)
- [Current architecture and tools](docs/ARCHITECTURE.md)
- [Current model receipts](ml/reports/field_upgrade_v3/)
- [Offline content and audio generation](content/README.md)
- [ML acquisition, training, and export](ml/README.md)
- [Product scope](docs/PRODUCT_SCOPE.md)
- [Dataset audit](docs/DATASET_AUDIT.md)
- [Review 1 presentation notes](docs/REVIEW_1.md)

Earlier planning documents describe intended release gates; the Review 2 validation record and current model receipts state what has actually been executed.
