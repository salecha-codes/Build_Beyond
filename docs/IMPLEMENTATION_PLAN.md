# Implementation sequence

The product and architecture decisions are finalized for implementation. No further user preference is required to start the technical work. This document does not claim that setup, training or APK generation has already happened.

## 1. Reproducible tools and data

- Use the existing `/workspace/Build_Beyond` checkout. Each cloud task is isolated; do not create a Git worktree unless explicitly requested.
- Keep images, model-training caches and raw research data outside the checkout. Retain pinned source manifests and compact audit evidence in the repository.
- Prepare Python 3.12 with PyTorch 2.9.1 and Torchvision 0.24.1 from the official CPU index, ONNX 1.18.0 and ONNX Runtime 1.23.2. Add Pillow, NumPy, scikit-learn, Matplotlib, image hashing, PyYAML and Pytest, resolving exact transitive versions into a lockfile.
- Prepare JDK 17, Android command-line SDK tools, SDK/platform 35, AGP 8.9.2 and Gradle 8.11.1. Verify the Gradle distribution against its published SHA-256. Use Kotlin 2.1.20, Compose BOM 2025.04.01, CameraX 1.4.2, Room 2.7.1 and KSP 2.1.20-1.0.32.
- Retrieve the three selected RGB crop folders from pinned PlantVillage and the relevant PlantDoc sources. Do not download grayscale/segmented copies as additional independent training data.
- Produce complete decode, hash, duplicate and split manifests; inspect questionable labels. The source tree and 79-sample audit are the starting point, not a substitute for this full ingestion pass.

Output: installable tools, dependency locks, immutable source references and auditable partitions. Tool/artifact availability has been checked for several key dependencies, but this stage has not executed yet.

## 2. Baseline and export

- Train a frozen-backbone baseline with group-aware validation and class-balanced training; log per-class results.
- Fine-tune only if the observed baseline justifies it. Avoid blindly increasing model size or training duration.
- Export fixed-shape ONNX with the documented preprocessing and two outputs.
- Verify PyTorch/ONNX output parity. Use simple initial confidence gating for integration, clearly marked provisional until calibration completes.

Output: a real model, labels, preprocessing fixtures and measured baseline metrics. Development fixtures can support UI work, but must be explicitly labeled and never presented as real inference.

## 3. Complete Android flow

- Build native screens, camera/gallery input, bounded-size image decoding and local model loading.
- Run actual local inference on a background thread and show typed result states.
- Package a small local guidance/audio set to verify the complete offline asset path; content marked unverified must not appear as approved treatment.
- Check the merged manifest for unwanted Internet permission and build separate ARM APKs.

Output: a complete installed scan-to-result flow with local assets. A build success is not a device-performance result.

## 4. Reliability and content

- Fit model-specific calibration, confidence/margin and embedding-distance gates using permitted validation data.
- Evaluate the declared unsupported-image challenge set; retain known limitations.
- Review relevant PlantDoc images before source-disjoint testing or domain fine-tuning.
- Inspect primary crop-management references, create versioned guidance for all enabled classes, draft/check Kannada translations and generate local English/Kannada audio using eSpeak NG. Listen to the outputs and record their review level.
- Add local Room history, deletion and explicit observation export.

Output: validated decision policy and source-traceable content. Expert follow-up opens a saved contact or share action; it does not promise an online expert service.

## 5. Optimize, test and package

- Compare FP32 and QDQ int8 models. Recompute model-dependent calibration/gates and assess phone resources before selecting the package.
- Run preprocessing fixtures across Python and Android; test the real airplane-mode journey, language/audio, resource use, denied permissions and failure recovery.
- Record actual device benchmark results, build hashes and known unsupported conditions.
- Complete Review 2/final materials using observed results. Preserve Review 1's planned-versus-achieved distinction.

Output: demonstrable APK, model/data card, evaluation report, source credits and short offline demo recording.

## Execution order and dependencies

Data/source work and toolchain preparation are independent. App scaffolding can progress after the model contract is fixed. Real inference integration requires an exported model; final confidence policy requires validation; enabled disease-specific advice requires verified content; performance claims require device measurements. Backend deployment is not on the critical path because no backend is used.

## Current external constraints

- UC IPM and other primary advisory pages were blocked by the environment's network policy. Guidance-source verification remains outstanding; URLs alone do not establish their contents.
- Full data decoding/near-duplicate audit, training, Android compilation, translation/audio review and phone testing remain unexecuted. These are implementation/validation tasks, not unresolved product choices.
- If later research needs blocked destinations, report the exact required domains for environment settings. Do not disable TLS checks or route around the policy. No publication or environment-draft changes were made during planning.

## Intended repository layout

```text
android/                 Native Android application
ml/                      Ingestion, training, export and evaluation tools
content/                 Versioned language records and audio-source text
contracts/               Model metadata, labels and decision-policy schemas
tests/                   Preprocessing fixtures and cross-component checks
docs/                    Architecture, evidence, evaluation and presentations
artifacts/               Small, intentional release metadata; large outputs ignored
```

Only the planning documents and compact audit evidence exist now. The listed application directories will be created during implementation.
