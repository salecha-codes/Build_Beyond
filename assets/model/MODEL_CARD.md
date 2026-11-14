# Leaf-guarded MobileNetV3 release

New binary leaf input head precedes the unchanged crop classifier. See leaf_validation.json for frozen TRAIN/TUNE protocol and held-out negative results. Exact-graph source qualification passed after frozen calibration and testing. Classifier-only accuracy is92.11% on source3674 and38.75% on the reused80-photo field comparison; these classifier figures exclude leaf rejection.


Model SHA-256: `3332b5634fcb1a8bea17317a0a9db4d6e44f9c0da24e7b03718b3ced5d6b2d1e`. Graph size:11,965,503bytes. Outputs17disease logits,960features and1leaf logit.

## Input leaf check

This graph adds a trained binary leaf-versus-object head sharing the same V3 features. It checks the image before presenting disease candidates; a rejected input returns a retake with no disease name or score. Threshold0.7736096007959162 was frozen on TUNE before opening the125-image negative test.

It rejected125/125 non-leaf test photos, including the held-out computer mouse, hamster, cat, laptop and monitor. This is a measured sample result, not a universal guarantee. The negatives are objects/mammals/electronics from a pinned ImageNet sample repository; ambiguous nature/plant classes were excluded. Test objects were excluded from leaf-head training; broader ImageNet pretraining is disclosed. Images are external research inputs and are not shipped in the app.

Source positive leaf recall3668/3674 (99.84%); source correct disease predictions retained3378/3674=91.94% end-to-end. Field leaf recall76/80 (95%); all31 previously correct field disease cases pass the leaf check, preserving31/80=38.75% end-to-end on the reused field set. See leaf_validation.json and the separate positive_pipeline_evaluation receipt. The leaf check does not certify the crop species or every unseen object/plant.
