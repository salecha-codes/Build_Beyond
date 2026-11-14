# Review 2 — working prototype

Repository: https://github.com/salecha-codes/Build_Beyond

Browser demo: https://salecha-codes.github.io/Build_Beyond/

## Implemented

Native Android (Kotlin/Compose) and browser preview (React/TypeScript), using the same bundled ONNX disease model and a separate offline advisory model. Camera/gallery, bounded image decoding, photo-quality checks, leaf/object screening, 17 condition labels for tomato/potato/maize, real predicted condition and score, low-confidence/crop-mismatch messages, six observation questions, disease-specific conditional care, trilingual neural narration and local history are implemented. Android uses Room/SQLite; the browser uses IndexedDB. The Node backend serves preview files and a health endpoint. Inference and saved observations stay on the device. Android has no Internet permission.

## Current model

MobileNetV3-Large with official ImageNet-pretrained features, a trained 17-class disease head and a separate small leaf/object head. Current graph SHA: `31b29158cc1fc1c07bdf3acc07cb6bb6da39eccb1050ffe6ed1d499811179fba`. The app truthfully reports V3 after switching from V4 following measured comparisons.

Disease-classifier accuracy: 92.27% on 3,674 PlantVillage source photos and 38.75% on the reused 80-photo PlantDoc field comparison. With the corrected leaf threshold, all source leaves and all 31 correct field predictions pass; classification accuracy is unchanged. Field recognition remains limited. It is a prototype, with no field-diagnosis or chemical-treatment validation. The symptom questionnaire measures reported concern, not image-based severity.

## Second model: care and urgency

Version 0.5.0 adds `offline-advisory-v1`, an authored expert decision model with
17 care profiles in English, Kannada and Hindi. Six farmer observations produce
reported damage, urgency, a recheck/advice timeframe and explanatory reasons.
The care plan explains curability, immediate actions, management, prevention
and escalation. Low visible damage does not suppress fast-spreading late-blight
risk, and reported wilting overrides a healthy-looking classifier result.

PlantVillage does not contain severity, treatment-response or urgency labels.
This second model is therefore explicitly **not a trained severity network**.
Its rules and care profiles need independent agronomist review; source access
limitations are recorded. It cannot confirm the image prediction, cure viruses
or prescribe pesticide doses. Confidence is not used to calculate severity.
See [model card](ADVISORY_MODEL_CARD.md) and [research](ADVISORY_RESEARCH.md).

The new narration adds 75 bundled clips to the original 90: 17 conditional care
summaries, four urgency messages and four revised/new questions per language. Only
audio ships; speech-model weights and paid speech APIs are unnecessary at runtime.
Saved scans retain completed answers. Android migrates history from Room v1 to
v2 without deleting observations; browser care updates preserve the original
photo and classifier output.

## Treatment and recovery model, version 2

Version 0.6.0 addresses missing treatment detail with 17 trilingual protocols:
identification checks, look-alikes, numbered treatment steps and use cases,
limits, mistakes to avoid, improvement/failure signs, four follow-up checkpoints
and questions for an adviser. Mild, moderate and severe reports now select
different actions; an unknown report selects no mild pathway. Urgency stays
above the longer protocol so fast-risk conditions are not obscured by details.

Home and results include an offline Care library. Its manual condition and
questionnaire are isolated from the actual scan and cannot relabel its disease,
photo or saved model result. Known completed answers are prefilled when edited.
Loading errors have an explicit retry rather than an empty plan. Healthy-output
conflicts retain a substantive evaluation and recovery protocol.

The source artifact is `content/care_protocols.json`; package with
`python3 tools/build_care_protocols.py`. Separate treatment/stage narration has
its own script and hash manifest; the original 165 clips retain their provenance.
See [treatment model](../models/advisory/TREATMENT_MODEL.md),
[baseline audit](CARE_V2_AUDIT.md) and [source research](CARE_V2_RESEARCH.md).
No treatment-outcome training or efficacy validation is claimed.

