"""Fix TUNE interval selection for an unchanged leaf head and model graph.

Writes an isolated candidate, freezes its threshold before loading reused TEST
features, and reports a comparison. Never installs assets or retrains weights.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

import numpy as np

from .leaf_gate import FIELD_TUNE, SOURCE_TUNE, rates, score, select_threshold, sha, write, wilson


def run(args):
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'candidate_frozen.json').exists():
        raise FileExistsError('Use a fresh output directory; frozen candidates cannot be retuned')
    bundle = args.bundle
    metadata = json.loads((bundle / 'model_metadata.json').read_text())
    model_hash = sha(bundle / 'crop_model.onnx')
    if model_hash != metadata['model_sha256']:
        raise ValueError('Model identity mismatch')
    head = dict(np.load(args.head, allow_pickle=False))
    previous_threshold = float(metadata['leaf_gate']['minimum_leaf_probability'])
    if float(head['threshold']) != previous_threshold:
        raise ValueError('Expected current frozen head threshold')
    tune_paths = {'source': SOURCE_TUNE, 'field': FIELD_TUNE,
                  'negative': args.leaf_work / 'negative_tune.npy'}
    tune_features = {k: np.load(p, allow_pickle=False) for k, p in tune_paths.items()}
    tune_features['field'] = tune_features['field']['features']
    if [len(tune_features[k]) for k in ('source', 'field', 'negative')] != [2228, 138, 104]:
        raise ValueError('Unexpected frozen TUNE partition sizes')
    tune_scores = {k: score(v, head) for k, v in tune_features.items()}
    threshold, metrics, interval = select_threshold(
        tune_scores['source'], tune_scores['field'], tune_scores['negative'])
    protocol = {
        'schema_version': 1, 'task': 'unchanged_leaf_head_threshold_selection_bugfix',
        'selection_partition': 'TUNE only',
        'selection': 'search all union-score intervals; maximize nonleaf rejection, then field recall, then source recall',
        'field_leaf_recall_floor': .95, 'source_leaf_recall_floor': .98,
        'representative': 'interior midpoint of winning (lower, upper] interval',
        'tune_cache_sha256': {k: sha(p) for k, p in tune_paths.items()},
        'head_sha256': sha(args.head), 'model_sha256': model_hash,
        'model_version': metadata['model_version'],
        'disease_classifier_changed': False, 'leaf_head_changed': False,
        'source_classifier_gates_changed': False,
        'reused_test_policy': 'comparison only after freezing; no threshold/model selection from TEST',
        'field_diagnosis_validated': False,
    }
    write(out / 'protocol.json', protocol)
    frozen = {'protocol_sha256': sha(out / 'protocol.json'),
              'model_sha256': model_hash, 'head_sha256': sha(args.head),
              'minimum_leaf_probability': threshold, 'threshold_interval': interval,
              'selected_tune_metrics': metrics, 'test_opened': False}
    write(out / 'candidate_frozen.json', frozen)
    frozen_hash = sha(out / 'candidate_frozen.json')
    # No TEST features, reports, or original receipt contents are opened above.
    original_receipt = bundle / 'leaf_validation.json'
    shutil.copy2(original_receipt, out / 'previous_leaf_validation.json')
    old_receipt = json.loads(original_receipt.read_text())
    if (old_receipt['model_sha256'] != model_hash or
            old_receipt['minimum_leaf_probability'] != previous_threshold):
        raise ValueError('Current leaf receipt is not bound to current model and threshold')
    test_paths = {
        'source': args.qualification / 'source_test_predictions.npz',
        'field': args.qualification / 'external_field_test_predictions.npz',
        'negative': args.leaf_work / 'negative_test.npy',
    }
    test_features = {}
    for k, p in test_paths.items():
        data = np.load(p, allow_pickle=False)
        test_features[k] = data['embeddings'] if k != 'negative' else data
    if [len(test_features[k]) for k in ('source', 'field', 'negative')] != [3674, 80, 125]:
        raise ValueError('Unexpected reused TEST partition sizes')
    test_scores = {k: score(v, head) for k, v in test_features.items()}
    comparison = {
        'reused_test': True, 'independent_validation': False,
        'candidate_frozen_sha256': frozen_hash,
        'test_cache_sha256': {k: sha(p) for k, p in test_paths.items()},
        'previous_threshold': previous_threshold, 'candidate_threshold': threshold,
        'previous': rates(test_scores['source'], test_scores['field'], test_scores['negative'], previous_threshold),
        'candidate': rates(test_scores['source'], test_scores['field'], test_scores['negative'], threshold),
    }
    previous_negative = json.loads((args.leaf_work / 'negative_test_report.json').read_text())
    if len(previous_negative['per_image']) != len(test_scores['negative']):
        raise ValueError('Negative manifest/report length mismatch')
    per_image = []
    for row, probability in zip(previous_negative['per_image'], test_scores['negative']):
        if not np.isclose(probability, row['leaf_probability'], rtol=1e-5, atol=1e-7):
            raise ValueError('Negative TEST feature order differs from frozen original report')
        per_image.append({**row, 'leaf_probability': float(probability),
                          'rejected': bool(probability < threshold)})
    rejected = int((test_scores['negative'] < threshold).sum())
    negative_report = {'samples': len(per_image), 'rejected': rejected,
                       'nonleaf_rejection': rejected / len(per_image),
                       'wilson95': wilson(rejected, len(per_image)),
                       'reused_test': True, 'independent_validation': False, 'per_image': per_image}
    validation = {
        'schema_version': 1, 'model_sha256': model_hash,
        'model_version': metadata['model_version'], 'output_name': 'leaf_logit',
        'minimum_leaf_probability': threshold, 'head_sha256': sha(args.head),
        'protocol': protocol, 'selected_tune_metrics': {
            'minimum_leaf_probability': threshold, 'threshold_interval': interval, 'metrics': metrics},
        'previous_tune_metrics': rates(tune_scores['source'], tune_scores['field'], tune_scores['negative'], previous_threshold),
        'negative_test': negative_report, 'reused_test_comparison': comparison,
        'previous_leaf_validation_sha256': sha(original_receipt),
        'candidate_frozen_sha256': frozen_hash,
        'disease_classifier_changed': False, 'leaf_head_changed': False,
        'leaf_gate_test_evaluated_once': False,
        'source_classifier_evaluation': {
            'file': 'source_evaluation.json', 'sha256': sha(bundle / 'source_evaluation.json'),
            'scope': 'unchanged classifier weights and classifier gates only; historical receipt contains previous leaf-validation hash',
            'input_gate_changed': True},
        'field_diagnosis_validated': False,
        'scope': 'prototype leaf input validation; reused examples do not establish field diagnosis accuracy or reject every nonleaf image',
    }
    if sha(out / 'candidate_frozen.json') != frozen_hash or sha(args.head) != frozen['head_sha256'] or sha(bundle / 'crop_model.onnx') != model_hash:
        raise ValueError('Frozen candidate identity changed during comparison')
    write(out / 'comparison.json', comparison)
    write(out / 'leaf_validation.json', validation)
    selected_examples = [r for r in per_image if r.get('class_name') in ['mouse', 'laptop']]
    print(json.dumps({'threshold': threshold, 'interval': interval, 'tune': metrics,
                      'reused_test': comparison, 'mouse_laptop_examples': selected_examples,
                      'receipt': str(out / 'leaf_validation.json')}, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, default=Path('models/assets/model'))
    p.add_argument('--head', type=Path, default=Path('/workspace/crop-artifacts/leaf_gate/leaf_head.npz'))
    p.add_argument('--leaf-work', type=Path, default=Path('/workspace/crop-artifacts/leaf_gate'))
    p.add_argument('--qualification', type=Path, default=Path('/workspace/crop-artifacts/healthy_qualification'))
    p.add_argument('--output', type=Path, default=Path('/workspace/crop-artifacts/leaf_threshold_fix'))
    run(p.parse_args())


if __name__ == '__main__':
    main()
