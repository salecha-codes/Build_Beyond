# Instrumentation input fixture

`leaf_input.jpg` is a PlantVillage tomato healthy-class example used only to exercise image decoding, model execution and persistence. These tests do not assert a disease prediction or estimate model accuracy.

Pinned source: https://github.com/spMohanty/PlantVillage-Dataset/blob/7f7ecc7e1eaca78107e3affe7cb5abd9427e139a/raw/color/Tomato___healthy/b9046af2-28a7-4546-9107-1ae6d0bb7de7___RS_HL 0174.JPG

SHA-256: `eb5f9c10404aabeab5d2205a06689c4f0c966b1c7dbca20bb96c8927ccd1dae8`

The repository dataset card declares CC BY-SA 3.0. This file belongs to the test APK, not the production app's default scan history. No source image or artificial outcome is inserted into production user history.

## Second photographic model smoke input

`field_leaf_input.jpg` is an original PlantDoc TRAIN photograph, also assigned to the frozen field-training partition. It is used only to establish that the shipped ONNX graph produces finite, input-dependent outputs for two different photographs. The instrumentation smoke does not assert a disease label, measure accuracy, or use held-out CAL/external-test images.

Pinned source: https://github.com/pratikkayal/PlantDoc-Dataset/blob/5467f6012d78d1c446145d5f582da6096f852ae8/train/Tomato%20leaf%20late%20blight/20150619d.jpg

SHA-256: `04ff0d731573d592c97f73cd2219800dcc9b4e7337c8ed90de2ec2374013a9fa`

Attribution: PlantDoc by Davinder Singh, Naman Jain, Pranjali Jain, Pratik Kayal, Sudhakar Kumawat and Nipun Batra (CoDS-COMAD 2020), dataset license CC BY 4.0: https://github.com/pratikkayal/PlantDoc-Dataset/blob/5467f6012d78d1c446145d5f582da6096f852ae8/LICENSE.txt . Source labels remain unreviewed candidate mappings. This byte-for-byte input belongs only to the test APK.

## Independent preprocessing fixtures

`golden/` contains Python-generated float32 NCHW reference tensors and source PNGs. The constant-color and textured leaf inputs each assert every NCHW value within absolute 1e-5 of the independent Python reference. The Android tensor path uses the Pillow-compatible separable bilinear helper. Both fixtures executed with zero maximum, mean and p99 error on the final Android emulator run. These fixture assets are test-only; this pair of fixtures establishes its tested preprocessing behavior, not exhaustive image-decoder or camera accuracy.

Leaf derivative source: https://github.com/spMohanty/PlantVillage-Dataset/blob/7f7ecc7e1eaca78107e3affe7cb5abd9427e139a/raw/color/Tomato___healthy/b9046af2-28a7-4546-9107-1ae6d0bb7de7___RS_HL 0174.JPG
Original source SHA-256: `eb5f9c10404aabeab5d2205a06689c4f0c966b1c7dbca20bb96c8927ccd1dae8`. PNG/tensor checksums and coordinate probes are in `golden/preprocessing_fixtures.json`.
