# Kandahar field data reproducibility

`crop_ml.kandahar_data` prepares external research data. It never runs model
inference, changes app assets, or publishes raw images. Its default outputs
quarantine broad source disease labels. Original **Blight / Healthy / Spot** may
be used only for the explicit three-way auxiliary experiment. The separate
`healthy` command maps only source **Healthy** with explicitly maize crop to
`maize_healthy` (index 3). Blight and Spot never map into the17 disease labels.

## Pinned source and terms

- Repository: https://github.com/RafiullahRafi/MaizeLeafDisease-Kandahar-FieldData-DeepLearningModels
- Commit: `33d0e081240535f6d70cca99b343517dc75e92eb`
- File: `Kdr_field_Dataset.zip`, 19,339,390 bytes.
- SHA-256: `69b4e2d7cb31d7098a61cbad699fc57403242b5ef9d0a5c1bce300ad7aa5162f`
- Repository license: GPL-3.0 as published. Image-specific license/provenance is
  not separately documented; retain source attribution and review these terms
  before any redistribution. Photos must remain outside the repo/app.

The source describes field and hybrid maize experiments. Its broad labels and
reported model accuracies do not establish exact disease species or our app's
field accuracy. Healthy is a dataset-provided label, not an independent expert
confirmation.

## Commands

Run from the repository root, using the ML environment in `ml/requirements.txt`.
These are **reproduction commands**, not deployment steps. Use a fresh external
root; do not overwrite a frozen experiment's manifests.

```bash
export PYTHONPATH=ml
python -m crop_ml.kandahar_data --help
python -m crop_ml.kandahar_data download --root /workspace/crop-data/kandahar-reproduction
```

Download verifies the exact size/SHA before extraction. Extraction rejects
absolute/traversal paths, symlinks, entries outside the published split folders,
excessive expansion, and an existing destination.

Supply **every** existing field partition to each audit, including reserved
partitions for duplicate exclusion only. No predictions or labels from reserved
partitions are used to fit a model. The example includes every JSONL in the
original partition directory, including overlapping original pools and excluded
rows, to reproduce the conservative 5,834-row prior comparison. Replace paths if your data lives elsewhere.

```bash
python -m crop_ml.kandahar_data inspect \
  --root /workspace/crop-data/kandahar-reproduction \
  --prior-maize-manifest /workspace/crop-data/splits.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/train.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/tune.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/calibration.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/external_test_locked.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/external_test_all_original.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/eligible_original_train_pool.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/limited_review_exclusions.jsonl

python -m crop_ml.kandahar_data audit-aux \
  --root /workspace/crop-data/kandahar-reproduction \
  --prior-maize-manifest /workspace/crop-data/splits.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/train.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/tune.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/calibration.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/external_test_locked.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/external_test_all_original.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/eligible_original_train_pool.jsonl \
  --prior-field-manifest /workspace/crop-data/plantdoc-5467f601/partitions/limited_review_exclusions.jsonl
```

`inspect` decodes images for exact encoded/pixel duplicate identification and
initial quarantine. `audit-aux` computes Pillow grayscale Lanczos 9×8 dHash64
under eight dihedral views, using Hamming distance ≤4. Prior perceptual comparison
uses all supplied source maize and field rows; exact SHA comparison covers all
supplied source rows. It groups original filename families, internal perceptual
neighbors, and same-label captures within three seconds. Entire connected groups
are quarantined for cross-split membership, conflicting labels, or prior-data
overlap. Duplicate pixels are removed. Original split assignments are preserved.

The initial audit opened reserved pixels strictly for duplicate exclusion; do
not rerun it during model tuning. Once frozen, use its receipts/manifests and
keep all locked test images out of training and selection. These heuristics do
not prove farm-level or date-level independence.

For the **explicit Healthy-only main-head protocol**, reuse audited metadata:

```bash
python -m crop_ml.kandahar_data healthy \
  --root /workspace/crop-data/kandahar-reproduction \
  --old-source-splits-manifest /workspace/crop-data/splits.jsonl \
  --old-train-tune-manifest /workspace/crop-artifacts/full_validation_protocol/tune.jsonl \
  --old-train-tune-manifest /workspace/crop-data/plantdoc-5467f601/partitions/train.jsonl \
  --old-train-tune-manifest /workspace/crop-data/plantdoc-5467f601/partitions/tune.jsonl
```

This step reads metadata only. It verifies bound auxiliary manifest hashes,
checks exact/group disjointness against existing main TRAIN/TUNE, and creates a
separate permission scope for compatible healthy rows. Supply all applicable
main TRAIN/TUNE manifests; arbitrary paths are recorded and hashed in receipts.

## Audited experiment counts

The original 2,045 JPEGs contained 2,040 unique encoded/pixel images and 782
filename-derived originals. The audit against 5,834 source-maize/field rows
excluded 164 photos as connected groups and removed four further pixel duplicates.
The resulting auxiliary split had TRAIN **1,757** (Blight 751, Healthy 448,
Spot 558), VALID **61** (23,18,20), and locked TEST **59** (29,14,16).
The Healthy-only protocol has TRAIN **448**, VALID **18**, locked TEST **14**.
No candidate inference on the new locked test was used for data preparation.

Each output directory contains JSONL manifests and an artifact-bound receipt
with source commit, archive hash, input-manifest hashes, counts, exclusions,
usage restrictions, and output hashes. File hashes include local paths and
therefore differ across machines even when photo identities/counts agree.
The14-photo healthy test can support only a small healthy-only assessment after
candidate freeze, never a general disease-accuracy claim.
