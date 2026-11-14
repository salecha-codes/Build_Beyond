# Field recognition upgrade

The deployed model is now MobileNetV3-Large with official ImageNet-pretrained features and a TRAIN-only trained17-class head. The best V4-only adaptation trials failed their tuning gates; none was deployed. V3's field tuning accuracy50.72% and source92.46% justified selecting it before calibration and final evaluation.

Same80-image PlantDoc external benchmark: V4 18/80=22.5%; V3 31/80=38.75%, +16.25points. This is a reused comparison benchmark, not new blind field data. V3 accepted precision50.0% at47.5%coverage remains weak; field diagnosis/advice remain unvalidated. Source fulltest3674:92.11%accuracy, macroF1.9087,96.47%acceptedprecision at87.02%coverage.

Artifact SHA `9f330bb88adffa64460c4e84faf808529a1a1fdc667977766f648cb28b51fa63`; size11,950,683bytes;17logits,960features. Exact model preprocessing, protocols, training-only feature standardization, official weight SHA, CAL gates and repeated-benchmark limits are recorded in these receipts.

Failed exploratory scripts remain under ml/crop_ml for reproducibility: head-only, natural-background, crop auxiliary, V4 teacher/relational distillation. Box-crop run was interrupted before its first evaluation. Their metrics are not deployed performance.