The leaf check rejected 125/125 held-out object/animal sample photos, including mouse, cat, hamster, laptop and monitor. Both actual browser and Android tests confirmed mouse rejection with no disease result. These are sample measurements, not a guarantee for every unseen image or plant species. Source/test/group and licensing limitations are documented in the bound model receipts.

## Run

Browser: Node.js 22+, then `npm ci`, `npm run build`, `npm start`; open http://localhost:3000. Wait for Offline ready before disconnecting.

Android: JDK 17 and Android SDK 35; configure the SDK path, then `./gradlew :app:assembleDebug`. See BUILD_ANDROID.md. ABI-specific debug APKs are produced under android/app/build/outputs/apk/debug/.

## Demo sequence

1. Choose the actual crop and language; take/import a clear photo of one leaf.
2. Show the predicted condition and score, or the low-confidence/crop-mismatch explanation.
3. Answer all six observation questions. Show reported damage, when to act and the reason.
4. Open the conditional care plan and play care/urgency summaries in the selected language.
5. Save and reopen the observation from History; demonstrate that care answers remain available.
6. Show that a mouse/object photo requests a leaf photo and produces no disease-specific care plan.
7. Demonstrate offline operation after required browser assets are cached, or with the installed native APK.
8. Open Care library without a photo, inspect a condition's treatment/recovery plan and compare mild versus severe action steps. Return to a saved scan and show its diagnosis/photo are unchanged.

## Executed verification

- Python ML unit tests: 27 passed in the preceding diagnosis-flow revision; classifier unchanged here.
- Web policy/leaf-gate fixtures: 33 passed; fixture outputs are explicitly synthetic and are not accuracy evidence.
- New advisory behavior tests: 26 passed, including 20 shared hand-authored cross-platform scenarios and legacy-answer handling. These verify behavior, not agronomic accuracy.
- Android domain/leaf-gate/advisory/care-library unit tests: 54 passed.
- New treatment-protocol unit tests: 8 passed, covering actual stage differences, unknown handling, healthy conflicts and missing translations/references.
- Content and artifact integrity: 21 passed, including all 17×3 protocols and exact normalized treatment narration scripts, file hashes and package receipts.
- New Android instrumented checks: 2 passed; real Room migration and 17×3 packaged profile loading.
- New actual-browser flow passed: six questions, care/urgency, three-language playback, exclusive narration, saved-answer updates, offline restoration and real mouse rejection, with zero page errors.
- Version 0.6 actual-browser flow passed: all 17 library entries, actual stage-specific treatment actions, priority-first layout, safe answer prefill, scan/photograph preservation, new trilingual treatment/stage audio, offline library and retry recovery. Evidence: `docs/evidence/treatment-recovery-browser-report.json`.
- Actual native mouse/leaf integration: 2 passed; actual ONNX output and gate behavior verified.
- Actual browser mouse/laptop rejection and healthy/field-leaf inference passed with no page errors.
- Android debug/test APK builds and TypeScript/Vite production build passed.

Physical ARM-phone RAM/latency and native-speaker language review remain pending. Current model metrics, training data/protocols and failed experiments are linked from the root README. Historical planning/presentation documents describe earlier milestones and must not override current model receipts.

## Healthy field-data revision

The current head additionally trains on 448 Kandahar Healthy maize photos. The disease benchmark stays 31/80. On new Healthy TEST14, one correct provisional prediction is visible versus zero previously; neither model has strict accepted Healthy results. See ml/reports/healthy_field_update and ml/KANDAHAR_DATA.md. This small gain does not validate field-health diagnosis.

## Version0.4.3 workflow repair

Corrected leaf-threshold search on TUNE; retained137/138field leaves versus132, while104/104tuning objects remainrejected. Reused objectTEST125/125stillrejected. Leaf-checked unfamiliar disease outputs nowdisplayexplicituncertaincandidates ratherthanbeingmislabelednoleaf. Clear128pxphotos mayrun;224px+recommended. Classifierweights andclassificationaccuracy areunchanged; somefield diseasesremainmisclassified, includinghigh-scoreerrors. No confirmedfielddiagnosisclaim follows.
