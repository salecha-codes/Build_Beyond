# MobileNetV4 offline crop classifier — Review 2

This is a trained, executable MobileNetV4-Conv-Small prototype, initialized from scratch and continued on full PlantVillage training data plus a smaller PlantDoc training partition. It is not an untrained placeholder.

## Exact artifact

- Model version: `mnv4-conv-small-supervised_from_scratch_mixed_domain_continuation-4a0c82796188`
- ONNX SHA-256: `4a0c82796188dce8c81d3840ec2817ee27cf29e9c148eeeefeb90662aa888b03`
- Size: 10,032,309 bytes; FP32, 17 classes, 960 pooled features, 224 × 224 RGB input.
- Selected checkpoint lineage epoch: 37. New work ran 12 full-source epochs and 12 mixed-domain epochs, with checkpoint selection on tuning partitions only. Earlier bounded training is preserved in receipts.

## Measured results — keep domains separate

| Frozen final test | Images | Raw accuracy | Accepted precision | Coverage |
|---|---:|---:|---:|---:|
| PlantVillage source domain | 3674 | 94.67% | 96.92% | 92.81% |
| PlantDoc external field-like photos | 80 | 22.50% | 30.77% | 32.50% |

Source all-class macro F1: 0.9401. Field performance is poor: this model is not ready for reliable farmer-photo diagnosis. Source acceptance is not a field-accuracy guarantee. PlantDoc labels are mostly unreviewed and the 80-image external set is small.

## What the app does

Both Android and browser verify the actual ONNX bytes and the bound evaluation/centroid sidecars. Source qualification passed the declared source-test criteria. High-scoring matches that pass frozen per-class confidence, margin and feature-distance gates can show a likely condition or healthy-looking result; ambiguous, disabled or rejected unfamiliar inputs remain uncertain. Scores are globally normalized over all 17 classes, then checked against the selected crop.

`diagnosis_validated=false`, `validated=false` and `allow_condition_specific_advice=false` remain unchanged. Accepted results are dataset-tested estimates, not confirmed diagnoses or chemical prescriptions. General observation guidance and user-reported symptom concern remain separate from classifier output. The centroid heuristic is not a validated unknown-image detector.

## Data and evaluation boundaries

PlantVillage: 16,856 TRAIN, 2,228 tuning, 1,392 CAL, 3,674 final source test. PlantDoc: 632 TRAIN, 138 tuning, 137 CAL, 80 eligible original external-test images. Temperature and acceptance gates used CAL only; normalized centroids used 17,488 TRAIN images. Model selection did not use these final test results. Historical source-test inspection for an earlier artifact and eight rare-class CAL images previously used for historical selection are disclosed in the protocol receipt; complete physical-leaf independence is not established.

Natural field photos differ substantially from isolated-leaf source images. More curated local field photos, better generalization and agricultural review are required before field use. See `source_evaluation.json` for per-class support, errors, intervals, protocol hashes and full domain-specific reports.

## Runtime evidence

ONNX checker and zero/nonzero PyTorch parity passed (maximum absolute difference 4.29e-06). Desktop CPU export microbenchmark p50 1.03 ms; this is not a physical-phone benchmark. Android and browser use the same bundled graph. Physical ARM-phone latency/RAM measurements remain pending.
