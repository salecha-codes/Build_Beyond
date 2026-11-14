# Dataset audit and supported taxonomy

This audit replaces the earlier approximate availability assessment. It inventories pinned repository trees and decodes a small deterministic image sample. It is not a full pixel-level audit or a model evaluation.

## Verified source versions

- PlantVillage: `7f7ecc7e1eaca78107e3affe7cb5abd9427e139a` at https://github.com/spMohanty/PlantVillage-Dataset
- PlantDoc: `5467f6012d78d1c446145d5f582da6096f852ae8` at https://github.com/pratikkayal/PlantDoc-Dataset
- Selected PlantVillage RGB files: **24,164**, before deduplication and exclusions.
- Crop totals: tomato **18,160**; potato **2,152**; maize **3,852**.
- Selected taxonomy: **17 categories**. Fourteen are nonhealthy conditions, one of which is a pest category (spider mites); three are healthy labels. Train a 17-output model; enable class-specific advice only after validation. Disabled classes produce an uncertain result, rather than being reassigned to another class.
- Source-declared dataset licenses: PlantVillage's repository dataset card declares CC BY-SA 3.0; PlantDoc includes CC BY 4.0. Keep attribution and source versions. Dataset licenses differ from training-library licenses. Full image datasets stay outside the application source checkout.

## Per-class inventory

| Category | RGB files | Files matched to source leaf map | Distinct mapped leaf groups |
|---|---:|---:|---:|
| Maize: Cercospora_leaf_spot Gray_leaf_spot | 513 | 0 | 0 |
| Maize: Common_rust_ | 1,192 | 0 | 0 |
| Maize: Northern_Leaf_Blight | 985 | 0 | 0 |
| Maize: healthy | 1,162 | 0 | 0 |
| Potato: Early_blight | 1,000 | 1,000 | 250 |
| Potato: Late_blight | 1,000 | 1,000 | 250 |
| Potato: healthy | 152 | 152 | 38 |
| Tomato: Bacterial_spot | 2,127 | 2,127 | 532 |
| Tomato: Early_blight | 1,000 | 999 | 250 |
| Tomato: Late_blight | 1,909 | 920 | 230 |
| Tomato: Leaf_Mold | 952 | 952 | 238 |
| Tomato: Septoria_leaf_spot | 1,771 | 1,000 | 250 |
| Tomato: Spider_mites Two-spotted_spider_mite | 1,676 | 1,676 | 419 |
| Tomato: Target_Spot | 1,404 | 0 | 0 |
| Tomato: Tomato_Yellow_Leaf_Curl_Virus | 5,357 | 2,738 | 685 |
| Tomato: Tomato_mosaic_virus | 373 | 0 | 0 |
| Tomato: healthy | 1,591 | 999 | 250 |

## Duplication and grouping

The Git tree contains **14 exact duplicate groups**, each with two selected files, and no cross-label exact duplicates in this subset. This comparison uses identical Git blob IDs, so it identifies byte-identical files without downloading every image. It does not identify recompressed or visually similar images.

Only **13,563 of 24,164** selected files were unambiguously matched to the supplied leaf-group map, spanning **3,392** known groups. Class-qualified filename matching was checked with conservative punctuation normalization; ambiguous/unmatched cases remain unresolved. In particular, the inspected map does not supply maize groups, and some other source naming conventions do not match. A random image split cannot therefore be described as fully leaf-independent.

Implementation must combine known groups with exact/near-duplicate clusters before splitting and report grouping coverage. Unresolved groups remain an explicit limitation. Hold out source-disjoint external images and use additional independent captures when available. Do not claim perceptual deduplication proves physical-leaf independence.

## Pixel sample review

Downloaded and decoded **79 images successfully**: 51 PlantVillage samples (three per selected class) and 28 PlantDoc samples (two per relevant available class). Both contact sheets were visually inspected. No decoder failures were found in this sample; the complete corpus has not been decoded.

PlantVillage samples generally show isolated leaves against controlled backgrounds. PlantDoc samples include backgrounds, watermarks, text, presentation slides, and comparison collages. The two available sampled PlantDoc spider-mite files are comparison montages containing multiple labeled symptom panels. Quarantine that class's PlantDoc images pending review; do not count them as independent field-test photographs.

