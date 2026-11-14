"""Pinned PlantDoc acquisition and metadata-only frozen partitions.

Source scripts were ported from the recorded Build Beyond acquisition. Candidate
labels remain unverified. Subcommands are explicit; importing runs no downloads,
image decoding, partitioning, training or model inference. Frozen outputs are never
overwritten. Historical spot-check notes below preserve past observations, not a
new visual review or an agricultural-expert review.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import csv
import datetime
import hashlib
import json
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image, ImageOps
from .common import LABELS_PATH, PROJECT

PLANTDOC_COMMIT = '5467f6012d78d1c446145d5f582da6096f852ae8'
PLANTDOC_LICENSE = 'CC-BY-4.0'
PARTITION_SEED = 'build-beyond-plantdoc-domain-v1-seed-42'
HISTORICAL_REVIEW = [{'source_path': 'train/Corn rust leaf/common-rust3.jpg',
  'sha256': '04cfdf7dd6686ca8a6dccd08c968df23ec7b61742d7c80ecd5a53aa7957cdf19',
  'condition_id': 'maize_common_rust',
  'review_method': 'individual_image_view_by_agent; not an agronomist or native-label expert review',
  'observations': 'Single close-up leaf-surface photo with brown lesions; no collage or text-only layout '
                  'observed. Disease label not verified.',
  'decision': 'retain_as_source_label_candidate_not_diagnosis_verified'},
 {'source_path': 'train/Corn Gray leaf spot/lipps-e.jpg',
  'sha256': '0a7b7262c4b4bc086913125e36696b5b89e377f662a7bf7aca95a43d8eb811a1',
  'condition_id': 'maize_gray_leaf_spot',
  'review_method': 'individual_image_view_by_agent; not an agronomist or native-label expert review',
  'observations': 'Photograph of an elongated leaf held in a hand; no collage or text-only layout observed. '
                  'Disease label not verified.',
  'decision': 'retain_as_source_label_candidate_not_diagnosis_verified'},
 {'source_path': 'train/Potato leaf early '
                 'blight/potato-blight-phytophthora-infestans-showing-infected-leaf-top-surface-bmmrtd.jpg',
  'sha256': '004a6826c8a076db0e5f33a5c8333a6bbe14da994c15084b3b3038db40aa2344',
  'condition_id': 'potato_early_blight',
  'review_method': 'individual_image_view_by_agent; not an agronomist or native-label expert review',
  'observations': 'Source filename explicitly names Phytophthora infestans, inconsistent with the '
                  'early-blight target; prominent stock-photo watermark observed. Quarantined for label '
                  'review, not relabeled.',
  'decision': 'quarantine_for_label_review'},
 {'source_path': 'train/Potato leaf late blight/potato_late-blight_08_zoom.jpg',
  'sha256': '08225e5f5940d234bffd9ad470561a7ea8e6e7ea7901dcb9c90da4fb5dd853b9',
  'condition_id': 'potato_late_blight',
  'review_method': 'individual_image_view_by_agent; not an agronomist or native-label expert review',
  'observations': 'Photograph showing several leaves with a dominant symptomatic pair; no visible panel '
                  'montage or text-only layout. Disease label not verified.',
  'decision': 'retain_as_source_label_candidate_not_diagnosis_verified'},
 {'source_path': 'train/Tomato leaf bacterial spot/bacterial-canker4x640-1nz1vm7.jpg',
  'sha256': '04f466fd99811ef1e64049f95a78fb3709aeae4fe064cfc5913ab11f7666f3cc',
  'condition_id': 'tomato_bacterial_spot',
  'review_method': 'individual_image_view_by_agent; not an agronomist or native-label expert review',
  'observations': 'Source filename names bacterial canker rather than bacterial spot. Leaf photo observed; '
                  'disease identity is not visually confirmed. Quarantined for label review, not relabeled.',
  'decision': 'quarantine_for_label_review'},
 {'source_path': 'train/Tomato Early blight leaf/tomato-early-blight-1.jpg',
  'sha256': '00267e1c492f34fbac534cd9994b7b1f039e8ef03d733ca4fcd429e5d4bfe105',
  'condition_id': 'tomato_early_blight',
  'review_method': 'individual_image_view_by_agent; not an agronomist or native-label expert review',
  'observations': 'Close-up photograph of a symptomatic leaf outdoors; no collage or text-only layout '
                  'observed. Disease label not verified.',
  'decision': 'retain_as_source_label_candidate_not_diagnosis_verified'},
 {'source_path': 'train/Tomato leaf late blight/20150619d.jpg',
  'sha256': '04ff0d731573d592c97f73cd2219800dcc9b4e7337c8ed90de2ec2374013a9fa',
  'condition_id': 'tomato_late_blight',
  'review_method': 'individual_image_view_by_agent; not an agronomist or native-label expert review',
  'observations': 'Photograph of two symptomatic leaves; no collage or text-only layout observed. Disease '
                  'label not verified.',
  'decision': 'retain_as_source_label_candidate_not_diagnosis_verified'},
 {'source_path': 'train/Tomato mold leaf/tomato_leaf-mold_01_zoom.jpg',
  'sha256': '02ce34bc701adf2c6d09578075a137632be6ba76e800048d7a26c309947fe0a9',
  'condition_id': 'tomato_leaf_mold',
  'review_method': 'individual_image_view_by_agent; not an agronomist or native-label expert review',
  'observations': 'Photograph of several curled leaves on a plant; no collage or text-only layout observed. '
                  'Disease label not verified.',
  'decision': 'retain_as_source_label_candidate_not_diagnosis_verified'},
 {'source_path': 'train/Tomato leaf mosaic virus/tomato_leaf_curl_ND_on_luffah_KC3701030-3.jpg',
  'sha256': '06abb18e0d50ff3033bfad357f0ba2ddee85f27f0f40127c5ff9a2a19ed352b4',
  'condition_id': 'tomato_mosaic_virus',
  'review_method': 'individual_image_view_by_agent; not an agronomist or native-label expert review',
  'observations': 'Source filename explicitly refers to leaf curl on luffah rather than tomato mosaic; '
                  'observed broad single leaf and small image. Quarantined for crop/label review, not '
                  'relabeled.',
  'decision': 'quarantine_for_label_review'},
 {'source_path': 'train/Tomato Septoria leaf spot/septoria_leaf_spot_of_tomato-1500x750.jpg',
  'sha256': '013981224e179d72c1538f59b7a226d2c7178d2bc4de61980db2d270ec74f3c9',
  'condition_id': 'tomato_septoria_leaf_spot',
  'review_method': 'individual_image_view_by_agent; not an agronomist or native-label expert review',
  'observations': 'Photograph of spotted leaves and fruit in a plant background; no collage or text-only '
                  'layout observed. Disease label not verified.',
  'decision': 'retain_as_source_label_candidate_not_diagnosis_verified'}]


def fetch_inventory(output: pathlib.Path, commit=PLANTDOC_COMMIT):
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('Inventory must pin an exact 40-character Git commit')
    if output.exists():
        raise FileExistsError('Refusing to overwrite an inventory')
    url = f'https://api.github.com/repos/pratikkayal/PlantDoc-Dataset/git/trees/{commit}?recursive=1'
    request = urllib.request.Request(url, headers={'User-Agent': 'BuildBeyond-PlantDoc-source-audit/1.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError('Inventory response exceeds 16 MiB')
    tree = json.loads(data)
    if tree.get('truncated'):
        raise ValueError('GitHub returned a truncated tree; do not acquire an incomplete dataset')
    inventory = {'commit': commit, 'entries': [{'path': row['path'], 'blob': row['sha'], 'type': row['type']} for row in tree['tree']]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, indent=2)+'\n')
    return inventory


def acquire(root: pathlib.Path, inventory_path: pathlib.Path, mapping_path: pathlib.Path,
            labels_path: pathlib.Path = LABELS_PATH, *, commit=PLANTDOC_COMMIT, workers=4):
    ROOT, COMMIT = root, commit
    RAW = ROOT/'raw'
    ORIGIN = 'https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/' + COMMIT + '/'
    INVENTORY = inventory_path
    if workers < 1:
        raise ValueError('workers must be positive')
    if not re.fullmatch(r'[a-f0-9]{40}', COMMIT):
        raise ValueError('Acquisition must pin an exact 40-character Git commit')
    if (ROOT/'all_images.jsonl').exists() or (ROOT/'partitions/partition_receipt.json').exists():
        raise FileExistsError('Refusing to overwrite acquired/frozen manifests; use a fresh output directory')
    ROOT.mkdir(parents=True, exist_ok=True)
    inventory = json.loads(INVENTORY.read_text())
    assert inventory['commit'] == COMMIT
    if any(pathlib.PurePosixPath(item['path']).is_absolute() or '..' in pathlib.PurePosixPath(item['path']).parts
           for item in inventory['entries']):
        raise ValueError('Inventory contains a path outside the pinned repository tree')
    by_path = {item['path']: item for item in inventory['entries'] if item['type'] == 'blob'}
    labels = {item['source_label']: item for item in json.loads(labels_path.read_text())['labels']}
    mapping = list(csv.DictReader(mapping_path.open()))
    selected = {row['plantdoc_label']: row for row in mapping if row['mapping_status'] == 'candidate_match'}
    entries = [item for name, item in by_path.items() if len(name.split('/')) >= 3 and name.split('/')[0] in ('train', 'test') and name.split('/')[1] in selected]

    def digest(data):
        return hashlib.sha256(data).hexdigest()

    def fetch(item):
        name = item['path']
        target = RAW / name
        url = ORIGIN + urllib.parse.quote(name, safe='/')
        target.parent.mkdir(parents=True, exist_ok=True)
        data = target.read_bytes() if target.is_file() else None
        if data is None:
            for attempt in range(4):
                try:
                    request = urllib.request.Request(url, headers={'User-Agent': 'BuildBeyond-PlantDoc-source-audit/1.0'})
                    with urllib.request.urlopen(request, timeout=30) as response:
                        data = response.read(32 * 1024 * 1024 + 1)
                    if len(data) > 32 * 1024 * 1024:
                        raise ValueError('Individual source exceeds 32 MiB acquisition cap')
                    break
                except (urllib.error.URLError, TimeoutError) as error:
                    if attempt == 3:
                        return {'source_path': name, 'download_error': str(error), 'source_url': url}
                    retry_after = error.headers.get('Retry-After') if isinstance(error, urllib.error.HTTPError) else None
                    time.sleep(min(float(retry_after or 2 ** attempt), 20))
            git_sha = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if git_sha != item['blob']:
                return {'source_path': name, 'download_error': 'Pinned Git blob hash mismatch', 'source_url': url}
            temporary = target.with_name(target.name + '.partial')
            temporary.write_bytes(data)
            temporary.replace(target)
        git_sha = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if git_sha != item['blob']:
            return {'source_path': name, 'download_error': 'Existing file differs from pinned Git blob', 'source_url': url}
        return {'source_path': name, 'local_path': str(target), 'source_url': url, 'git_blob_sha1': git_sha, 'sha256': digest(data), 'bytes': len(data)}

    for source_name in ('LICENSE.txt', 'README.md'):
        result = fetch(by_path[source_name])
        if result.get('download_error'):
            raise RuntimeError(result)

    print(f'Downloading {len(entries)} candidate-label images from pinned official source.', flush=True)
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for index, row in enumerate(pool.map(fetch, entries), 1):
            rows.append(row)
            if index % 50 == 0 or index == len(entries):
                print(f'Acquired {index}/{len(entries)}; errors={sum(bool(r.get("download_error")) for r in rows)}', flush=True)
    (ROOT / 'acquisition.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))

    print('Decoding sequentially, recording dimensions and lightweight duplicate hashes.', flush=True)
    for row in rows:
        split, source_class = row['source_path'].split('/')[:2]
        match = selected[source_class]
        label = labels[match['plantvillage_label']]
        row.update(original_split=split, source_class=source_class, condition_id=label['id'], label_index=label['index'], crop_id=label['crop_id'], source_dataset='PlantDoc classification', source_commit=COMMIT, license='CC-BY-4.0', mapping_status='candidate_match', visual_review_status='not_visually_reviewed', quality_flags=[])
        if row.get('download_error'):
            row['quality_flags'].append('download_failure')
            continue
        try:
            with Image.open(row['local_path']) as image:
                row.update(width=image.width, height=image.height, mode=image.mode, format=image.format)
                image.verify()
            with Image.open(row['local_path']) as image:
                image.load()
                image = ImageOps.exif_transpose(image)
                gray = image.convert('L').resize((9, 8), Image.Resampling.LANCZOS)
                pixels = list(gray.getdata())
                bits = sum((pixels[y * 9 + x] > pixels[y * 9 + x + 1]) << (y * 8 + x) for y in range(8) for x in range(8))
                row['dhash64'] = f'{bits:016x}'
            row['decode_ok'] = True
            if min(row['width'], row['height']) < 64:
                row['quality_flags'].append('very_small_image_requires_review')
            if max(row['width'], row['height']) / min(row['width'], row['height']) > 3.5:
                row['quality_flags'].append('extreme_aspect_ratio_requires_review')
            if re.search(r'(?i)(collage|montage|comparison|comparision|versus|(?:^|[ _.-])vs(?:[ _.-]|$)|slideshare)', pathlib.Path(row['source_path']).name):
                row['quality_flags'].append('filename_suggests_comparison_or_collage_requires_review')
        except Exception as error:
            row['decode_ok'] = False
            row['decode_error'] = str(error)
            row['quality_flags'].append('decode_failure')

    by_hash = collections.defaultdict(list)
    for row in rows:
        if row.get('sha256'):
            by_hash[row['sha256']].append(row)
    duplicates = []
    for sha, group in by_hash.items():
        if len(group) < 2:
            continue
        duplicates.append({'sha256': sha, 'source_paths': [row['source_path'] for row in group], 'conditions': sorted({row['condition_id'] for row in group}), 'splits': sorted({row['original_split'] for row in group})})
        conflicting = len({row['condition_id'] for row in group}) > 1
        cross_split = len({row['original_split'] for row in group}) > 1
        for row in group:
            row['exact_duplicate_group'] = sha
            if conflicting:
                row['quality_flags'].append('conflicting_label_exact_duplicate')
            elif cross_split and row['original_split'] == 'train':
                row['quality_flags'].append('exact_duplicate_of_locked_test')
            elif not cross_split and row is not group[0]:
                row['quality_flags'].append('same_split_exact_duplicate')

    for row in rows:
        row['metadata_eligible'] = bool(row.get('decode_ok')) and not row['quality_flags']
        row['pool_role'] = 'field_test_locked' if row['original_split'] == 'test' else 'field_train_candidate_requires_visual_review'

    def write_rows(filename, values):
        (ROOT / filename).write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in values))

    write_rows('all_images.jsonl', rows)
    write_rows('field_train_candidates.jsonl', [row for row in rows if row['original_split'] == 'train' and row['metadata_eligible']])
    write_rows('field_test_locked.jsonl', [row for row in rows if row['original_split'] == 'test'])
    write_rows('quarantine.jsonl', [row for row in rows if not row['metadata_eligible']])
    (ROOT / 'exact_duplicate_groups.json').write_text(json.dumps(duplicates, indent=2, ensure_ascii=False) + '\n')
    summary = {'source_repository': 'https://github.com/pratikkayal/PlantDoc-Dataset', 'source_commit': COMMIT, 'license': 'CC-BY-4.0', 'license_source': ORIGIN + 'LICENSE.txt', 'original_splits_preserved': True, 'test_evaluated': False, 'training_performed': False, 'visual_review_performed': False, 'candidate_label_classes': len(selected), 'counts': {}, 'by_class': {}, 'quality_flag_counts': dict(collections.Counter(flag for row in rows for flag in row['quality_flags'])), 'downloaded_bytes': sum(row.get('bytes', 0) for row in rows), 'exact_duplicate_groups': len(duplicates), 'near_duplicate_policy': 'dhash64 recorded only; similar hashes are review candidates and are not automatically treated as independent photos', 'known_excluded_mapping_statuses': {row['plantdoc_label']: row['mapping_status'] for row in mapping if row['plantdoc_label'] and row['mapping_status'] != 'candidate_match'}, 'limitations': ['Candidate cross-dataset labels are not expert-verified.', 'Internet-sourced PlantDoc photos may contain collages, text, watermarks, and non-independent crops not detectable from metadata.', 'Metadata-eligible training images still require visual/label review before domain fine-tuning.', 'Official test remains untouched and is not a broad independent farm-camera trial.', 'No cross-dataset perceptual duplicate adjudication has been performed.']}
    for split in ('train', 'test'):
        subset = [row for row in rows if row['original_split'] == split]
        summary['counts'][split] = {'source_files': len(subset), 'decoded': sum(bool(row.get('decode_ok')) for row in subset), 'metadata_eligible': sum(row['metadata_eligible'] for row in subset), 'quarantined': sum(not row['metadata_eligible'] for row in subset)}
    for source_class in selected:
        subset = [row for row in rows if row['source_class'] == source_class]
        summary['by_class'][source_class] = {split: {'source_files': sum(row['original_split'] == split for row in subset), 'metadata_eligible': sum(row['original_split'] == split and row['metadata_eligible'] for row in subset)} for split in ('train', 'test')}
    (ROOT / 'audit_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    (ROOT / 'README.md').write_text('# Pinned PlantDoc candidate acquisition\n\nOriginal train and test files are retained byte-for-byte in `raw/`. All source Git blob hashes are checked. `field_train_candidates.jsonl` contains decoded, metadata-eligible candidate label matches; visual/label review remains required before optional fine-tuning. `field_test_locked.jsonl` records every selected original test image and must remain excluded from training and model selection. It includes metadata flags without altering or evaluating the files. `quarantine.jsonl` records download/decode, filename/aspect, and exact-duplicate exclusions. dHash is a lightweight review aid, not a visual-review or independent-source guarantee.\n\nDataset: PlantDoc by Singh, Jain, Jain, Kayal, Kumawat and Batra (CoDS-COMAD 2020), Creative Commons Attribution 4.0 International. See `raw/LICENSE.txt`, pinned source URLs in each record, and `audit_summary.json`. No training, inference evaluation, or image-level human review occurred in this acquisition.\n')
    print(json.dumps(summary['counts'], indent=2), flush=True)
    print('Artifacts:', ROOT, flush=True)


def audit_metadata(root: pathlib.Path, source_manifest: pathlib.Path):
    if (root/'partitions/partition_receipt.json').exists():
        raise FileExistsError('Refusing to change manifests after partitions were frozen')
    prior_summary = json.loads((root/'audit_summary.json').read_text())
    if 'cross_source_exact_duplicate_files' in prior_summary:
        raise FileExistsError('Metadata audit was already applied')
    rows = [json.loads(line) for line in (root / 'all_images.jsonl').read_text().splitlines()]
    for row in rows:
        # Keep canonical IDs compatible with the existing PlantVillage manifest schema.
        row['label_id'] = row['condition_id']
        row['source'] = 'plantdoc'
        row['blob_sha1'] = row.get('git_blob_sha1')
    plantvillage = collections.defaultdict(list)
    for line in source_manifest.read_text().splitlines():
        row = json.loads(line)
        if row.get('sha256'):
            plantvillage[row['sha256']].append({'source_path': row['source_path'], 'label_id': row['label_id']})
    cross_source = []
    for row in rows:
        if row.get('sha256') in plantvillage:
            row['quality_flags'].append('exact_duplicate_of_plantvillage_source')
            cross_source.append({'plantdoc_path': row['source_path'], 'plantvillage_matches': plantvillage[row['sha256']]})

    train = [row for row in rows if row['original_split'] == 'train' and row.get('dhash64')]
    test = [row for row in rows if row['original_split'] == 'test' and row.get('dhash64')]
    near = []
    for a in train:
        for b in test:
            if a.get('sha256') == b.get('sha256'):
                continue
            distance = (int(a['dhash64'], 16) ^ int(b['dhash64'], 16)).bit_count()
            if distance <= 4:
                near.append({'train_path': a['source_path'], 'test_path': b['source_path'], 'dhash_distance': distance, 'train_condition': a['condition_id'], 'test_condition': b['condition_id'], 'status': 'unreviewed_similarity_candidate_not_confirmed_duplicate'})
                flag = 'possible_near_duplicate_of_locked_test_requires_review'
                if flag not in a['quality_flags']:
                    a['quality_flags'].append(flag)

    for row in rows:
        row['metadata_eligible'] = bool(row.get('decode_ok')) and not row['quality_flags']
        row['status'] = 'ok' if row['metadata_eligible'] else 'quarantined'

    def save(name, selected):
        (root / name).write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in selected))

    save('all_images.jsonl', rows)
    save('field_train_candidates.jsonl', [row for row in rows if row['original_split'] == 'train' and row['metadata_eligible']])
    save('field_test_locked.jsonl', [row for row in rows if row['original_split'] == 'test'])
    save('quarantine.jsonl', [row for row in rows if not row['metadata_eligible']])
    (root / 'cross_source_exact_duplicates.json').write_text(json.dumps(cross_source, indent=2) + '\n')
    (root / 'cross_split_near_duplicate_candidates.json').write_text(json.dumps(near, indent=2) + '\n')
    summary = json.loads((root / 'audit_summary.json').read_text())
    summary['quality_flag_counts'] = dict(collections.Counter(flag for row in rows for flag in row['quality_flags']))
    summary['cross_source_exact_duplicate_files'] = len(cross_source)
    summary['cross_split_near_duplicate_candidate_pairs'] = len(near)
    summary['near_duplicate_policy'] = '64-bit dHash distance <=4 across original train/test flags unreviewed similarity candidates; flagged train images excluded pending visual review. Not a confirmed duplicate judgment.'
    summary['source_manifest_sha256'] = hashlib.sha256(source_manifest.read_bytes()).hexdigest()
    for split in ('train', 'test'):
        subset = [row for row in rows if row['original_split'] == split]
        decoded = [row for row in subset if row.get('decode_ok')]
        summary['counts'][split] = {'source_files': len(subset), 'decoded': len(decoded), 'metadata_eligible': sum(row['metadata_eligible'] for row in subset), 'quarantined': sum(not row['metadata_eligible'] for row in subset), 'width_range': [min(row['width'] for row in decoded), max(row['width'] for row in decoded)], 'height_range': [min(row['height'] for row in decoded), max(row['height'] for row in decoded)], 'mode_counts': dict(collections.Counter(row['mode'] for row in decoded))}
    for source_class, detail in summary['by_class'].items():
        for split in ('train', 'test'):
            detail[split]['metadata_eligible'] = sum(row['source_class'] == source_class and row['original_split'] == split and row['metadata_eligible'] for row in rows)
    (root / 'audit_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    with (root / 'README.md').open('a') as out:
        out.write('\nAdditional manifest-only audit compares exact hashes to the acquired PlantVillage corpus and flags original train images with dHash distance ≤4 to locked test images. Those are unreviewed similarity candidates, not confirmed duplicates. They are withheld from the candidate training manifest pending review. Test originals remain unchanged. See `cross_source_exact_duplicates.json` and `cross_split_near_duplicate_candidates.json`.\n')
    print(json.dumps({'counts': summary['counts'], 'cross_source_exact_duplicate_files': len(cross_source), 'cross_split_near_duplicate_candidate_pairs': len(near), 'quality_flags': summary['quality_flag_counts']}, indent=2))


def partition(root: pathlib.Path, output: pathlib.Path, *, review_metadata: pathlib.Path | None = None,
              seed=PARTITION_SEED):
    ROOT, OUT, SEED = root, output, seed
    RATIOS = {'train': .70, 'tune': .15, 'calibration': .15}
    if (OUT/'partition_receipt.json').exists():
        raise FileExistsError('Refusing to overwrite a frozen field protocol')
    audit = json.loads((ROOT/'audit_summary.json').read_text())
    if 'cross_source_exact_duplicate_files' not in audit or 'cross_split_near_duplicate_candidate_pairs' not in audit:
        raise ValueError('Run the manifest-only source/similarity audit before freezing field partitions')
    OUT.mkdir(parents=True, exist_ok=True)
    def read(name):
        return [json.loads(line) for line in (ROOT/name).read_text().splitlines() if line.strip()]
    def sha_bytes(data):
        return hashlib.sha256(data).hexdigest()
    reviews = json.loads(review_metadata.read_text()) if review_metadata is not None else HISTORICAL_REVIEW
    candidates = {row['source_path']: row for row in read('field_train_candidates.jsonl')}
    for row in reviews:
        if row['source_path'] not in candidates or row['sha256'] != candidates[row['source_path']]['sha256']:
            raise ValueError('Historical review metadata does not match acquired source bytes/paths')
    review_exclusions = {row['source_path']: row['observations'] for row in reviews if row['decision'] == 'quarantine_for_label_review'}
    (OUT/'limited_visual_review.json').write_text(json.dumps(reviews, indent=2, ensure_ascii=False)+'\n')
    original_candidates = read('field_train_candidates.jsonl')
    assert all(row['original_split'] == 'train' and row['metadata_eligible'] for row in original_candidates)
    rows = [row.copy() for row in original_candidates if row['source_path'] not in review_exclusions]
    excluded = [dict(row, exclusion_reason=review_exclusions[row['source_path']]) for row in original_candidates if row['source_path'] in review_exclusions]

    parent = list(range(len(rows)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    edges = []
    for i, a in enumerate(rows):
        for j in range(i):
            b = rows[j]
            exact = a['sha256'] == b['sha256']
            distance = (int(a['dhash64'], 16) ^ int(b['dhash64'], 16)).bit_count()
            if exact or distance <= 4:
                union(i, j)
                edges.append({'left_source_path': a['source_path'], 'right_source_path': b['source_path'], 'dhash_distance': distance, 'same_sha256': exact, 'same_label': a['condition_id'] == b['condition_id'], 'interpretation': 'conservative grouping only; similarity is not a confirmed duplicate judgment'})
    groups = collections.defaultdict(list)
    for i, row in enumerate(rows):
        groups[find(i)].append(row)
    group_list = list(groups.values())
    class_totals = collections.Counter(row['label_id'] for row in rows)
    targets = {split: {label: count * ratio for label, count in class_totals.items()} for split, ratio in RATIOS.items()}
    assigned = {split: collections.Counter() for split in RATIOS}
    partitions = {split: [] for split in RATIOS}
    def stable_key(group):
        identity = '\n'.join(sorted(row['source_path'] + ':' + row['sha256'] for row in group))
        return sha_bytes((SEED + ':' + identity).encode())
    group_list.sort(key=lambda group: (-len(group), stable_key(group)))
    group_summary = []
    for group in group_list:
        counts = collections.Counter(row['label_id'] for row in group)
        def cost(split):
            class_delta = sum(((assigned[split][label] + count - targets[split][label]) ** 2 - (assigned[split][label] - targets[split][label]) ** 2) / max(targets[split][label], 1) for label, count in counts.items())
            target_total = len(rows) * RATIOS[split]
            before = len(partitions[split])
            total_delta = ((before + len(group) - target_total) ** 2 - (before - target_total) ** 2) / target_total
            return class_delta + 0.1 * total_delta
        split = min(RATIOS, key=lambda name: (cost(name), list(RATIOS).index(name)))
        group_id = 'plantdoc_source_group_' + stable_key(group)[:20]
        for row in group:
            row.update(id='plantdoc:' + row['source_commit'][:8] + ':' + sha_bytes(row['source_path'].encode())[:24], image_id='plantdoc:' + row['sha256'], raw_label=row['source_class'], canonical_condition_id=row['label_id'], canonical_class_index=row['label_index'], domain='plantdoc_internet_field_like', split=split, partition=split, group_id=group_id, leaf_group=group_id, label_review_status='source_dataset_candidate_not_expert_reviewed')
            row['visual_review_status'] = 'agent_spot_checked_quality_only_not_expert_reviewed' if any(review['source_path'] == row['source_path'] for review in reviews) else 'not_visually_reviewed'
            partitions[split].append(row)
        assigned[split].update(counts)
        group_summary.append({'group_id': group_id, 'split': split, 'size': len(group), 'condition_counts': dict(counts), 'source_paths': [row['source_path'] for row in group]})

    all_paths = set()
    all_groups = set()
    def write(name, values):
        values = sorted(values, key=lambda row: row['source_path'])
        data = ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in values).encode()
        (OUT / name).write_bytes(data)
        return {'file': name, 'rows': len(values), 'sha256': sha_bytes(data)}

    files = {}
    for split, subset in partitions.items():
        paths = {row['source_path'] for row in subset}
        group_ids = {row['group_id'] for row in subset}
        assert not paths & all_paths and not group_ids & all_groups
        assert set(assigned[split]) == set(class_totals), 'Every mapped class must be represented in each partition'
        all_paths.update(paths); all_groups.update(group_ids)
        files[split] = write(split + '.jsonl', subset)
    assert len(all_paths) == len(rows)
    files['eligible_original_train_pool'] = write('eligible_original_train_pool.jsonl', [row for subset in partitions.values() for row in subset])
    files['limited_review_exclusions'] = write('limited_review_exclusions.jsonl', excluded)

    # Only pre-existing metadata is read below; no test pixels, model scores or metrics.
    test_originals = read('field_test_locked.jsonl')
    assert all(row['original_split'] == 'test' for row in test_originals)
    assert not {row['sha256'] for row in rows} & {row['sha256'] for row in test_originals}
    for row in test_originals:
        row.update(id='plantdoc:' + row['source_commit'][:8] + ':' + sha_bytes(row['source_path'].encode())[:24], image_id='plantdoc:' + row['sha256'], raw_label=row['source_class'], canonical_condition_id=row['label_id'], canonical_class_index=row['label_index'], domain='plantdoc_internet_field_like', split='external_test_locked', partition='external_test_locked', group_id='plantdoc_external_test_' + row['sha256'][:20], label_review_status='source_dataset_candidate_not_expert_reviewed')
    files['external_test_all_original'] = write('external_test_all_original.jsonl', test_originals)
    files['external_test_locked'] = write('external_test_locked.jsonl', [row for row in test_originals if row['metadata_eligible']])
    (OUT / 'train_only_similarity_edges.json').write_text(json.dumps(edges, indent=2) + '\n')
    (OUT / 'source_groups.json').write_text(json.dumps(group_summary, indent=2) + '\n')
    receipt = {'protocol_version': 'plantdoc-original-train-grouped-v1', 'created_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source_commit': rows[0]['source_commit'], 'seed': SEED, 'requested_ratios': RATIOS, 'source_candidate_count': len(original_candidates), 'limited_review_count': len(reviews), 'limited_review_exclusions': len(excluded), 'eligible_original_train_count': len(rows), 'source_group_count': len(group_list), 'multi_image_groups': sum(len(group) > 1 for group in group_list), 'largest_group_size': max(map(len, group_list)), 'similarity_rule': 'Original-training images only; union exact SHA-256 or 64-bit dHash distance <=4, transitive closure; conservative grouping without duplicate identity claims.', 'assignment_method': 'Deterministic greedy minimum normalized squared deviation from per-class and total 70/15/15 targets; all groups stay in one partition.', 'split_counts': {split: len(subset) for split, subset in partitions.items()}, 'per_class_counts': {label: {split: assigned[split][label] for split in RATIOS} for label in sorted(class_totals)}, 'files': files, 'source_manifest_sha256': sha_bytes((ROOT / 'field_train_candidates.jsonl').read_bytes()), 'external_test_metadata_manifest_sha256': sha_bytes((ROOT / 'field_test_locked.jsonl').read_bytes()), 'original_test_used_for_split_decisions': False, 'original_test_pixels_read_by_partition_script': False, 'model_metrics_used': False, 'training_or_inference_performed': False, 'label_status': 'Candidate mappings and source labels remain unreviewed by an agricultural expert. Limited image review checked quality/filename consistency only.', 'release_policy': 'Freeze this receipt before optional domain adaptation. Train only on train.jsonl; select checkpoint on tune.jsonl; reserve calibration.jsonl for the final fixed model/policy. external_test_locked.jsonl is final external evaluation only. Do not combine with PlantVillage tests as one field-accuracy claim.'}
    (OUT / 'partition_receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n')
    (OUT / 'README.md').write_text('# Frozen PlantDoc domain-adaptation partitions\n\nThese partitions use eligible original-training images after the recorded limited-review exclusions; see partition_receipt.json for exact counts. Source disease labels remain candidate mappings, not expert-confirmed diagnoses. Exact SHA and conservative training-only dHash groups stay together.\n\n- `train.jsonl`: optional mixed-domain training only.\n- `tune.jsonl`: optional domain-model selection only.\n- `calibration.jsonl`: reserve until the selected model is frozen.\n- `external_test_locked.jsonl`: metadata-eligible original test images; final external check only.\n- `external_test_all_original.jsonl`: all selected original test records, preserving prior metadata flags.\n\nNo test pixels or model metrics were used to create the train/tune/calibration split. Existing acquisition-time test similarity flags remain respected. See `partition_receipt.json` for counts, checksums, seed, grouping, and limitations; `limited_visual_review.json` preserves the exact historical limited-review notes used by this invocation. No image bytes or source labels were changed.\n')
    print(json.dumps({key: receipt[key] for key in ['split_counts', 'source_group_count', 'multi_image_groups', 'largest_group_size', 'per_class_counts']}, indent=2))
    print('Frozen partitions:', OUT)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='phase', required=True)
    inventory = sub.add_parser('inventory', help='Fetch a pinned official GitHub tree; no image downloads')
    inventory.add_argument('--output', type=pathlib.Path, required=True)
    inventory.add_argument('--commit', default=PLANTDOC_COMMIT)
    acquire_parser = sub.add_parser('acquire', help='Download/check original bytes, license and candidate metadata')
    acquire_parser.add_argument('--root', type=pathlib.Path, required=True)
    acquire_parser.add_argument('--inventory', type=pathlib.Path, required=True)
    acquire_parser.add_argument('--mapping', type=pathlib.Path, default=PROJECT/'docs/audit/plantdoc_mapping.csv')
    acquire_parser.add_argument('--labels', type=pathlib.Path, default=LABELS_PATH)
    acquire_parser.add_argument('--commit', default=PLANTDOC_COMMIT)
    acquire_parser.add_argument('--workers', type=int, default=4)
    audit = sub.add_parser('audit', help='Manifest-only source/hash/similarity audit; no pixels decoded')
    audit.add_argument('--root', type=pathlib.Path, required=True)
    audit.add_argument('--plantvillage-manifest', type=pathlib.Path, required=True)
    split = sub.add_parser('partition', help='Freeze train/tune/CAL and locked external-test manifests')
    split.add_argument('--root', type=pathlib.Path, required=True)
    split.add_argument('--output', type=pathlib.Path, required=True)
    split.add_argument('--review-metadata', type=pathlib.Path,
                       help='Historical limited-review JSON; default is the exact recorded ten-image spot check')
    split.add_argument('--seed', default=PARTITION_SEED)
    args = parser.parse_args(argv)
    if args.phase == 'inventory':
        result = fetch_inventory(args.output, args.commit)
        print(json.dumps({'commit': result['commit'], 'entries': len(result['entries']), 'output': str(args.output)}))
    elif args.phase == 'acquire':
        acquire(args.root, args.inventory, args.mapping, args.labels, commit=args.commit, workers=args.workers)
    elif args.phase == 'audit':
        audit_metadata(args.root, args.plantvillage_manifest)
    else:
        partition(args.root, args.output, review_metadata=args.review_metadata, seed=args.seed)


if __name__ == '__main__':
    main()
