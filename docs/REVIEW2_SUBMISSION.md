# Review 2 — working prototype

Repository: https://github.com/salecha-codes/Build_Beyond

Browser demo: https://salecha-codes.github.io/Build_Beyond/

## Implemented

Native Android (Kotlin/Compose) and browser preview (React/TypeScript), using the same bundled ONNX model. Camera/gallery, bounded image decoding, photo-quality checks, leaf/object screening, 17 condition labels for tomato/potato/maize, real predicted condition and score, low-confidence/crop-mismatch messages, three symptom questions, general observation guidance, 90 bundled English/Kannada/Hindi audio clips, and local history are implemented. Android uses Room/SQLite; the browser uses IndexedDB. The Node backend serves preview files and a health endpoint. Inference and saved observations stay on the device. Android has no Internet permission.

## Current model

MobileNetV3-Large with official ImageNet-pretrained features, a trained 17-class disease head and a separate small leaf/object head. Current graph SHA: `3332b5634fcb1a8bea17317a0a9db4d6e44f9c0da24e7b03718b3ced5d6b2d1e`. The app truthfully reports V3 after switching from V4 following measured comparisons.

Disease-classifier accuracy: 92.11% on 3,674 PlantVillage source photos and 38.75% on the reused 80-photo PlantDoc field comparison. Including leaf rejection, source accuracy is 91.94%; all 31 correct field predictions pass, so field accuracy remains 38.75%. Field recognition remains limited. It is a prototype, with no field-diagnosis or chemical-treatment validation. The symptom questionnaire measures reported concern, not image-based severity.

The leaf check rejected 125/125 held-out object/animal sample photos, including mouse, cat, hamster, laptop and monitor. Both actual browser and Android tests confirmed mouse rejection with no disease result. These are sample measurements, not a guarantee for every unseen image or plant species. Source/test/group and licensing limitations are documented in the bound model receipts.

## Run

Browser: Node.js 22+, then `npm ci`, `npm run build`, `npm start`; open http://localhost:3000. Wait for Offline ready before disconnecting.

Android: JDK 17 and Android SDK 35; configure the SDK path, then `./gradlew :app:assembleDebug`. See BUILD_ANDROID.md. ABI-specific debug APKs are produced under android/app/build/outputs/apk/debug/.

## Demo sequence

1. Choose the actual crop and language; take/import a clear photo of one leaf.
2. Show the predicted condition and score, or the low-confidence/crop-mismatch explanation.
3. Answer symptom questions and play general guidance in the selected language.
4. Save and reopen the observation from History.
5. Show that a mouse/object photo requests a leaf photo and produces no disease label.
6. Demonstrate offline operation after required browser assets are cached, or with the installed native APK.

## Executed verification

- Python ML unit tests: 25 passed.
- Web policy/leaf-gate fixtures: 31 passed; fixture outputs are explicitly synthetic and are not accuracy evidence.
- Android domain/leaf-gate unit tests: 32 passed.
- Actual native mouse/leaf integration: 2 passed; actual ONNX output and gate behavior verified.
- Actual browser mouse/laptop rejection and healthy/field-leaf inference passed with no page errors.
- Android debug/test APK builds and TypeScript/Vite production build passed.

Physical ARM-phone RAM/latency and native-speaker language review remain pending. Current model metrics, training data/protocols and failed experiments are linked from the root README. Historical planning/presentation documents describe earlier milestones and must not override current model receipts.
