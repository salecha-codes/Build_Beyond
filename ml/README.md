# Crop model training and evaluation

Current release: pretrained MobileNetV3-Large with a trained 17-class head; field comparison 22.5% → 38.75%. See [executed V3 receipts](reports/field_upgrade_v3/) and the shared model card. `crop_ml.v3_comparator` trains/selects on TRAIN/TUNE only; `crop_ml.export_v3_candidate` embeds the exact frozen backbone/head/standardization in ONNX. Their `--help` lists reproducible commands and paths. Calibration/finalization uses the same two-phase `crop_ml.qualify` pipeline below.

## Historical V4 pipeline


The earlier V4 prototype used **MobileNetV4-Conv-Small**, with 17 stable condition IDs from `contracts/labels.json`. Both current V3-Large and historical V4-Conv-Small expose 960 pooled features; the earlier V3-Small 576-feature assumption does not apply.

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

The bundle contains `crop_model.onnx`, labels, preprocessing metadata, decision policy, model card and execution receipts. Export initially leaves all predictions uncertain. The separate two-phase qualification below can enable dataset-tested prototype matches for the exact exported artifact. **Field `validated=false` stays separate**; export parity or source accuracy cannot validate field diagnosis or chemical prescriptions.

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

## Full-data retraining and source acceptance

The replacement pipeline uses all 16,856 source training images. The original 3,620-image validation partition is divided by known groups into 2,228 tuning and 1,392 calibration images. Checkpoints are selected on tuning only; calibration fits temperature and per-class confidence/margin/distance gates. The original full 3,674-image source test is evaluated once after the selected model and gates are frozen. Historical exposure and incomplete physical-leaf metadata are recorded in the protocol receipt.

```sh
python -m crop_ml.prepare_qualification --data-root /workspace/crop-data --output /workspace/crop-artifacts/full_validation_protocol --prior-subset /workspace/crop-artifacts/scratch_continued/validation_subset.jsonl --replay-prior-sampler
python -m crop_ml.training_improved --data-root /workspace/crop-data --output /workspace/crop-artifacts/full_training --selection-manifest /workspace/crop-artifacts/full_validation_protocol/tune.jsonl --calibration-manifest /workspace/crop-artifacts/full_validation_protocol/calibration.jsonl --resume-checkpoint /workspace/crop-artifacts/scratch_continued/best.pt --epochs 12 --threads 4 --precision bf16
```

The prior subset/checkpoint above come from the historical bounded experiment. Use fresh output directories: protocol CLIs refuse to overwrite frozen files. BF16 is a CPU training optimization; selection and export run in FP32.

`crop_ml.field_data` supplies `inventory`, `acquire`, `audit` and `partition` commands for pinned PlantDoc commit `5467f6012d78d1c446145d5f582da6096f852ae8` (CC-BY-4.0). Source-label conflicts and exact/near duplicates are quarantined; the eligible original training pool supplies 632 train, 138 tune and 137 calibration images. Eighty eligible original-test images remain a separate external benchmark. These are internet-sourced, field-like pictures with mostly unreviewed disease labels, not a farmer trial.

`training_improved --mode field-audit` audits the frozen base on field tuning; `--mode field` trains mixed source/field batches using only TRAIN images. The saved selection protocol declares source-retention floors, field-improvement criteria, epochs and partition hashes before candidate evaluation. The optional extension is a separate experiment with a recorded protocol; it does not rewrite earlier selection decisions. See the executed receipts for its exact warm start and selected candidate.

After selecting and exporting the final checkpoint, run qualification in two explicit phases:

```sh
python -m crop_ml.qualify fit --bundle /workspace/crop-artifacts/final_bundle --work-dir /workspace/crop-artifacts/qualification --protocol /workspace/crop-artifacts/full_validation_protocol --field-protocol /workspace/crop-data/plantdoc-5467f601/partitions --include-field-train --threads 3
python -m crop_ml.qualify finalize --bundle /workspace/crop-artifacts/final_bundle --work-dir /workspace/crop-artifacts/qualification --protocol /workspace/crop-artifacts/full_validation_protocol --field-protocol /workspace/crop-data/plantdoc-5467f601/partitions --threads 3
python tools/sync_model_bundle.py /workspace/crop-artifacts/final_bundle
```

Omit `--include-field-train` for a model without field training; the selected training receipt must prove an exact manifest match. `fit` reads TRAIN and CAL only and freezes policy hashes. `finalize` checks those locks, marks the test operation before inference and rejects repeated finalization. It reports source accuracy/macro F1 and accepted precision/coverage, including per-class support and uncertainty bounds; external field results stay separate. Predeclared source qualification requires accuracy ≥85%, macro F1 ≥0.80, accepted precision ≥90%, and coverage ≥30%. Passing enables source prototype matches, never field validation or condition-specific prescriptions.

Both apps check the evaluated artifact hash, receipt hash, frozen temperature/gates and normalized training-only centroids. A missing qualification stays uncertain; corrupt claimed evidence makes the model unavailable. The centroid gate is an unfamiliar-feature heuristic, with no validated unknown-image rejection guarantee.

## Leaf/object input head

`crop_ml.nonleaf_data` prepares pinned object/animal negatives with class-group splits. `crop_ml.leaf_gate` fits a binary head against real leaf TRAIN features, freezes threshold on TUNE, and evaluates locked object TEST before exporting an isolated three-output graph. Requalify the new exact ONNX hash with `crop_ml.qualify`, then install the bound leaf-validation sidecar with `tools/sync_model_bundle.py`. See leaf_guard receipts for executed counts, ImageNet source limitations and positive-leaf recall. Photos remain external and are not packaged.

## Additional verified field data

See [KANDAHAR_DATA.md](KANDAHAR_DATA.md) for pinned acquisition, perceptual/family audits, licensing/provenance and exact Healthy-only mapping. Only448TRAINHealthymaize photos enter the current17-class head. Blight/Spot remainbroadauxiliary labels andneverbecomeexactdisease targets. VALID18 selectedthehead; lockedTEST14 wasopenedonceafterfreezing. Currentoutcomes are in reports/healthy_field_update.
