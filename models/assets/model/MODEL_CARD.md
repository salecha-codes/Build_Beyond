# MobileNetV3-Large field prototype

This release uses official ImageNet-pretrained torchvision MobileNetV3-Large visual features and a TRAIN-only fitted 17-class linear head. Feature standardization fitted on TRAIN is embedded in ONNX. It replaces the weaker from-scratch MobileNetV4 model following tuning-only candidate selection.

## Exact artifact

Model: `mnv3-large-imagenet-v2-field-head-9f330bb88adf`. ONNX SHA-256: `9f330bb88adffa64460c4e84faf808529a1a1fdc667977766f648cb28b51fa63`. Size: 11,950,683 bytes. Inputs: RGB FP32 NCHW224×224, identical letterbox/ImageNet normalization contract. Outputs:17 logits and960 pooled visual features. Both apps verify the actual graph and bound evaluation/centroid sidecars.

## Frozen evaluation

| Domain | Images | Raw accuracy | Accepted precision | Coverage |
|---|---:|---:|---:|---:|
| PlantVillage source | 3674 | 92.11% | 96.47% | 87.02% |
| PlantDoc external field-like | 80 | 38.75% | 50.00% | 47.50% |

Field accuracy improves from V4's22.50% to38.75% on the same80-photo comparison benchmark (+16.25percentage points). This set was already evaluated for V4; it is a reused comparison benchmark, not newly blind independent data. New model selection used TRAIN/TUNE only; CAL fitted gates, and the frozen candidate was evaluated once. Source macro F1 0.9087.

Field performance remains poor. The model is a prototype and does not establish reliable farmer-photo diagnosis. External labels are mostly unreviewed and80images is small. No chemical prescriptions are enabled. `diagnosis_validated=false` and `allow_condition_specific_advice=false` remain explicit. Low-confidence results display a real predicted condition with uncertainty; crop mismatch retains selected/predicted crop comparison. Scores are model outputs, not field accuracy.

## Training/data scope

A frozen pretrained backbone and17-class head used the audited source TRAIN cap400/class plus632PlantDoc TRAIN photos. Exact counts, weighting, selected iteration and official weight SHA are in training_receipt.json/export receipts. Source TUNE2228 and field TUNE138 selected the candidate. Source CAL1392+field CAL137 fit temperature, score/margin and training-centroid distance gates. Source full TEST3674 and external80 were not used to train or choose the candidate. Historical exposure and source physical-leaf grouping limits remain in the evaluation receipt.

Deployment remains entirely offline: the pretrained teacher weights and training tools are not required by the phone. ONNX checker and zero/nonzero/real-photo PyTorch parity passed. Actual ARM-phone latency and peak RAM have not been measured. See source_evaluation.json for full errors/support/intervals and protocol identities.
