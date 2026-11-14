# Historical evaluation and release-planning checklist

This document is an early planning checklist, not the current model card or status report. The project now has a trained MobileNetV3-Large model and recorded evaluations. For current artifacts and measured results, see [the model card](../models/assets/model/MODEL_CARD.md), [model retraining validation](MODEL_RETRAINING_VALIDATION.md), and [the root README](../README.md). The targets below remain planning criteria unless a current receipt explicitly records a measurement.

## Data integrity

Freeze source commits and manifests. Split by the union of known leaf groups and confirmed duplicate clusters, not filenames alone. Preserve unresolved grouping information. Use an approximate 70/15/15 class-stratified group split with explicit final counts. Tiny classes receive group-aware treatment; report wide uncertainty rather than enlarging test sets through related-image leakage.

Perform training-only augmentation. Fit preprocessing statistics, class centroids, quantization calibration, temperature and thresholds using their permitted train/validation partitions only. A locked test result must not be used to tune a threshold or choose a model. If the test is used during development, acknowledge it and obtain a fresh holdout.

## Required comparisons

1. ImageNet frozen-backbone classification head baseline.
2. Fine-tuned compact model on the identical split.
3. Source-only versus reviewed external-domain fine-tuning, where data supports it.
4. FP32 PyTorch versus exported FP32 ONNX parity.
5. Exported FP32 versus QDQ quantized model.
6. Always-predict results versus uncertainty-gated results, reporting retained coverage.

## Model metrics

Report per-class support, precision, recall and F1; macro F1; balanced accuracy; and confusion matrices. Provide overall accuracy as a secondary metric. For each crop, report healthy-class false positives and disease-to-healthy mistakes. Never hide a weak class in a crop aggregate.

For confidence, report temperature fitting, NLL, 15-bin ECE, a reliability diagram, and accepted-prediction accuracy versus acceptance coverage. Preserve per-bin counts, accuracy and mean confidence so diagrams are reproducible from the receipt. Report precision, recall, F1 and support per class; include the confusion matrix. For unfamiliar-input rejection, report the challenge-set composition, false-acceptance rate, false rejection of supported images and examples of failure. Confidence and embedding gates do not establish complete unknown detection.

The active V3 evaluation receipt records temperature fitting, NLL, ECE and per-class evaluation, but predates retained reliability-bin counts. Its reliability diagram cannot be reconstructed from the aggregate ECE alone; rerun exact-artifact qualification with the current reporter before publishing a diagram. All such results must identify their data domain. They do not establish field-diagnosis validation.

External evaluation is separate from internal source test results. The ten candidate PlantDoc disease matches provide just 85 official test images before cleaning; do not combine them with internal tests to advertise a single general field-accuracy number. Classes without external coverage must be identified. Bootstrap intervals should resample independent groups when feasible, not related images.

## Preprocessing and runtime checks

Use the same fixed image fixtures on Python and Android. Test orientation, RGB order, resize/letterbox, padding, normalization, label order, logits and final decision behavior. Compare continuous outputs within declared tolerances; quantization needs its own accuracy comparison, not equality to floating-point logits.

On a real **3–4 GB RAM Android phone**, measure first session load, cold inference, at least 30 warm inferences, p50/p95 latency, peak memory, APK/model size and repeated-use behavior. Keep preprocessing and inference timings separate and report end-to-end time too. A desktop result is not a phone benchmark. Check that repeated inference does not leak resources. Record chipset, ABI, Android version, RAM and test conditions. A RAM-limited emulator can test UI and resource handling, but does not establish ARM inference speed or thermal behavior. If only a 4 GB phone is measured, do not claim a 3 GB phone was validated.

Engineering targets: packaged model at most 10 MB, per-ABI APK at most 50 MB, whole-app peak PSS at most 200 MB during the defined capture/assessment/audio journey, warm end-to-end p95 at most 1.5 seconds, and no crashes/OOM in the defined repeated-use test. Measure PSS with Android memory tooling, including the camera, UI, native inference session and images; a model's file size is not its runtime memory. Device results may require optimization; these goals are not achieved measurements or compatibility promises for an unspecified phone.

## App acceptance scenarios

- Fresh launch after installation in airplane mode, without prior app model/voice downloads.
- Camera scan, gallery scan, language switch, guidance and audio playback without network.
- Restart and observation/history recovery.
- Permission denial/cancellation, rotated and very large images, malformed input and missing/corrupt assets.
- Poor photo → understandable retake; crop mismatch → crop correction; low confidence → uncertainty path.
- Healthy-looking result wording and unavailable/unvalidated-condition behavior.
- Delete an observation and verify its owned image is deleted.
- Export an observation only through explicit user action.

## Content acceptance

Every enabled advice card must match its condition, cite an inspected primary source, carry a version, and have checked English/Kannada text and audio. Automated translation or backtranslation alone is not evidence of native-speaker review. Record the review level honestly. Advice must not imply an exact treatment or dosage can be determined from a classifier score alone.

## Shipping decision

Choose the simplest model meeting the observed constraints. A quantized model should normally lose no more than one percentage point of macro F1 on the internal validation comparison and should improve a measured resource constraint; external behavior is checked separately. If it fails, ship the already-validated compact FP32 model. Enable condition-specific advice only where the class has adequate validation and content verification. Report unvalidated classes explicitly.

Release deliverables: model card, data/split manifest, reproducible metrics, source and dependency credits, build checksums, actual phone measurements and an airplane-mode demonstration recording. Nothing in Review 1 should describe planned results as achieved.
