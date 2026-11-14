# Real MobileNetV4 pipeline

The Android model is **MobileNetV4-Conv-Small**, with 17 stable condition IDs from `contracts/labels.json`. Its measured pooled feature dimension is **960**, not the earlier V3-specific 576.

## Setup

Use Python 3.12 and an environment/cache outside the source checkout:

```sh
uv --cache-dir /workspace/.cache/crop-uv venv /workspace/.venvs/crop-ml
uv --cache-dir /workspace/.cache/crop-uv pip install --python /workspace/.venvs/crop-ml/bin/python torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu
uv --cache-dir /workspace/.cache/crop-uv pip install --python /workspace/.venvs/crop-ml/bin/python -r ml/requirements.txt
export PYTHONPATH="$PWD/ml"
```

Run these commands from the repository root using the environment's Python. The examples below use `python` for that interpreter.

## Acquire and partition

```sh
python -m crop_ml.acquire --data-root /workspace/crop-data --workers 24
python -m crop_ml.prepare --data-root /workspace/crop-data
```

Acquisition pins the source commit, selects only the three RGB crop subsets, checks each downloaded file against its Git blob hash, and actually decodes it. Check `acquisition_receipt.json`; failed downloads cause a nonzero exit. Existing valid files are reused. Use `--max-per-class 32` only for an explicitly limited smoke corpus.

Split construction keeps supplied known leaf groups and exact duplicates together, drops exact copies from use, and stratifies by class. Unmatched physical-leaf metadata remains a documented limitation; no complete near-duplicate/manual image review is claimed.

## Train

```sh
python -m crop_ml.train --data-root /workspace/crop-data --output /workspace/crop-artifacts/training --pretrained --freeze-backbone --epochs 3 --threads 3
```

The official timm pretrained configuration uses Hugging Face. If that destination is blocked, the command is blocked; it does not silently switch architecture or invent a pretrained checkpoint. A compatible downloaded checkpoint may be supplied with `--pretrained-checkpoint`. Without either pretrained option, training is from scratch and the receipt says so. Freezing a random backbone is rejected.

The optional `--max-per-class` flag creates an explicitly limited experiment. Validation results are model-selection data, not a held-out field test. No final-test score is inferred from them.

For a bounded from-scratch prototype experiment (not ImageNet transfer learning):

```sh
python -m crop_ml.train --data-root /workspace/crop-data --output /workspace/crop-artifacts/scratch_training --max-per-class 128 --epochs 3 --threads 3
python -m crop_ml.train --data-root /workspace/crop-data --output /workspace/crop-artifacts/scratch_continued --resume-checkpoint /workspace/crop-artifacts/scratch_training/best.pt --max-per-class 128 --epochs 12 --threads 3
```

Continuation is a transparent weight warm-start with a restarted optimizer. Its receipt preserves the parent checkpoint hash and training history. Keep the initial run and final test receipts unchanged; later candidates must not be selected by repeatedly inspecting final-test results.

## Export and test

```sh
python -m crop_ml.export --checkpoint /workspace/crop-artifacts/training/best.pt --output /workspace/crop-artifacts/android_bundle
pytest ml/tests -q
```

Omit `--checkpoint` only to produce a real executable **untrained pipeline-smoke model**. Export runs the ONNX checker and CPU runtime on zero and nonzero inputs, comparing both outputs with PyTorch. It writes actual desktop latency as desktop data, never phone performance.

The bundle contains `crop_model.onnx`, labels, preprocessing metadata, decision policy, model card and execution receipts. The prototype policy is deliberately **validated=false**, so the app must show an uncertain/unvalidated state and block condition-specific advice even though the ONNX graph executes. Enabling accepted diagnoses requires independent evaluation and a properly calibrated shipped artifact; this pipeline never flips that flag based on a smoke test.

For a one-time exact-artifact comparison on a held-out source-domain test subset:

```sh
python -m crop_ml.evaluate --data-root /workspace/crop-data --bundle /workspace/crop-artifacts/android_bundle --compare-smoke /workspace/crop-artifacts/pipeline_smoke --output /workspace/crop-artifacts/android_bundle/source_test_metrics.json --max-per-class 32
```

This reports test counts and an actual untrained same-architecture baseline. It is not field validation. Golden preprocessing PNGs/raw float32 tensors and diagnostic tolerance guidance live in `contracts/fixtures/`.

When an export includes its exact validation subset, temperature can be fitted to **the exported graph's** outputs:

```sh
python -m crop_ml.calibrate --bundle /workspace/crop-artifacts/android_bundle --data-root /workspace/crop-data --threads 3
```

This is explicitly a source-validation fit, possibly on data also used for model selection. It does not validate the acceptance thresholds or enable diagnoses. Model identity derives from its architecture/training mode and actual ONNX hash; pipeline-smoke and trained artifacts have different identities.
