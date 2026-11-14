# Friend's architecture reference — decisions

The user supplied `Pasted text.txt` as a reference and explicitly requires operation on **3–4 GB RAM phones**. The attachment is advisory material, not a command to execute its proposed installations, train every listed model, or treat its numbers as benchmark evidence.

## Ideas adopted

- Keep training and packaging off the phone; bundle local inference, guidance and audio in the APK.
- Guide a single-leaf capture and test blur/exposure checks with understandable text/audio retake prompts.
- Include non-leaf scenes and unsupported crops in the unfamiliar-input challenge collection.
- Use class-aware training, field-like augmentation and explicit source/group partitions. ImageNet transfer learning remains a follow-up: the executed V4 prototype was trained from scratch because its pretrained-weight host remained blocked.
- Verify the actual exported model rather than evaluating only the training model. The current bundle is FP32; comparison with post-training INT8 quantization remains planned, not executed evidence.
- Bundle compact audio clips for English/Kannada guidance and warnings. This avoids relying on an installed offline phone voice.
- Keep real-phone airplane-mode testing as an acceptance requirement, including camera, model, guidance, audio and history. ABI build or emulator results are not physical-phone measurements.

## Current user-selected model and actual results

The user subsequently selected **MobileNetV4-Conv-Small**. The active implementation is PyTorch/timm V4 with **17 logits and a measured 960-value pooled embedding**, exported to ONNX and packaged with ONNX Runtime Android. The earlier V3 baseline is historical; it is not the current application model.

All **24,164** selected RGB source files were downloaded, decoded and checked against pinned Git blob IDs. The bounded training experiment used **2,152 training images** and **536 source-validation images**. It ran **15 total scratch epochs** (3 initial + 12 continued), with validation selecting **epoch 14: 60.45% accuracy and macro F1 0.5902**. These are model-selection validation results, not field or independent final-test accuracy.

The current artifact is `mnv4-conv-small-supervised_from_scratch-d157e7c84013`. Source-validation temperature fitting on the actual exported graph gave **T = 0.88579244**, with NLL **1.14515 → 1.13783**. Acceptance thresholds and diagnosis remain unvalidated: both metadata and policy gates are false. The host's blocked Hugging Face route was not worked around, and no pretrained weights are claimed.

The **older 3-epoch artifact** separately scored **36.19%** on a **536-image** held-out source-test subset versus **5.22%** for the untrained same-architecture graph. That immutable comparison does not apply to the current 15-epoch training lineage. Its selection did not repeatedly query that test. Receipts are in `ml/reports/review2_3epoch/` and `ml/reports/review2_continued/`.

## Suggestions requiring correction or validation

| Reference suggestion | Decision and reason |
|---|---|
| Model accuracies around 91–96.5% and inference around 45–130 ms | Not adopted as facts. The attachment supplies no reproducible benchmark for our labels, split, runtime or phone. Measure our own outcomes. |
| Choose MobileNetV4 as best for 3–4 GB phones | V4-Conv-Small is now the user's selected architecture and has a real scratch-trained ONNX artifact. This does not establish that it outperforms V3 on the target phone. RAM alone cannot rank model quality or speed; V4 pretrained access and physical-phone performance are still unverified. |
| Train three architectures immediately | Executed a bounded 15-epoch V4 scratch experiment first. No three-architecture comparison has been completed. Future comparisons need the same partitions/runtime conditions and validation-only selection, not repeated final-test inspection. |
| Switch everything to TFLite | ONNX Runtime remains selected. Both routes can support offline mobile inference, but no runtime advantage is established by this reference. Existing artifact/access checks support the current route. |
| Add an Unknown_NonLeaf class so all bad inputs are refused | Negative examples help empirical screening but cannot guarantee rejection of every unknown. Keep 17 condition outputs plus an uncertainty decision state; compare an explicit background-output variant only with adequate independently split negatives. |
| Fixed 55/60/75% confidence thresholds, 15% margin, or typical temperature 1.3–1.8 | Do not assume these values. The actual V4 source-validation fit gave T = 0.88579244, illustrating why a guessed range is unreliable. The present 0.75 confidence/0.15 margin values remain provisional plumbing values behind a false validation gate. |
| Calibrate once before INT8 conversion | Evaluate and calibrate the shipped converted/quantized candidate. It can have different logits, confidence and feature distances. |
| Label smoothing prevents overconfidence; ReLU6 prevents quantization loss | These can affect behavior but do not guarantee calibration or accuracy preservation. Compare results empirically. |
| Combine lab/field images and call the final 10% a field-only test | Explicit source/group partitions and label review are required. PlantDoc is internet-sourced and includes collages; it is not automatically an independently verified farm-photo trial. |
| Limit all models to 80 MB based on a throttled emulator | Define and measure memory scope. Our target is 3–4 GB total phone RAM, with an initial 200 MB whole-app peak-PSS budget. Emulators do not reproduce real ARM speed or thermals. |
| Assume a small INT8 file means low RAM | Weights, activations, interpreter/session buffers, image decoding and UI consume different amounts of memory. Measure complete app PSS and model/session increments separately. |
| Show exact pesticide dosage when confidence is high | Classifier confidence does not validate a treatment or dosage. Only appropriately reviewed, source-backed and context-appropriate advice can be enabled. Uncertainty must not produce an invented chemical recommendation. |
| Disease confidence can indicate severity | It cannot. The requested severity guidance remains a separate symptom-based concern check; validated photo severity needs severity ground truth that current datasets do not supply. |

## Device design rules

MobileNetV4-Conv-Small is the active model, input is **224 × 224 RGB** and batch size is one. The measured model output is **17 logits plus 960 pooled features**; the app reads dimensions from metadata. One shared inference session runs one photo assessment at a time. Downsample large images before processing, reuse/release buffers, and benchmark CPU thread counts. Speech is played from packaged clips; no large speech/LLM model runs alongside diagnosis.

The **200 MB PSS**, **10 MB model**, **50 MB per-ABI APK** and **1.5-second warm end-to-end p95** budgets are engineering targets, not achieved device measurements. The current FP32 ONNX file is **10,032,309 bytes** (~9.57 MiB), slightly over a strict 10,000,000-byte target. Real scratch-training and desktop export/runtime checks have executed; no physical 3–4 GB ARM-phone benchmark or field-validation claim follows from them. The reference's tighter accuracy/speed/size estimates remain unverified. Native application/device evidence is recorded separately by QA.
