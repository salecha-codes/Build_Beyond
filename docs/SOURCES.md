# Research sources and evidence boundaries

## Problem source

Only the final user-uploaded **Build_Beyond26_Problem_Statements.pdf**, PS 4.1, defines this project. The earlier problem PDF is excluded. No separate judging rubric was supplied.

## Data sources inspected

1. PlantVillage, pinned commit `7f7ecc7e1eaca78107e3affe7cb5abd9427e139a`: https://github.com/spMohanty/PlantVillage-Dataset
2. Dataset card and declared image-data license: https://github.com/spMohanty/PlantVillage-Dataset/blob/7f7ecc7e1eaca78107e3affe7cb5abd9427e139a/README_HF.md
3. Leaf grouping: https://github.com/spMohanty/PlantVillage-Dataset/blob/7f7ecc7e1eaca78107e3affe7cb5abd9427e139a/leaf_grouping/leaf-map.json
4. PlantDoc classification, pinned commit `5467f6012d78d1c446145d5f582da6096f852ae8`: https://github.com/pratikkayal/PlantDoc-Dataset
5. PlantDoc license: https://github.com/pratikkayal/PlantDoc-Dataset/blob/5467f6012d78d1c446145d5f582da6096f852ae8/LICENSE.txt

Complete Git trees were inventoried using filtered bare research clones. No entire project checkout was replaced, and no full image corpus was downloaded. Seventy-nine sample files were retrieved from pinned raw URLs, decoded, hashed and inspected as contact sheets. The compact evidence lives under `docs/audit/`; the larger research manifests remain outside the app checkout.

## Model and runtime sources inspected

- Torchvision MobileNetV3 model and weight metadata: https://github.com/pytorch/vision/blob/main/torchvision/models/mobilenetv3.py
- Official pretrained weights, HEAD returned 200: https://download.pytorch.org/models/mobilenet_v3_small-047dcff4.pth
- PyTorch/Torchvision package metadata: https://pypi.org/pypi/torch/2.9.1/json and https://pypi.org/pypi/torchvision/0.24.1/json — Torchvision explicitly requires Torch 2.9.1.
- ONNX Runtime Android example: https://github.com/microsoft/onnxruntime-inference-examples/tree/main/mobile/examples/image_classification/android
- ONNX Runtime Android artifact inspected: https://repo.maven.apache.org/maven2/com/microsoft/onnxruntime/onnxruntime-android/1.23.2/onnxruntime-android-1.23.2.aar
- ONNX Runtime Python metadata: https://pypi.org/pypi/onnxruntime/1.23.2/json
- Quantization implementation: https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/python/tools/quantization/quantize.py
- eSpeak NG Kannada voice definition: https://github.com/espeak-ng/espeak-ng/blob/master/espeak-ng-data/lang/dra/kn

The Android AAR was 30,241,654 downloaded bytes and contains all four common Android ABIs. Its manifest declares minSdk 24. The per-ABI application size and installed runtime performance have not been measured. Published third-party benchmarks are not our measurements.

Google Maven/Maven Central metadata returned 200 for AGP 8.9.2, Compose BOM 2025.04.01, CameraX 1.4.2, Room 2.7.1, Kotlin 2.1.20 and KSP 2.1.20-1.0.32. Gradle 8.11.1's published checksum was accessible. This establishes availability, not successful compilation.

## Advisory sources selected but not yet verified

- UC Integrated Pest Management crop guidelines: https://ipm.ucanr.edu/agriculture/
- Tamil Nadu Agricultural University Agritech guidance: https://agritech.tnau.ac.in/

UC IPM requests returned a proxy tunnel 403. The TNAU source is selected for later verification; its content has not been retrieved in this research pass. Exact source support for each guidance statement remains unverified. Do not label a treatment card as source-reviewed based only on these URLs. Kannada translation, pronunciation and agricultural suitability also remain content-validation tasks.

## Network and research limits

GitHub native/raw access, official PyTorch weight metadata, PyPI, Google Maven and Maven Central worked for the checked operations. GitHub API, Hugging Face, TensorFlow's tested Google Storage weight URL, UC IPM and Plantix requests were blocked by the environment proxy. These are operation-specific observations, not claims that the services are generally unavailable or require new credentials.

The architecture therefore uses an accessible PyTorch/ONNX route and avoids a hosted inference dependency. No proxy bypass, TLS-verification bypass, new secret, environment draft change or publication was performed. A complete competitor review and source-backed agricultural content review have not been completed; the product makes no uniqueness or treatment-validation claim based on this research.
