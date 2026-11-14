"""Explore a field-CAL precision gate for a *new, locked* crop model.

This command reads a fit-phase CAL cache only. It never reads source/field tests,
changes the packaged policy, or claims independent field validation. It emits a
candidate proposal for review before a final-test lock, plus exact CAL support.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np

from .acceptance import _probabilities, _scores, evaluate_source_acceptance, wilson_interval
from .qualify import predicted_centroid_distances


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def analyze(work_dir: Path, output: Path, *, precision: float = .80,
            minimum_field_accepted: int = 5, historical_cal_audit: bool = False) -> dict:
    """Fit stricter per-class gates on CAL only, with source retention reported."""
    if output.exists():
        raise FileExistsError('Refusing to overwrite a prior gate experiment')
    if not (.5 < precision <= 1) or minimum_field_accepted < 5:
        raise ValueError('Field-CAL target must be >50% and support at least five')
    fit_path, predictions_path = work_dir/'fit_receipt.json', work_dir/'calibration_predictions.npz'
    policy_path, centroids_path = work_dir/'candidate_policy.json', work_dir/'embedding_centroids.json'
    fit = json.loads(fit_path.read_text())
    if (fit.get('test_evaluated') or (work_dir/'test_started.json').exists()) and not historical_cal_audit:
        raise ValueError('This candidate has already started final-test evaluation; do not refit gates')
    for path, key in [(predictions_path, 'calibration_predictions_sha256'),
                      (policy_path, 'candidate_policy_sha256'),
                      (centroids_path, 'embedding_centroids_sha256')]:
        if _sha(path) != fit[key]:
            raise ValueError(f'Frozen fit input changed: {path.name}')
    policy = json.loads(policy_path.read_text())
    basis = json.loads(centroids_path.read_text())
    if policy['model_version'] != fit['model_version'] or policy['model_sha256'] != fit['model_sha256']:
        raise ValueError('Policy and fit receipt belong to different models')
    if basis['model_sha256'] != fit['model_sha256'] or basis['label_ids'] != policy['label_ids']:
        raise ValueError('Centroids and policy disagree')
    with np.load(predictions_path, allow_pickle=False) as values:
        logits, features = values['logits'], values['embeddings']
        labels, group_ids = values['labels'], values['group_ids'].tolist()
    source_count = fit['fit_domain_counts']['calibration']['plantvillage']
    field_count = fit['fit_domain_counts']['calibration']['plantdoc_field_like']
    if field_count < 1 or len(labels) != source_count + field_count:
        raise ValueError('This fit lacks an independent field CAL slice')
    probabilities = _probabilities(logits.astype(np.float64), policy['temperature'])
    predicted, confidence, margin = _scores(probabilities)
    distances = predicted_centroid_distances(features, predicted, basis['centroids'])
    proposal = deepcopy(policy)
    per_class = {}
    field = slice(source_count, len(labels))
    for index, name in enumerate(policy['label_ids']):
        row = proposal['class_thresholds'][name]
        original = policy['class_thresholds'][name]
        mask = predicted[field] == index
        truth = labels[field] == index
        best = None
        if original['enabled'] and mask.sum() >= minimum_field_accepted:
            confidences = sorted({float(original['minimum_confidence']), .5, .6, .7, .8, .9, .95, .975, .99})
            margins = sorted({float(original['minimum_margin']), .05, .15, .3, .5, .7, .9})
            distance_bound = float(original['max_embedding_distance'])
            distance_limits = sorted({distance_bound, *[float(x) for x in np.quantile(
                distances[field][mask], [.2, .4, .6, .8]) if x <= distance_bound]})
            for c in confidences:
                if c < original['minimum_confidence']:
                    continue
                for m in margins:
                    if m < original['minimum_margin']:
                        continue
                    for d in distance_limits:
                        selected = mask & (confidence[field] >= c) & (margin[field] >= m) & (distances[field] <= d)
                        count = int(selected.sum())
                        if count < minimum_field_accepted:
                            continue
                        good = int((selected & truth).sum())
                        if good/count + 1e-12 < precision:
                            continue
                        # Maximize field CAL coverage, then correct support, source
                        # retention and strictness. This is selection evidence only.
                        source_selected = (predicted[:source_count] == index) & (confidence[:source_count] >= c) & \
                            (margin[:source_count] >= m) & (distances[:source_count] <= d)
                        rank = (count, good, int(source_selected.sum()), c, m, -d)
                        if best is None or rank > best[0]:
                            best = (rank, c, m, d, good, count)
        if best is None:
            row.update(enabled=False, reason='Insufficient correct field CAL support for precision gate')
            per_class[name] = {'enabled': False, 'field_cal_predictions': int(mask.sum()),
                               'field_cal_correct': int((mask & truth).sum())}
        else:
            _, c, m, d, good, count = best
            row.update(minimum_confidence=c, minimum_margin=m, max_embedding_distance=d,
                       reason='CAL-only field-aware prototype gate; requires independent test')
            per_class[name] = {'enabled': True, 'field_cal_predictions': int(mask.sum()),
                               'field_cal_accepted': count, 'field_cal_accepted_correct': good,
                               'field_cal_precision': good/count,
                               'field_cal_precision_wilson95': wilson_interval(good, count)}
    proposal['source_acceptance_enabled'] = any(v['enabled'] for v in proposal['class_thresholds'].values())
    source_report = evaluate_source_acceptance(logits[:source_count], labels[:source_count], proposal,
        policy['label_ids'], group_ids=group_ids[:source_count], embedding_distances=distances[:source_count])
    field_report = evaluate_source_acceptance(logits[field], labels[field], proposal,
        policy['label_ids'], group_ids=group_ids[source_count:], embedding_distances=distances[field])
    report = {'schema_version': 1, 'scope': 'CAL-only exploratory selection; no independent field guarantee',
              'historical_cal_audit_after_prior_finalization': historical_cal_audit,
              'model_sha256': fit['model_sha256'], 'fit_receipt_sha256': _sha(fit_path),
              'calibration_predictions_sha256': fit['calibration_predictions_sha256'],
              'target_observed_field_cal_precision': precision,
              'minimum_field_cal_accepted_per_enabled_class': minimum_field_accepted,
              'source_cal': {key: source_report[key] for key in ['samples','accuracy','accepted_precision','coverage','accepted_predictions']},
              'field_cal': {key: field_report[key] for key in ['samples','accuracy','accepted_precision','coverage','accepted_predictions','accepted_correct','accepted_precision_wilson95']},
              'enabled_class_count': sum(row['enabled'] for row in proposal['class_thresholds'].values()),
              'per_class': per_class,
              'feasible_with_source_coverage_30pct': bool(field_report['accepted_predictions'] >= minimum_field_accepted and
                  field_report['accepted_precision'] is not None and field_report['accepted_precision'] >= precision and
                  source_report['coverage'] >= .30),
              'limitations': ['CAL chosen and reported on the same small field sample; precision is optimistic.',
                              'Cannot claim field readiness without a new independent locked field test.',
                              'Disabled classes return uncertainty; no crop masking or score inflation.'],
              'candidate_class_thresholds': proposal['class_thresholds']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--precision', type=float, default=.80)
    parser.add_argument('--minimum-field-accepted', type=int, default=5)
    parser.add_argument('--historical-cal-audit', action='store_true',
                        help='Analyze a previously finalized model CAL cache for research only')
    args = parser.parse_args(argv)
    report = analyze(args.work_dir, args.output, precision=args.precision,
                     minimum_field_accepted=args.minimum_field_accepted,
                     historical_cal_audit=args.historical_cal_audit)
    print(json.dumps({key: report[key] for key in ['model_sha256','source_cal','field_cal',
                                                   'enabled_class_count','feasible_with_source_coverage_30pct']}, indent=2))


if __name__ == '__main__':
    main()
