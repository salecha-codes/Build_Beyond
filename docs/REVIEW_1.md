# Review 1 — ideation presentation

Presentation wording below describes the planned system. Replace future-tense claims with achieved results only when corresponding evidence exists.

## Slide 1 — The problem

**A farmer's crop-health decision should not stop when the internet does.**

Farmers using budget Android phones need help interpreting leaf symptoms and understanding practical next steps. Poor connectivity, unsuitable photos and unfamiliar terminology complicate that task.

Speaker note: use a concrete scenario—a farmer notices damage on a tomato leaf and has weak mobile connectivity. Avoid unsourced crop-loss statistics.

## Slide 2 — The proposed experience

**Select crop → photograph leaf → receive a local assessment → hear the next steps.**

- Three crops: tomato, potato, maize.
- English/Kannada text and bundled audio.
- Specific retake instructions when photo quality is poor.
- An explicit uncertain outcome when the app cannot assess reliably.
- Local history and an observation card to share with a trusted expert.

Speaker note: emphasize the complete flow, including what happens when a confident diagnosis is not justified.

## Slide 3 — Technical architecture

Development: audited datasets → compact transfer-learning model → ONNX export → evaluation and calibration → APK assets.

Phone: CameraX/gallery → image preparation → ONNX Runtime CPU → decision policy → local guidance/audio/history.

There is no runtime inference server. The app packages its model, runtime, text and audio. Android 7+ is the selected runtime baseline; actual device performance will be measured.

## Slide 4 — Data and feasibility evidence

- Inventoried **24,164 selected RGB files**: 18,160 tomato, 2,152 potato, 3,852 maize.
- **17 crop-condition categories** are available, including healthy classes and a pest category.
- Downloaded and decoded **79 sample images** and visually reviewed the contact sheets.
- Found class imbalance and exact duplicates; only part of the supplied leaf-group map can be matched unambiguously.
- Verified an accessible pretrained-weight source and inspected the Android runtime package for platform/ABI support.

Speaker note: these are completed research checks. Do not imply a full pixel audit, trained accuracy or successful APK installation.

## Slide 5 — What differentiates our implementation

**Reliable offline behavior and honest uncertainty are the features we will test.**

- Guided capture before inference.
- Measured confidence and empirical rejection of unfamiliar inputs.
- Regional-language audio that does not depend on downloaded voices.
- Evaluation beyond controlled source images.
- Actual model-size, latency and memory results on an Android phone.

Speaker note: crop-diagnosis apps already exist. We are not claiming a new category or guaranteed disease recognition. Our differentiation is a measurable implementation hypothesis.

## Slide 6 — How success will be measured

- Per-class precision, recall, F1 and healthy/diseased confusion.
- Separate external-image results with explicit compatible labels.
- Accuracy among accepted predictions together with acceptance coverage.
- Failures and rejection behavior on an unfamiliar-input challenge set.
- Installed airplane-mode demonstration, including audio.
- Actual phone latency, memory, model size and APK size.

Remaining validation: complete ingestion, model training, content/translation review and phone benchmarks. Engineering goals are not achieved measurements.

## 60-second pitch

> We are building an offline crop-health assistant for farmers with budget Android phones. The farmer selects tomato, potato or maize and photographs a leaf. The app checks photo quality, runs a compact model directly on the device, and explains the likely condition and next steps in English or Kannada, including offline audio. If the image is unsuitable or the model is uncertain, it asks for a better photo or suggests expert follow-up. We have inventoried over 24,000 relevant source images, reviewed image samples and verified the Android runtime route. We will evaluate individual conditions, varied images, uncertainty handling and real phone performance. Our final demonstration will run in airplane mode, with the model and guidance already packaged in the app.

## Likely judge questions

**Why these crops?** They have relevant labeled source data and overlapping external-image coverage. The exact class audit is available; crop selection is data-driven rather than arbitrary.

**Why not just use an online vision API?** The stated user needs an offline experience. We train outside the phone and deploy a compact model for local execution.

**What is new compared with existing apps?** We do not claim offline diagnosis itself is new. We aim to demonstrate a focused combination of capture assistance, measured uncertainty, regional audio and transparent phone/external-image evaluation.

**How accurate is it?** No trained result exists at ideation. We will report per-class and external results separately; a controlled source-image score will not be presented as field accuracy.

**How do you prevent wrong advice?** We use explicit unsupported/uncertain states, validation-derived gates and source-traceable guidance. These reduce some risks but do not guarantee correctness. Unvalidated conditions do not get enabled disease-specific advice.

**Can it run on a cheap phone?** The selected runtime supports Android 7+ and 32-/64-bit ARM CPUs; the package was inspected. Actual memory and latency still require measurement on the available phone.

**How does voice work offline?** Guidance audio is generated and checked during development, then bundled in the APK. No installed phone voice or live speech service is required.

**What if the farmer photographs the wrong crop or a non-leaf?** Selected-crop consistency, photo checks and empirical uncertainty gates lead to correction/uncertain states. We will measure unfamiliar-input failures rather than promise universal rejection.
