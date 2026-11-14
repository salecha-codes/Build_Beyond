"""Audit source identities and freeze group-preserving tuning/calibration manifests.

No images are evaluated and no test outcomes are read by this script. Historical
evaluation receipt metadata is recorded explicitly; the historical test is not
an entirely untouched benchmark. Run with Python 3, no third-party dependencies.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import random



def load(path):
    return [json.loads(line) for line in path.open() if line.strip()]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(output: Path, name, rows):
    path = output / name
    path.write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows))
    return {'path': str(path), 'sha256': digest(path), 'images': len(rows),
            'groups': len({r['group_id'] for r in rows})}


def prepare_protocol(data_root: Path, output: Path, prior_subsets: list[Path], *, seed=2601,
                     replay_prior_sampler=False, prior_prediction_paths=(),
                     historical_test_receipt: Path | None = None):
    ROOT, DATA, SEED, PRIOR_SUBSETS = output, data_root, seed, prior_subsets
    if (ROOT/'protocol_receipt.json').exists():
        raise FileExistsError('Refusing to overwrite an already frozen qualification protocol')
    if not PRIOR_SUBSETS:
        raise ValueError('Declare at least one exact prior selection subset for exposure auditing')
    ROOT.mkdir(parents=True, exist_ok=True)
    rows = load(DATA / 'splits.jsonl')
    verified = [r for r in load(DATA / 'manifest.jsonl') if r.get('status') == 'verified']
    by_sha = collections.defaultdict(list)
    by_group = collections.defaultdict(list)
    by_leaf = collections.defaultdict(list)
    for row in rows:
        assert row['status'] == 'verified'
        by_sha[row['sha256']].append(row)
        by_group[row['group_id']].append(row)
        if row.get('leaf_group'):
            by_leaf[row['leaf_group']].append(row)
    assert all(len(items) == 1 for items in by_sha.values()), 'Exact duplicate in frozen split'
    for groups in (by_group, by_leaf):
        for identity, items in groups.items():
            assert len({r['split'] for r in items}) == 1, f'Cross-split group: {identity}'
            assert len({r['label_id'] for r in items}) == 1, f'Cross-label group: {identity}'
    assert set(by_sha) == {r['sha256'] for r in verified}, 'Deduplicated source coverage differs'
    row_by_sha = {r['sha256']: r for r in rows}
    # Audit all original leaf metadata, including metadata on a dropped exact copy.
    original_leaf_members = collections.defaultdict(list)
    identity_fields = ['source', 'source_commit', 'label_index', 'label_id', 'crop_id']
    for source_row in verified:
        split_row = row_by_sha[source_row['sha256']]
        assert all(source_row[k] == split_row[k] for k in identity_fields), 'Verified identity changed'
        if source_row.get('leaf_group'):
            original_leaf_members[source_row['leaf_group']].append(split_row)
    for identity, members in original_leaf_members.items():
        assert len({r['split'] for r in members}) == 1, f'Original leaf metadata crosses split: {identity}'
        assert len({r['group_id'] for r in members}) == 1, f'Original leaf metadata crosses group: {identity}'
    assert all(Path(r['local_path']).is_file() for r in rows), 'Acquired image missing'
    prior_images = set()
    prior_receipts = []
    for path in PRIOR_SUBSETS:
        old = load(path)
        for row in old:
            current = row_by_sha[row['sha256']]
            assert current['split'] == 'validation'
            assert current['group_id'] == row['group_id']
            prior_images.add(row['sha256'])
        prior_receipts.append({'path': str(path), 'sha256': digest(path), 'images': len(old)})
    prior_groups = {row_by_sha[s]['group_id'] for s in prior_images}
    if replay_prior_sampler:
        # The initial three-epoch experiment used the same seed/max-per-class sampler;
        # check its lineage rather than assuming the later manifest covers exposure.
        rng = random.Random(26)
        replay = {}
        for split in ['train', 'validation']:
            candidates = [r for r in rows if r['split'] == split]
            replay[split] = [r for index in range(17) for r in rng.sample(
                [r for r in candidates if r['label_index'] == index],
                min(128 if split == 'train' else 32, sum(r['label_index'] == index for r in candidates)))]
        exact_old = load(PRIOR_SUBSETS[0])
        assert [r['sha256'] for r in replay['validation']] == [r['sha256'] for r in exact_old]
        for path in prior_prediction_paths:
            assert json.loads(path.read_text())['labels'] == [r['label_index'] for r in exact_old]

    validation = [r for r in rows if r['split'] == 'validation']
    classes = sorted({r['label_id'] for r in validation}, key=lambda c: next(r['label_index'] for r in validation if r['label_id'] == c))
    cal_groups = set()
    per_class = {}
    for label in classes:
        members = [r for r in validation if r['label_id'] == label]
        groups = {r['group_id'] for r in members}
        novel = groups - prior_groups
        target_groups = max(1, round(len(groups) * .4))
        # Stable hash permutation avoids dependence on input row ordering/Python RNG.
        candidates = novel if novel else groups
        ordered = sorted(candidates, key=lambda g: hashlib.sha256(f'{SEED}:{label}:{g}'.encode()).hexdigest())
        selected = set(ordered[:min(target_groups, len(candidates))])
        assert selected and groups - selected
        cal_groups.update(selected)
        cal = [r for r in members if r['group_id'] in selected]
        per_class[label] = {
            'validation_images': len(members), 'validation_groups': len(groups),
            'previously_selected_images': sum(r['sha256'] in prior_images for r in members),
            'previously_selected_groups': len(groups & prior_groups),
            'novel_groups_available': len(novel), 'target_calibration_groups': target_groups,
            'calibration_images': len(cal), 'calibration_groups': len(selected),
            'tune_images': len(members)-len(cal), 'tune_groups': len(groups-selected),
            'calibration_prior_selection_images': sum(r['group_id'] in prior_groups for r in cal),
            'calibration_prior_selection_groups': sorted(selected & prior_groups),
            'novel_calibration_shortfall': max(0, target_groups-len(novel)),
        }
    tune = [r for r in validation if r['group_id'] not in cal_groups]
    calibration = [r for r in validation if r['group_id'] in cal_groups]
    assert {r['sha256'] for r in tune}.isdisjoint(r['sha256'] for r in calibration)
    assert {r['group_id'] for r in tune}.isdisjoint(r['group_id'] for r in calibration)
    assert len(tune)+len(calibration) == len(validation)
    test = [r for r in rows if r['split'] == 'test']
    files = {'tune': save(ROOT, 'tune.jsonl', tune), 'calibration': save(ROOT, 'calibration.jsonl', calibration),
             'test_locked': save(ROOT, 'test_locked.jsonl', test)}
    old_test = historical_test_receipt
    historical_test = None
    if old_test is not None:
        old = json.loads(old_test.read_text())
        historical_test = {'receipt': str(old_test), 'receipt_sha256': digest(old_test),
                           'previously_evaluated_samples': old.get('evaluated_samples'),
                           'source_test_samples': old.get('source_test_samples'),
                           'limited_subset': old.get('limited_subset')}
    result = {
        'schema_version': 1, 'protocol_version': 'source-group-calibration-v1', 'seed': SEED,
        'source_split_manifest': str(DATA/'splits.jsonl'), 'source_split_sha256': digest(DATA/'splits.jsonl'),
        'source_counts': dict(collections.Counter(r['split'] for r in rows)),
        'audit': {'verified_files_before_exact_dedup': len(verified), 'unique_split_images': len(rows),
                  'exact_duplicates_excluded': len(verified)-len(rows),
                  'unique_groups': len(by_group), 'known_leaf_group_images': sum(bool(r.get('leaf_group')) for r in rows),
                  'known_leaf_groups': len(by_leaf), 'cross_split_exact_hash_collisions': 0,
                  'cross_split_group_collisions': 0, 'cross_split_known_leaf_collisions': 0,
                  'original_manifest_leaf_groups_including_dropped_copies': len(original_leaf_members),
                  'verified_identity_mapping_checked': True, 'all_unique_image_paths_exist': True,
                  'image_bytes_rehashed_this_run': False,
                  'verification_scope': 'Audit of verified acquisition hashes, group identities and original manifests; no perceptual or manual duplicate review.'},
        'partition_method': 'Per-class group-preserving 40% of groups for calibration, stable SHA256 permutation. Prefer only groups absent from all old selection subsets. Where novel groups are fewer than target, take all novel groups and leave calibration smaller. Only where zero novel groups exist, use exposed groups and disclose exposure.',
        'files': files, 'per_class': per_class, 'prior_validation_subsets': prior_receipts,
        'prior_validation_unique_images': len(prior_images), 'prior_validation_unique_groups': len(prior_groups),
        'prior_initial_and_continued_selection_sampler_replay_matches_exact_order': True if replay_prior_sampler else None,
        'historical_test_exposure': historical_test,
        'boundaries': [
            'Training uses original train only. Checkpoint and hyperparameter selection use tune only.',
            'Freeze checkpoint and exported artifact SHA256 before inference on calibration.',
            'Fit scalar temperature and choose confidence/margin thresholds on calibration only. Do not feed calibration performance back into training or checkpoint choice.',
            'Any calibration stratum marked with prior-selection exposure is not independent of historic selection.',
            'Run the selected exact artifact once on the entire original source-test manifest with frozen temperature/thresholds. Report failures without adjusting from test.',
            'Historical source-test exposure is recorded when its receipt is supplied. Absence of that receipt does not establish a pristine benchmark.',
            'Known leaf identifiers are incomplete. Unmatched physical leaves, source-domain bias and field-photo generalization remain unresolved.',
            'Source-domain confidence does not validate diagnosis, treatment, symptom severity, or performance on farmers’ field photos.',
        ], 'diagnosis_validated': False,
    }
    (ROOT/'protocol_receipt.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prior-subset', type=Path, action='append', required=True,
                        help='Exact old model-selection validation JSONL; repeat for all known subsets')
    parser.add_argument('--seed', type=int, default=2601)
    parser.add_argument('--replay-prior-sampler', action='store_true',
                        help='Verify the historic seed26/max-per-class128 sampler against first prior subset')
    parser.add_argument('--prior-predictions', type=Path, action='append', default=[],
                        help='Historic predictions JSON to check against exact replayed label order')
    parser.add_argument('--historical-test-receipt', type=Path)
    args = parser.parse_args(argv)
    if args.prior_predictions and not args.replay_prior_sampler:
        parser.error('--prior-predictions requires --replay-prior-sampler')
    result = prepare_protocol(args.data_root, args.output, args.prior_subset, seed=args.seed,
        replay_prior_sampler=args.replay_prior_sampler, prior_prediction_paths=args.prior_predictions,
        historical_test_receipt=args.historical_test_receipt)
    print(json.dumps({'files': result['files'], 'audit': result['audit']}, indent=2))


if __name__ == '__main__':
    main()
