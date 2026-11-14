"""One-time frozen comparison on the new Kandahar Healthy test photos.

The test is opened only after the candidate passes source qualification and the
previously reused field benchmark's predeclared non-regression check. Results
remain a tiny retrospective source-labeled comparison, not field validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .acceptance import _probabilities, _scores, wilson_interval
from .common import read_jsonl, sha256
from .model import prepare_image
from .qualify import _exclusive_json, predicted_centroid_distances


def _bundle_result(bundle: Path, rows: list[dict], threads: int) -> dict:
    import onnxruntime as ort
    from PIL import Image
    metadata = json.loads((bundle/'model_metadata.json').read_text())
    policy = json.loads((bundle/'decision_policy.json').read_text())
    graph_hash = sha256(bundle/'crop_model.onnx')
    if not (graph_hash == metadata['model_sha256'] == policy['model_sha256']):
        raise ValueError('Bundle graph, metadata and policy identity differ')
    if not policy.get('source_acceptance_qualified') or not metadata.get('source_acceptance_qualified'):
        raise ValueError('Bundle has no source-qualified gate')
    gate = metadata['leaf_gate']
    if gate['receipt_file'] != 'leaf_validation.json' or sha256(bundle/gate['receipt_file']) != gate['receipt_sha256']:
        raise ValueError('Leaf receipt integrity differs')
    leaf_receipt = json.loads((bundle/gate['receipt_file']).read_text())
    if leaf_receipt['model_sha256'] != graph_hash or \
            leaf_receipt['minimum_leaf_probability'] != gate['minimum_leaf_probability']:
        raise ValueError('Leaf threshold is not bound to this graph')
    centroids = json.loads((bundle/'embedding_centroids.json').read_text())
    if centroids['model_sha256'] != graph_hash or len(centroids['centroids']) != 17:
        raise ValueError('Centroids are not bound to the exact graph')
    options = ort.SessionOptions(); options.intra_op_num_threads = threads; options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(bundle/'crop_model.onnx'), options, providers=['CPUExecutionProvider'])
    logits, features, leaf_probability = [], [], []
    for row in rows:
        with Image.open(row['local_path']) as image:
            tensor = prepare_image(image)[None]
        scores, embedding, leaf_logit = session.run(['logits', 'embeddings', 'leaf_logit'], {'image': tensor})
        if scores.shape != (1, 17) or embedding.shape != (1, 960) or leaf_logit.shape != (1, 1) or \
                not np.isfinite(scores).all() or not np.isfinite(embedding).all() or not np.isfinite(leaf_logit).all():
            raise ValueError('Actual ONNX graph outputs violate the 17/960/1 contract')
        logits.append(scores[0]); features.append(embedding[0])
        leaf_probability.append(1/(1+math.exp(-max(-60., min(60., float(leaf_logit[0, 0]))))))
    logits, features = np.asarray(logits), np.asarray(features)
    predicted, confidence, margin = _scores(_probabilities(logits.astype(np.float64), policy['temperature']))
    distance = predicted_centroid_distances(features, predicted, centroids['centroids'])
    leaf_pass = np.asarray(leaf_probability) >= gate['minimum_leaf_probability']
    healthy = predicted == 3
    row = policy['class_thresholds']['maize_healthy']
    supported = bool(row['enabled'])
    n = len(rows)
    familiar = distance <= row['max_embedding_distance'] if supported else np.zeros(n, dtype=bool)
    visible_correct = healthy & leaf_pass & familiar
    strict_correct = (visible_correct & (confidence >= row['minimum_confidence']) &
                      (margin >= row['minimum_margin'])) if supported else np.zeros(n, dtype=bool)
    return {'model_sha256': graph_hash, 'model_version': metadata['model_version'], 'samples': n,
            'top_maize_healthy': int(healthy.sum()), 'leaf_pass': int(leaf_pass.sum()),
            'correct_and_leaf_pass': int((healthy & leaf_pass).sum()),
            'visible_correct_and_leaf_pass': int(visible_correct.sum()),
            'visible_correct_and_leaf_pass_rate': float(visible_correct.mean()),
            'visible_correct_wilson95': wilson_interval(int(visible_correct.sum()), n),
            'strict_healthy_accepted': int(strict_correct.sum()),
            'unfamiliar_healthy_prediction': int((healthy & leaf_pass & ~familiar).sum()),
            'healthy_class_enabled': supported,
            'candidate_score_range': [float(np.min(confidence[healthy])), float(np.max(confidence[healthy]))] if healthy.any() else None,
            'distance_range_for_correct_predictions': [float(np.min(distance[healthy])), float(np.max(distance[healthy]))] if healthy.any() else None,
            'scope': ('Visible correct means the healthy top class, leaf pass, enabled class, and '
                      'familiar distance; low score or margin may still show only a provisional candidate. '
                      'Photo quality/blur gates and manual user crop choice are outside this graph-level count.')}


def evaluate(control: Path, candidate: Path, work_dir: Path, source: Path, output: Path,
             joint_field: Path, threads: int = 3) -> dict:
    if output.exists():
        raise FileExistsError('Refusing to repeat the locked healthy test')
    release = json.loads((candidate/'source_evaluation.json').read_text())
    if not all(release['qualification_decision']['checks'].values()):
        raise ValueError('Candidate failed the predeclared source criteria')
    joint = json.loads(joint_field.read_text())
    if joint['model_sha256'] != release['model_sha256'] or joint['classifier_correct_and_leaf_pass'] < 31:
        raise ValueError('Candidate failed previous field non-regression; keep new test sealed')
    source_receipt = json.loads((source/'receipt.json').read_text())
    test = source/'test_locked.jsonl'
    if sha256(test) != source_receipt['manifest_sha256']['test_locked']:
        raise ValueError('Healthy test manifest differs from pinned source receipt')
    # Lock before reading its rows or pixels. An interrupted run needs review,
    # not an unnoticed retry/selection cycle.
    _exclusive_json(work_dir/'new_healthy_test_started.json', {
        'schema_version': 1, 'control_model_sha256': sha256(control/'crop_model.onnx'),
        'candidate_model_sha256': release['model_sha256'],
        'healthy_test_manifest_sha256': source_receipt['manifest_sha256']['test_locked'],
        'joint_old_field_report_sha256': sha256(joint_field),
        'criterion': 'candidate_visible_correct_and_leaf_pass > control; source criteria pass and old field non-regression'})
    rows = read_jsonl(test)
    if len(rows) != 14 or any(row['label_id'] != 'maize_healthy' or row['label_index'] != 3 for row in rows):
        raise ValueError('Only the frozen 14-image maize Healthy test is eligible')
    for row in rows:
        if hashlib.sha256(Path(row['local_path']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Healthy test image bytes differ from manifest')
    baseline = _bundle_result(control, rows, threads)
    trained = _bundle_result(candidate, rows, threads)
    report = {'schema_version': 1, 'source_commit': source_receipt['source_commit'],
              'source_receipt_sha256': sha256(source/'receipt.json'),
              'healthy_test_manifest_sha256': source_receipt['manifest_sha256']['test_locked'],
              'control': baseline, 'candidate': trained,
              'visible_correct_gain': trained['visible_correct_and_leaf_pass']-baseline['visible_correct_and_leaf_pass'],
              'passes_predeclared_healthy_visibility_improvement': trained['visible_correct_and_leaf_pass'] > baseline['visible_correct_and_leaf_pass'],
              'field_diagnosis_validated': False,
              'limitations': ['Fourteen Healthy-only field photos are too few for disease accuracy claims.',
                              'The dataset-provided Healthy label has not been independently expert reviewed.',
                              'The older PlantDoc external benchmark was reused for non-regression and is not a fresh blind field test.']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--joint-field', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threads', type=int, default=3)
    args = parser.parse_args(argv)
    print(json.dumps(evaluate(args.control, args.candidate, args.work_dir, args.source,
                              args.output, args.joint_field, args.threads), indent=2))


if __name__ == '__main__':
    main()
