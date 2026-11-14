"""Measure frozen disease and leaf gates together on the reused field benchmark.

Run only after ``crop_ml.qualify finalize`` has locked and evaluated a model.
This report cannot calibrate thresholds and is not independent field validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .acceptance import _accepted, _probabilities, _scores, wilson_interval
from .common import labels, read_jsonl, sha256
from .model import prepare_image
from .qualify import predicted_centroid_distances


def measure(bundle: Path, work_dir: Path, field_protocol: Path, output: Path, threads: int = 3) -> dict:
    if output.exists():
        raise FileExistsError('Refusing to overwrite a prior joint-field report')
    metadata = json.loads((bundle/'model_metadata.json').read_text())
    policy = json.loads((bundle/'decision_policy.json').read_text())
    evaluation = json.loads((bundle/'source_evaluation.json').read_text())
    leaf_gate = metadata['leaf_gate']
    model_sha = sha256(bundle/'crop_model.onnx')
    if not (model_sha == metadata['model_sha256'] == policy['model_sha256'] == evaluation['model_sha256']):
        raise ValueError('Exact model hash differs among graph and frozen receipts')
    receipt_path = bundle/leaf_gate['receipt_file']
    if leaf_gate['receipt_file'] != 'leaf_validation.json' or sha256(receipt_path) != leaf_gate['receipt_sha256']:
        raise ValueError('Leaf gate receipt integrity failed')
    leaf_receipt = json.loads(receipt_path.read_text())
    if leaf_receipt['model_sha256'] != model_sha or leaf_receipt['minimum_leaf_probability'] != leaf_gate['minimum_leaf_probability']:
        raise ValueError('Leaf gate does not belong to this graph/threshold')
    if not (work_dir/'test_started.json').exists() or not (work_dir/'source_evaluation.json').exists():
        raise ValueError('Run locked final qualification before this read-only report')
    if sha256(work_dir/'source_evaluation.json') != sha256(bundle/'source_evaluation.json'):
        raise ValueError('Frozen final report differs from packaged receipt')
    partition = json.loads((field_protocol/'partition_receipt.json').read_text())
    benchmark = partition['files']['external_test_locked']
    rows_path = field_protocol/benchmark['file']
    if sha256(rows_path) != benchmark['sha256']:
        raise ValueError('External field benchmark changed')
    rows = read_jsonl(rows_path)
    with np.load(work_dir/'external_field_test_predictions.npz', allow_pickle=False) as previous:
        scores, features = previous['logits'], previous['embeddings']
        truth, image_hashes = previous['labels'], previous['image_sha256'].tolist()
    if len(rows) != benchmark['rows'] or len(rows) != len(scores):
        raise ValueError('Stored classifier outputs and frozen benchmark have different lengths')
    for index, row in enumerate(rows):
        if row['sha256'] != image_hashes[index] or row['label_index'] != int(truth[index]):
            raise ValueError('Stored classifier output order differs from frozen field benchmark')
    import onnxruntime as ort
    from PIL import Image
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(bundle/'crop_model.onnx'), options, providers=['CPUExecutionProvider'])
    probabilities = np.empty(len(rows), dtype=np.float64)
    for index, row in enumerate(rows):
        data = Path(row['local_path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('External field image bytes changed')
        with Image.open(row['local_path']) as image:
            tensor = prepare_image(image)[None]
        value = session.run(['leaf_logit'], {'image': tensor})[0]
        if value.shape != (1, 1) or not np.isfinite(value).all():
            raise ValueError('Leaf gate output changed shape or became nonfinite')
        z = float(value[0, 0])
        probabilities[index] = 1 / (1 + math.exp(-max(-60., min(60., z))))
    threshold = leaf_gate['minimum_leaf_probability']
    leaf_pass = probabilities >= threshold
    softmax = _probabilities(scores.astype(np.float64), policy['temperature'])
    predicted, confidence, margin = _scores(softmax)
    basis = json.loads((bundle/'embedding_centroids.json').read_text())
    if basis['model_sha256'] != model_sha:
        raise ValueError('Centroid sidecar belongs to a different model')
    distance = predicted_centroid_distances(features, predicted, basis['centroids'])
    score_pass = _accepted(predicted, confidence, margin, policy, policy['label_ids'], distance)
    conditions = labels()
    if [item['id'] for item in conditions] != policy['label_ids']:
        raise ValueError('Classifier labels differ from crop routing contract')
    crop = np.array([item['crop_id'] for item in conditions])
    same_crop = crop[predicted] == crop[truth]
    correct = predicted == truth
    delivered = leaf_pass & score_pass & same_crop
    good = int((delivered & correct).sum())
    delivered_count = int(delivered.sum())
    report = {'schema_version': 1, 'model_sha256': model_sha, 'source_evaluation_sha256': sha256(bundle/'source_evaluation.json'),
        'leaf_validation_sha256': leaf_gate['receipt_sha256'],
        'benchmark_manifest_sha256': benchmark['sha256'], 'samples': len(rows),
        'leaf_threshold': threshold, 'leaf_retained': int(leaf_pass.sum()),
        'leaf_retention': float(leaf_pass.mean()),
        'raw_classification_correct': int(correct.sum()),
        'raw_classification_accuracy': float(correct.mean()),
        'classifier_correct_and_leaf_pass': int((correct & leaf_pass).sum()),
        'classifier_correct_and_leaf_pass_rate': float((correct & leaf_pass).mean()),
        'score_gate_pass': int(score_pass.sum()),
        'after_leaf_score_correct_crop': {
            'delivered_condition_results': delivered_count, 'correct': good,
            'incorrect': delivered_count-good,
            'precision': good/delivered_count if delivered_count else None,
            'precision_wilson95': wilson_interval(good, delivered_count),
            'coverage': delivered_count/len(rows)},
        'leaf_pass_crop_mismatch_abstentions': int((leaf_pass & score_pass & ~same_crop).sum()),
        'field_diagnosis_validated': False,
        'note': ('Same reused 80-photo PlantDoc benchmark previously inspected for V4/V3 candidates. '
                 'Selection uses known correct crop as a best-case user input. This is a retrospective '
                 'comparison, not an independent field trial or a guarantee for farmer photos. '
                 'Quality/blur/brightness checks are outside this graph-level measurement.')}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--field-protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threads', type=int, default=3)
    args = parser.parse_args(argv)
    print(json.dumps(measure(args.bundle, args.work_dir, args.field_protocol, args.output, args.threads), indent=2))


if __name__ == '__main__':
    main()
