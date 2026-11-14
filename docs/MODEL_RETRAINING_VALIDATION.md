# Current field upgrade

The current shipped architecture is MobileNetV3-Large, replacing V4 after TRAIN/TUNE selection and frozen evaluation. Source accuracy92.11%; reused80-photo field benchmark38.75% versus V4 22.5%. Field accuracy remains limited. Exact current evidence is in [field_upgrade_v3](../ml/reports/field_upgrade_v3/) and the canonical model card. Historical V4 evidence below does not describe the current model.

# Retrained MobileNetV4 — executed evidence

The previous small-subset model and unconditional unvalidated gate caused every scan to remain uncertain. The replacement was trained on the full source TRAIN partition and continued on a separate mixed source/field TRAIN pool. Selection used TUNE only; temperature/gates used CAL, then the exact exported graph and frozen policy were evaluated once on the original full source test and separate external field-like test.

The final source test scored 94.67% accuracy / 0.9401 macro F1. Accepted precision was 96.92% at 92.81% coverage. External field-like accuracy was only 22.5%, with 30.77% accepted precision at 32.5% coverage. These domains are never pooled; the model remains unsuitable for reliable field diagnosis.

Source-qualified matches are separate from field validation. Android and web check model SHA, sidecar SHA, model/version binding, frozen temperature/class gates and 960-dimensional normalized centroids. Global 17-class scores are checked before crop consistency. Missing qualification stays uncertain; corrupt claimed evidence fails model loading. Field validation and chemical/condition-specific advice remain false.

Executed checks: 25 Python ML tests, 25 Android domain tests, 25 web policy fixtures; TypeScript and native debug/test-APK production compilation passed. Policy fixture tests use explicit synthetic runtime stubs and are not recognition evidence. ONNX checker and zero/nonzero PyTorch parity passed with maximum absolute error 4.30e-6. Physical ARM-phone latency/RAM are not measured. Actual device/runtime follow-up evidence is recorded separately when completed.

Canonical exact-artifact evidence: [model card](../models/assets/model/MODEL_CARD.md), [source and external evaluation](../models/assets/model/source_evaluation.json), [training/protocol receipts](../ml/reports/review2_full/). Historical limited runs remain under their original report directories; their scores do not describe this replacement.
