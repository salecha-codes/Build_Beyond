# Further field experiments — not shipped

The current app still ships the leaf-guarded MobileNetV3 model, SHA `3332b5634fcb1a8bea17317a0a9db4d6e44f9c0da24e7b03718b3ced5d6b2d1e`.

- Residual neural heads: best field tuning accuracy 51.45%, versus the current 50.72%; insufficient improvement.
- RBF kernel head: field tuning accuracy 55.80%, but only 29/80 correct after the leaf check on the reused reserved field benchmark, versus the current 31/80. Rejected.
- Partial disease-tail fine-tuning: three field tuning results 51.45%, 50.72%, 48.55%; no candidate qualified. The original leaf-check pathway stayed unchanged.

Training/selection used TRAIN and TUNE partitions. Only the selected RBF graph received frozen calibration and reserved comparison evaluation; it was not deployed. No thresholds were retuned from the field benchmark. The benchmark was already used in earlier model comparisons and is not newly blind independent data. These reports preserve unsuccessful work without presenting its tuning scores as shipped performance.
