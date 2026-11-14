# Shared crop model assets

`assets/model/` is the canonical six-file bundle used by both the Android app and the browser prototype. Android adds `models/assets` as an assets source directory, preserving runtime paths such as `model/crop_model.onnx`. The web build serves the same files at `<BASE_URL>assets/model/`. Do not keep a second model copy in either application source tree.

The actual model is MobileNetV4-Conv-Small (`timm` name `mobilenetv4_conv_small.e2400_r224_in1k`), exported as ONNX opset 17/IR 8, with 17 logits and a 960-dimensional pooled embedding. It was trained from scratch; pretrained weights were not available. The 10,032,309-byte model SHA-256 is:

```
d157e7c8401319a700039de467caba6728b7bdbf35b4cdae1818757cf0ba7e3c
```

Its version is `mnv4-conv-small-supervised_from_scratch-d157e7c84013`. Model metadata and the acceptance policy both retain `validated: false` / `diagnosis_validated: false`. Real model scores are visible as prototype evidence; they must not be presented as a confirmed disease or validated probabilities. The browser checks the model byte length, SHA-256, model/policy versions and the stable 17-label mapping before creating an ONNX Runtime Web CPU WASM session.

The selected epoch 14 checkpoint follows 15 source-domain epochs (3 initial +12 continued), with 2,152 training images and 536 model-selection validation images. Source-validation accuracy 60.45% and macro F1 0.5902 are not independent test or field results. The older 3-epoch model has its own test receipt and those results do not describe this bundle. Provenance and export/calibration receipts are in [`ml/reports/review2_continued/`](../ml/reports/review2_continued/) and [the bundled model card](assets/model/MODEL_CARD.md).

Training data was acquired from PlantVillage RGB at Git commit `7f7ecc7e1eaca78107e3affe7cb5abd9427e139a`, with Git-blob verification, decoded-file checks and group-aware splits. See [`ml/README.md`](../ml/README.md) for acquisition, source licensing/provenance, split limitations and commands. Data, Python environments, training checkpoints and raw downloads stay outside this repository.

Use `python tools/sync_model_bundle.py /path/to/exported/bundle` from the repository root to update all shared files after verifying the bundle. This installer validates the checksum and label/version contract before replacement.

## Preprocessing

The model consumes RGB float32 NCHW `[1,3,224,224]`. Resizing uses half-up letterbox dimensions, `[124,116,104]` padding, and the Pillow antialiased bilinear 22-bit separable filter before ImageNet normalization. The Android helper and browser `preprocessRgb` port use the same convention, including rounding after each resize axis. Independent golden image/tensor fixtures live in [`contracts/fixtures/`](../contracts/fixtures/).

The browser uses `createImageBitmap` to apply EXIF orientation once and caps working images at 1024 px. Browser codec/large-image downsampling can differ from Android camera decoding; exact tensor parity is specified from identical decoded RGB input. ONNX Runtime's WASM/glue files are bundled locally. First load needs the static assets; offline reload depends on the application's service worker/cache, rather than a remote inference service.
