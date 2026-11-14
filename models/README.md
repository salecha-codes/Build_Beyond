# Shared crop model assets

`assets/model/` is the canonical bundle used by both the Android app and the browser prototype. Android adds `models/assets` as an assets source directory, preserving runtime paths such as `model/crop_model.onnx`. The web build serves the same files at `<BASE_URL>assets/model/`. Do not keep a second model copy in either application source tree.

The selected release uses **MobileNetV3-Large**, initialized with official torchvision ImageNet weights, with a trained17-class linear head. TRAIN-fitted feature standardization is embedded in the graph. The model still outputs17logits and960pooled features from224×224RGB images. It replaces the from-scratch V4 prototype because field benchmark accuracy improved22.5%→38.75%; source accuracy is92.11%. Read [metadata](assets/model/model_metadata.json), [the model card](assets/model/MODEL_CARD.md), and [current receipts](../ml/reports/field_upgrade_v3/). The field benchmark was reused from the V4 comparison and remains small.

`source_evaluation.json` records the exact model's frozen-calibration policy and independent source-test outcome; `embedding_centroids.json` contains normalized training-only class features. Both applications verify those sidecars' SHA, model/version binding and frozen per-class thresholds before allowing a source-tested likely condition or healthy-looking result. Low score, ambiguity, disabled classes and excessive feature distance remain uncertain. All scores are normalized globally over 17 classes before the selected crop is checked.

Source acceptance is separate from field diagnosis: `validated` / `diagnosis_validated` remain false. Accepted prototype results display the actual condition and model-match score, with general observation guidance. A separate `allow_condition_specific_advice` flag controls condition-specific advice; source qualification does not enable it. The source test and the small PlantDoc field-like test are reported separately, never pooled into one accuracy claim.

Training data was acquired from PlantVillage RGB at Git commit `7f7ecc7e1eaca78107e3affe7cb5abd9427e139a`, with Git-blob verification, decoded-file checks and group-aware splits. See [`ml/README.md`](../ml/README.md) for acquisition, source licensing/provenance, split limitations and commands. Data, Python environments, training checkpoints and raw downloads stay outside this repository.

Use `python tools/sync_model_bundle.py /path/to/exported/bundle` from the repository root to update all shared files after verifying the bundle. This installer validates model/evidence checksums, labels, versions and the frozen policy before replacement. The Android package and web asset sync copy the same sidecars.

## Preprocessing

The model consumes RGB float32 NCHW `[1,3,224,224]`. Resizing uses half-up letterbox dimensions, `[124,116,104]` padding, and the Pillow antialiased bilinear 22-bit separable filter before ImageNet normalization. The Android helper and browser `preprocessRgb` port use the same convention, including rounding after each resize axis. Independent golden image/tensor fixtures live in [`contracts/fixtures/`](../contracts/fixtures/).

The browser uses `createImageBitmap` to apply EXIF orientation once and caps working images at 1024 px. Browser codec/large-image downsampling can differ from Android camera decoding; exact tensor parity is specified from identical decoded RGB input. ONNX Runtime's WASM/glue files are bundled locally. First load needs the static assets; offline reload depends on the application's service worker/cache, rather than a remote inference service.

## Leaf validation sidecar

The current graph adds leaf_logit[1,1]. metadata.leaf_gate names its frozen probability threshold and hash-bound leaf_validation.json receipt. Both clients validate that receipt before enabling the gate; a negative input produces no disease candidates. Read ml/reports/leaf_guard for negative testing and source/field leaf-recall impact.