The pinned PlantDoc classification tree contains **2,578 train/test image files**, while its documentation describes 2,598 data points. Use the pinned inventory counts in experiments. The discrepancy has not been explained; no missing files were invented or silently added.

## Cross-dataset mapping

Counts below are source files before image review and deduplication. A candidate label match still requires inspection. The object-detection CSV used in earlier research is a different artifact; these counts now come from the actual classification repository.

| Target category | PlantDoc class | Train files | Test files | Status |
|---|---|---:|---:|---|
| Maize: Cercospora_leaf_spot Gray_leaf_spot | Corn Gray leaf spot | 64 | 4 | candidate match |
| Maize: Common_rust_ | Corn rust leaf | 106 | 10 | candidate match |
| Maize: Northern_Leaf_Blight | Corn leaf blight | 180 | 12 | ambiguous do not merge |
| Maize: healthy | — | 0 | 0 | not present |
| Potato: Early_blight | Potato leaf early blight | 109 | 8 | candidate match |
| Potato: Late_blight | Potato leaf late blight | 97 | 8 | candidate match |
| Potato: healthy | — | 0 | 0 | not present |
| Tomato: Bacterial_spot | Tomato leaf bacterial spot | 101 | 9 | candidate match |
| Tomato: Early_blight | Tomato Early blight leaf | 79 | 9 | candidate match |
| Tomato: Late_blight | Tomato leaf late blight | 101 | 10 | candidate match |
| Tomato: Leaf_Mold | Tomato mold leaf | 85 | 6 | candidate match |
| Tomato: Septoria_leaf_spot | Tomato Septoria leaf spot | 140 | 11 | candidate match |
| Tomato: Spider_mites Two-spotted_spider_mite | Tomato two spotted spider mites leaf | 2 | 0 | quarantine sampled collages |
| Tomato: Target_Spot | — | 0 | 0 | not present |
| Tomato: Tomato_Yellow_Leaf_Curl_Virus | Tomato leaf yellow virus | 70 | 6 | ambiguous do not merge |
| Tomato: Tomato_mosaic_virus | Tomato leaf mosaic virus | 44 | 10 | candidate match |
| Tomato: healthy | Tomato leaf | 55 | 8 | verify healthy label convention |

There are only **85 official PlantDoc test files across the ten candidate disease-label matches** before exclusions. This is a small test, not comprehensive validation of all 17 outputs. Healthy maize/potato, target spot, and spider mites lack suitable official test coverage here. Broad yellow-virus and corn-blight labels are not merged automatically. There is no external accuracy claim yet.

## Locked data policy

1. Fetch pinned RGB sources into an external data directory, recording path, source, checksum, crop, condition, duplicate cluster and leaf group.
2. Decode every selected file; quarantine corrupt files, questionable labels, and multi-condition collages with reasons.
3. Compute exact hashes and perceptual hashes; manually inspect suspicious cross-label/near-duplicate clusters.
4. Create class-stratified group partitions at an approximate 70/15/15 train/validation/test ratio, adjusting small classes to preserve independent groups. Publish the exact final counts rather than claiming the ratio is exact.
5. Partition validation groups into tuning and calibration roles where sample sizes allow; document small-class uncertainty. Keep the final test locked.
6. Use class-balanced loss and capped sampling. Apply augmentation only to training images. Related grayscale and segmented versions are not independent extra observations.
7. Reserve PlantDoc test images before any domain fine-tuning. Only reviewed, compatible PlantDoc training images may enter fine-tuning, with source/duplicate groups kept separate from test. Report source-only and domain-adapted results independently.
8. Prepare an additional challenge set with unsupported crops and non-leaf scenes. It is an empirical test, not proof of universal unknown detection.

Machine-readable inventory: [crop coverage](audit/crop_coverage.csv), [mapping](audit/plantdoc_mapping.csv), and [audit summary](audit/audit_summary.json). Full inventories, sample hashes, samples, and contact sheets are retained in `/workspace/research/build-beyond/final-plan/` in this task. Those local research files must not be assumed to exist in a fresh checkout.
