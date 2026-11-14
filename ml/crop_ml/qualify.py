"""Two-phase, exact-artifact source qualification; field diagnosis stays false.

``fit`` reads train features and calibration images only. ``finalize`` is an
explicit, exclusive one-time full-source-test operation. Importing this module
does not run inference. Temporary arrays/checkpoints stay outside the checkout.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time

import numpy as np

from .acceptance import AcceptanceConfig, evaluate_source_acceptance, fit_source_acceptance
from .common import labels, read_jsonl, sha256, write_json, write_jsonl

CRITERIA = {'accuracy_min': 0.85, 'macro_f1_min': 0.80,
            'accepted_precision_min': 0.90, 'coverage_min': 0.30}
DISTANCE_QUANTILE = 0.995


def canonical_sha256(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                         allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _exclusive_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')


def normalize_embeddings(embeddings) -> np.ndarray:
    values = np.asarray(embeddings, dtype=np.float64)
    if values.ndim != 2 or not len(values) or not np.isfinite(values).all():
        raise ValueError('Embeddings must be a finite, nonempty [samples, dimension] array')
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if (norms <= 1e-12).any():
        raise ValueError('Zero-length embeddings cannot support a centroid-distance gate')
    return values/norms


def fit_train_centroids(embeddings, targets, label_ids) -> dict:
    """No calibration/test features enter centroid fitting."""
    values = normalize_embeddings(embeddings)
    truth = np.asarray(targets)
    if truth.shape != (len(values),) or not np.issubdtype(truth.dtype, np.integer):
        raise ValueError('Integer training labels must match embeddings')
    if not ((truth >= 0) & (truth < len(label_ids))).all():
        raise ValueError('Training label outside label contract')
    means, counts = [], {}
    for index, label in enumerate(label_ids):
        subset = values[truth == index]
        if not len(subset):
            raise ValueError(f'No train centroid support for {label}')
        means.append(subset.mean(axis=0))
        counts[label] = len(subset)
    centroids = normalize_embeddings(np.asarray(means))
    return {'schema_version': 1, 'label_ids': list(label_ids),
            'embedding_dimension': values.shape[1], 'centroids': centroids.tolist(),
            'normalization': 'l2_per_embedding_mean_then_l2_centroid',
            'distance': 'l2_unit_embedding_to_predicted_class_centroid',
            'train_samples': len(values), 'train_class_counts': counts,
            'unknown_detection_validated': False}


def predicted_centroid_distances(embeddings, predicted, centroids) -> np.ndarray:
    values = normalize_embeddings(embeddings)
    centers = np.asarray(centroids, dtype=np.float64)
    predicted = np.asarray(predicted)
    if centers.ndim != 2 or centers.shape[1] != values.shape[1] or not np.isfinite(centers).all():
        raise ValueError('Centroid dimension/values differ from model embeddings')
    if not np.allclose(np.linalg.norm(centers, axis=1), 1, atol=1e-6):
        raise ValueError('Centroids must be unit length')
    if predicted.shape != (len(values),) or not np.issubdtype(predicted.dtype, np.integer):
        raise ValueError('Predicted labels must match embeddings')
    if not ((predicted >= 0) & (predicted < len(centers))).all():
        raise ValueError('Predicted label outside centroids')
    return np.linalg.norm(values-centers[predicted], axis=1)


def add_calibration_distance_gate(policy, cal_logits, cal_embeddings, truth, groups, centroids):
    """Fit distances on correct CAL predictions, then audit the combined CAL gate."""
    result = deepcopy(policy)
    predicted = np.asarray(cal_logits).argmax(axis=1)
    truth = np.asarray(truth)
    distances = predicted_centroid_distances(cal_embeddings, predicted, centroids)
    names = result['label_ids']
    for index, label in enumerate(names):
        row = result['class_thresholds'][label]
        correct = (predicted == index) & (truth == index)
        support = int(correct.sum())
        row['calibration_correct_distance_support'] = support
        if row['enabled']:
            if support < result['selection_config']['minimum_class_accepted']:
                row.update(enabled=False, reason='Insufficient correct CAL support for centroid-distance quantile')
            else:
                row['max_embedding_distance'] = float(np.quantile(distances[correct], DISTANCE_QUANTILE, method='linear'))
                row['embedding_distance_quantile'] = DISTANCE_QUANTILE
    result['source_acceptance_enabled'] = any(r['enabled'] for r in result['class_thresholds'].values())
    report = evaluate_source_acceptance(cal_logits, truth, result, names, group_ids=groups,
                                        embedding_distances=distances)
    # The distance cutoff may remove correct examples; don't retain an enabled
    # class that no longer meets the predeclared CAL support/precision criterion.
    disabled = False
    for label, evidence in report['per_class'].items():
        row = result['class_thresholds'][label]
        if row['enabled'] and (evidence['accepted_predictions'] < result['selection_config']['minimum_class_accepted']
                               or evidence['accepted_precision'] is None
                               or evidence['accepted_precision']+1e-12 < result['selection_config']['target_precision']):
            row.update(enabled=False, reason='Combined score/margin/distance gate has insufficient CAL support or precision')
            disabled = True
    result['source_acceptance_enabled'] = any(r['enabled'] for r in result['class_thresholds'].values())
    if disabled:
        report = evaluate_source_acceptance(cal_logits, truth, result, names, group_ids=groups,
                                            embedding_distances=distances)
    result['calibration_report'] = report
    result['distance_gate'] = {'enabled': True, 'fit_partition': 'train_centroids_and_correct_CAL_distance_quantiles',
                               'distance_quantile': DISTANCE_QUANTILE, 'unknown_detection_validated': False,
                               'limitation': 'Source feature-distance heuristic only. No measured unknown-plant or field-photo rejection guarantee.'}
    return result


def qualification_decision(test_report: dict, criteria: dict = CRITERIA) -> dict:
    checks = {
        'accuracy': test_report['accuracy'] >= criteria['accuracy_min'],
        'macro_f1_all_labels': test_report['macro_f1_all_labels'] >= criteria['macro_f1_min'],
        'accepted_precision': test_report['accepted_precision'] is not None and test_report['accepted_precision'] >= criteria['accepted_precision_min'],
        'coverage': test_report['coverage'] >= criteria['coverage_min'],
    }
    return {'source_acceptance_qualified': all(checks.values()), 'criteria': dict(criteria), 'checks': checks,
            'failure_reasons': [name for name, passed in checks.items() if not passed]}


def _load_bundle(bundle: Path):
    metadata = json.loads((bundle/'model_metadata.json').read_text())
    actual_hash = sha256(bundle/'crop_model.onnx')
    if actual_hash != metadata['model_sha256']:
        raise ValueError('Export metadata model SHA differs from actual ONNX bytes')
    contract = json.loads((bundle/'labels.json').read_text())['labels']
    if contract != labels():
        raise ValueError('Bundle labels differ from stable repository contract')
    expected = {'name': 'image', 'dtype': 'float32', 'shape': [1, 3, 224, 224],
                'width': 224, 'height': 224, 'layout': 'NCHW', 'color_order': 'RGB',
                'resize': 'letterbox', 'resize_rounding': 'half_up', 'interpolation': 'bilinear',
                'padding_rgb': [124, 116, 104], 'mean': [.485, .456, .406], 'std': [.229, .224, .225],
                'pixel_scale': 255.0, 'exif_orientation': True}
    if metadata.get('architecture') != 'MobileNetV4-Conv-Small' or metadata.get('embedding_dimension') != 960:
        raise ValueError('Only the actual V4-Conv-Small/960 embedding contract is supported')
    if metadata.get('class_count') != 17 or metadata.get('model_file') != 'crop_model.onnx':
        raise ValueError('Model file or class count differs from the bundle contract')
    if metadata.get('outputs') != {'logits': {'name': 'logits', 'shape': [1, 17]},
                                   'embeddings': {'name': 'embeddings', 'shape': [1, 960]}}:
        raise ValueError('Declared model outputs differ from supported inference contract')
    for key, value in expected.items():
        if metadata['input'].get(key) != value:
            raise ValueError(f'Unsupported preprocessing contract: {key}')
    if metadata.get('diagnosis_validated'):
        raise ValueError('This qualification is source-only, not a field-validation workflow')
    return metadata, contract


def _protocol(directory: Path):
    path = directory/'protocol_receipt.json'
    receipt = json.loads(path.read_text())
    source_path = Path(receipt['source_split_manifest'])
    if sha256(source_path) != receipt['source_split_sha256']:
        raise ValueError('Original source split has changed')
    for role in ['tune', 'calibration', 'test_locked']:
        item = receipt['files'][role]
        if sha256(Path(item['path'])) != item['sha256']:
            raise ValueError(f'Frozen {role} manifest has changed')
    return receipt, sha256(path)


def _field_protocol(directory: Path | None):
    if directory is None:
        return None, None
    path = directory/'partition_receipt.json'
    receipt = json.loads(path.read_text())
    for role in ['train', 'tune', 'calibration', 'external_test_locked']:
        item = receipt['files'][role]
        file_path = directory/item['file']
        if sha256(file_path) != item['sha256']:
            raise ValueError(f'Frozen PlantDoc {role} manifest has changed')
        if len(read_jsonl(file_path)) != item['rows']:
            raise ValueError(f'PlantDoc {role} manifest has a different row count')
    return receipt, sha256(path)


def _field_rows(directory, receipt, role):
    return read_jsonl(directory/receipt['files'][role]['file'])


def _infer_rows(bundle: Path, rows: list[dict], threads: int, role: str):
    """Only invoked by an explicit fit/finalize command, never at import time."""
    import onnxruntime as ort
    from PIL import Image
    from .model import prepare_image
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(bundle/'crop_model.onnx'), options, providers=['CPUExecutionProvider'])
    logits = np.empty((len(rows), 17), dtype=np.float32)
    embeddings = np.empty((len(rows), 960), dtype=np.float32)
    elapsed = []
    started = time.monotonic()
    for index, row in enumerate(rows):
        with Image.open(row['local_path']) as image:
            tensor = prepare_image(image)[None]
        tick = time.monotonic()
        scores, features = session.run(['logits', 'embeddings'], {'image': tensor})
        elapsed.append((time.monotonic()-tick)*1000)
        if scores.shape != (1, 17) or features.shape != (1, 960):
            raise ValueError('Actual ONNX output shapes differ from declared contract')
        if not np.isfinite(scores).all() or not np.isfinite(features).all():
            raise ValueError('Non-finite actual ONNX output')
        logits[index], embeddings[index] = scores[0], features[0]
        if (index+1) % 500 == 0:
            print(json.dumps({'phase': role, 'completed': index+1, 'samples': len(rows)}, separators=(',', ':')), flush=True)
    return logits, embeddings, {'samples': len(rows), 'elapsed_seconds': time.monotonic()-started,
                                 'desktop_inference_only_latency_ms': {'p50': float(np.median(elapsed)), 'p95': float(np.percentile(elapsed, 95))},
                                 'phone_benchmark_executed': False}


def _save_predictions(path: Path, rows, logits, embeddings):
    np.savez(path, logits=logits, embeddings=embeddings,
             labels=np.array([r['label_index'] for r in rows], dtype=np.int64),
             image_sha256=np.array([r['sha256'] for r in rows]),
             group_ids=np.array([r['group_id'] for r in rows]))


def fit_bundle(bundle: Path, protocol_dir: Path, work_dir: Path, threads=3, *,
               field_protocol_dir: Path | None = None, include_field_train=False) -> dict:
    metadata, label_contract = _load_bundle(bundle)
    protocol, protocol_hash = _protocol(protocol_dir)
    field_protocol, field_hash = _field_protocol(field_protocol_dir)
    training_receipt_path = bundle/'training_receipt.json'
    training_receipt = json.loads(training_receipt_path.read_text()) if training_receipt_path.exists() else {}
    if include_field_train and field_protocol is None:
        raise ValueError('--include-field-train requires --field-protocol')
    if bool(training_receipt.get('field_training_used', False)) != bool(include_field_train):
        raise ValueError('Field train centroid inclusion must match selected model training provenance')
    if include_field_train and training_receipt.get('field_train_manifest_sha256') != field_protocol['files']['train']['sha256']:
        raise ValueError('Selected model used a different field training manifest')
    work_dir.mkdir(parents=True, exist_ok=True)
    if (work_dir/'fit_started.json').exists():
        raise FileExistsError('Fit already started in this directory; do not silently repeat CAL selection')
    identity = {'schema_version': 1, 'model_version': metadata['model_version'], 'model_sha256': metadata['model_sha256'],
                'protocol_sha256': protocol_hash, 'predeclared_source_test_criteria': CRITERIA,
                'field_protocol_sha256': field_hash, 'field_training_used': bool(include_field_train),
                'field_train_manifest_sha256': field_protocol['files']['train']['sha256'] if include_field_train else None,
                'distance_quantile': DISTANCE_QUANTILE, 'started_at': _utc()}
    _exclusive_json(work_dir/'fit_started.json', identity)
    train = [r for r in read_jsonl(Path(protocol['source_split_manifest'])) if r['split'] == 'train']
    calibration = read_jsonl(Path(protocol['files']['calibration']['path']))
    assert len(train) == protocol['source_counts']['train']
    source_train_count, source_cal_count = len(train), len(calibration)
    if field_protocol is not None:
        field_calibration = _field_rows(field_protocol_dir, field_protocol, 'calibration')
        if include_field_train:
            train += _field_rows(field_protocol_dir, field_protocol, 'train')
        calibration += field_calibration
    # Exact hashes are also checked across datasets; namespaced group IDs alone
    # would not detect an identical PlantVillage image in a second source.
    assert {r['sha256'] for r in train}.isdisjoint(r['sha256'] for r in calibration)
    assert {r['group_id'] for r in train}.isdisjoint(r['group_id'] for r in calibration)
    write_jsonl(work_dir/'calibration_combined.jsonl', calibration)
    combined_cal_hash = sha256(work_dir/'calibration_combined.jsonl')
    names = [r['id'] for r in label_contract]
    train_logits, train_features, train_timing = _infer_rows(bundle, train, threads, 'train_centroids')
    centroids = fit_train_centroids(train_features, np.array([r['label_index'] for r in train]), names)
    centroids.update(model_version=metadata['model_version'], model_sha256=metadata['model_sha256'],
                     scope='source_domain_only', source_split_sha256=protocol['source_split_sha256'],
                     train_domain_counts={'plantvillage': source_train_count, 'plantdoc_field_like': len(train)-source_train_count},
                     field_train_manifest_sha256=identity['field_train_manifest_sha256'])
    write_json(work_dir/'embedding_centroids.json', centroids)
    del train_logits, train_features
    cal_logits, cal_features, cal_timing = _infer_rows(bundle, calibration, threads, 'calibration')
    truth = np.array([r['label_index'] for r in calibration], dtype=np.int64)
    groups = [r['group_id'] for r in calibration]
    policy = fit_source_acceptance(cal_logits, truth, names, model_sha256=metadata['model_sha256'],
                                    calibration_manifest_sha256=combined_cal_hash,
                                    group_ids=groups, config=AcceptanceConfig())
    policy = add_calibration_distance_gate(policy, cal_logits, cal_features, truth, groups, centroids['centroids'])
    cal_distances = predicted_centroid_distances(cal_features, cal_logits.argmax(axis=1), centroids['centroids'])
    calibration_domains = {}
    for domain, region in [('plantvillage', slice(0, source_cal_count)),
                            ('plantdoc_field_like', slice(source_cal_count, len(calibration)))]:
        if len(truth[region]):
            calibration_domains[domain] = evaluate_source_acceptance(cal_logits[region], truth[region], policy,
                names, group_ids=groups[region], embedding_distances=cal_distances[region])
    policy['distance_gate']['correct_distance_support_by_domain'] = {
        domain: {label: report['per_class'][label]['raw_correct'] for label in names}
        for domain, report in calibration_domains.items()
    }
    policy.update(model_version=metadata['model_version'], source_evaluated=False, source_acceptance_qualified=False,
                  thresholds_calibrated=False, allow_condition_specific_advice=False,
                  embedding_centroids_file='embedding_centroids.json',
                  embedding_centroids_sha256=sha256(work_dir/'embedding_centroids.json'))
    write_json(work_dir/'candidate_policy.json', policy)
    _save_predictions(work_dir/'calibration_predictions.npz', calibration, cal_logits, cal_features)
    receipt = {**identity, 'completed_at': _utc(), 'fit_partitions': {'train': len(train), 'calibration': len(calibration)},
               'fit_domain_counts': {'train': {'plantvillage': source_train_count, 'plantdoc_field_like': len(train)-source_train_count},
                                     'calibration': {'plantvillage': source_cal_count, 'plantdoc_field_like': len(calibration)-source_cal_count}},
               'combined_calibration_manifest_sha256': combined_cal_hash,
               'candidate_policy_sha256': sha256(work_dir/'candidate_policy.json'),
               'thresholds_sha256': canonical_sha256(policy['class_thresholds']),
               'embedding_centroids_sha256': sha256(work_dir/'embedding_centroids.json'),
               'calibration_predictions_sha256': sha256(work_dir/'calibration_predictions.npz'),
               'train_centroids_execution': train_timing, 'calibration_execution': cal_timing,
               'test_evaluated': False, 'source_acceptance_qualified': False, 'diagnosis_validated': False,
               'calibration_report': policy['calibration_report'], 'calibration_domains': calibration_domains,
               'field_protocol': field_protocol}
    write_json(work_dir/'fit_receipt.json', receipt)
    return receipt


def finalize_bundle(bundle: Path, protocol_dir: Path, work_dir: Path, threads=3, *,
                    field_protocol_dir: Path | None = None) -> dict:
    metadata, label_contract = _load_bundle(bundle)
    protocol, protocol_hash = _protocol(protocol_dir)
    field_protocol, field_hash = _field_protocol(field_protocol_dir)
    fit_receipt = json.loads((work_dir/'fit_receipt.json').read_text())
    if fit_receipt['model_sha256'] != metadata['model_sha256'] or fit_receipt['model_version'] != metadata['model_version']:
        raise ValueError('Model identity changed after CAL fitting')
    if fit_receipt['protocol_sha256'] != protocol_hash or fit_receipt['predeclared_source_test_criteria'] != CRITERIA:
        raise ValueError('Protocol or predeclared criteria changed after CAL fitting')
    if fit_receipt.get('field_protocol_sha256') != field_hash:
        raise ValueError('PlantDoc protocol changed or differs from the predeclared CAL mixture')
    for name, key in [('candidate_policy.json', 'candidate_policy_sha256'), ('embedding_centroids.json', 'embedding_centroids_sha256')]:
        if sha256(work_dir/name) != fit_receipt[key]:
            raise ValueError(f'Frozen {name} changed after CAL fitting')
    policy = json.loads((work_dir/'candidate_policy.json').read_text())
    centroids = json.loads((work_dir/'embedding_centroids.json').read_text())
    if canonical_sha256(policy['class_thresholds']) != fit_receipt['thresholds_sha256']:
        raise ValueError('Frozen class thresholds changed')
    # Exclusive stamp precedes any test image inference. An interrupted run needs
    # explicit review, never an unnoticed second test/threshold-selection cycle.
    _exclusive_json(work_dir/'test_started.json', {'started_at': _utc(), 'model_sha256': metadata['model_sha256'],
                    'candidate_policy_sha256': fit_receipt['candidate_policy_sha256'],
                    'test_manifest_sha256': protocol['files']['test_locked']['sha256'], 'criteria': CRITERIA,
                    'external_field_manifest_sha256': field_protocol['files']['external_test_locked']['sha256'] if field_protocol else None})
    test = read_jsonl(Path(protocol['files']['test_locked']['path']))
    if len(test) != protocol['source_counts']['test'] or any(r['split'] != 'test' for r in test):
        raise ValueError('Final test is not the original full source-test partition')
    test_logits, test_features, timing = _infer_rows(bundle, test, threads, 'final_source_test')
    distances = predicted_centroid_distances(test_features, test_logits.argmax(axis=1), centroids['centroids'])
    source_test = evaluate_source_acceptance(test_logits, np.array([r['label_index'] for r in test]), policy,
                                             [r['id'] for r in label_contract], group_ids=[r['group_id'] for r in test],
                                             model_sha256=metadata['model_sha256'], embedding_distances=distances)
    source_test.update(manifest_sha256=protocol['files']['test_locked']['sha256'],
                       full_original_source_test=True, execution=timing,
                       class_counts=dict(Counter(r['label_id'] for r in test)))
    # Preserve source outcomes before the separate external-domain evaluation;
    # a later failure must not invite an unnoticed second source-test run.
    write_json(work_dir/'source_test_report.json', source_test)
    _save_predictions(work_dir/'source_test_predictions.npz', test, test_logits, test_features)
    external_field_test = None
    if field_protocol is not None:
        external = _field_rows(field_protocol_dir, field_protocol, 'external_test_locked')
        external_logits, external_features, external_timing = _infer_rows(bundle, external, threads, 'external_field_like_test')
        external_distances = predicted_centroid_distances(external_features, external_logits.argmax(axis=1), centroids['centroids'])
        external_field_test = evaluate_source_acceptance(external_logits, np.array([r['label_index'] for r in external]), policy,
            [r['id'] for r in label_contract], group_ids=[r['group_id'] for r in external],
            model_sha256=metadata['model_sha256'], embedding_distances=external_distances)
        external_field_test.update(manifest_sha256=field_protocol['files']['external_test_locked']['sha256'],
            domain='plantdoc_internet_field_like', execution=external_timing,
            class_counts=dict(Counter(r['label_id'] for r in external)),
            label_status=field_protocol['label_status'],
            qualification_criterion=False, field_diagnosis_validated=False,
            limitation='Small separate internet-sourced, field-like benchmark with source-label mappings not reviewed by an agricultural expert. It is not a farmer field trial and is never pooled with PlantVillage accuracy.')
        write_json(work_dir/'external_field_test_report.json', external_field_test)
        _save_predictions(work_dir/'external_field_test_predictions.npz', external, external_logits, external_features)
    decision = qualification_decision(source_test, fit_receipt['predeclared_source_test_criteria'])
    qualified = decision['source_acceptance_qualified'] and policy['source_acceptance_enabled']
    receipt = {'schema_version': 1, 'model_version': metadata['model_version'], 'model_sha256': metadata['model_sha256'],
               'scope': 'source_domain_only', 'source_evaluated': True, 'source_acceptance_qualified': qualified,
               'thresholds_sha256': fit_receipt['thresholds_sha256'], 'class_thresholds': policy['class_thresholds'],
               'frozen_policy': {'temperature': policy['temperature'], 'class_thresholds': deepcopy(policy['class_thresholds'])},
               'thresholds_hash_encoding': 'UTF-8 JSON, sorted object keys, compact separators, ensure_ascii=false',
               'temperature': policy['temperature'], 'embedding_centroids_sha256': fit_receipt['embedding_centroids_sha256'],
               'calibration_report': policy['calibration_report'], 'temperature_fit': policy['temperature_fit'],
               'calibration_domains': fit_receipt['calibration_domains'], 'calibration_domain_counts': fit_receipt['fit_domain_counts']['calibration'],
               'source_test': source_test, 'qualification_decision': decision,
               'external_field_test': external_field_test, 'field_protocol': field_protocol,
               'field_protocol_sha256': field_hash,
               'fit_receipt_sha256': sha256(work_dir/'fit_receipt.json'), 'protocol_sha256': protocol_hash,
               'source_protocol': protocol, 'completed_at': _utc(),
               'unknown_detection_validated': False, 'field_trial_executed': False, 'diagnosis_validated': False,
               'limitations': protocol['boundaries'] + [
                   'Acceptance criteria are observed full-source-test metrics, not lower-confidence-bound guarantees.',
                   'Centroid distance is fitted to training and correct CAL features only; unknown-image rejection was not validated.',
                   'Source photos largely show isolated leaves. No field-photo, symptom-severity, treatment, or physical-phone performance claim follows.']}
    write_json(work_dir/'source_evaluation.json', receipt)
    bundle.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(work_dir/'source_evaluation.json', bundle/'source_evaluation.json')
    shutil.copyfile(work_dir/'embedding_centroids.json', bundle/'embedding_centroids.json')
    final_policy = json.loads((bundle/'decision_policy.json').read_text())
    final_policy.update({k: v for k, v in policy.items() if k != 'calibration_report'})
    final_policy.update(validated=False, diagnosis_validated=False, thresholds_calibrated=False,
                         source_evaluated=True, source_thresholds_calibrated=True,
                         source_acceptance_qualified=qualified, source_acceptance_enabled=qualified,
                         calibration_source_acceptance_enabled=policy['source_acceptance_enabled'],
                         source_evaluation_file='source_evaluation.json',
                         source_evaluation_sha256=sha256(bundle/'source_evaluation.json'),
                         allow_condition_specific_advice=False,
                         reason='SOURCE_ACCEPTANCE_QUALIFIED' if qualified else 'SOURCE_CRITERIA_NOT_MET',
                         validation_status='source_tested_prototype' if qualified else 'source_criteria_not_met',
                         note='Source-tested prototype only; field diagnosis and chemical prescriptions remain unvalidated.')
    metadata.update(diagnosis_validated=False, source_evaluated=True, source_thresholds_calibrated=True,
                     source_acceptance_qualified=qualified, source_acceptance_enabled=qualified,
                     source_evaluation_file='source_evaluation.json', source_evaluation_sha256=final_policy['source_evaluation_sha256'],
                     test_scope='Full original source-domain test with frozen CAL gates; no field diagnosis or phone-performance validation.')
    write_json(bundle/'decision_policy.json', final_policy)
    write_json(bundle/'model_metadata.json', metadata)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['fit', 'finalize'])
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, default=Path('/workspace/crop-artifacts/full_validation_protocol'))
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--threads', type=int, default=3)
    parser.add_argument('--field-protocol', type=Path,
                        help='Optional frozen PlantDoc partitions: append CAL and report locked external test separately')
    parser.add_argument('--include-field-train', action='store_true',
                        help='Fit phase only; append field TRAIN centroids when the selected training receipt proves mixed training')
    args = parser.parse_args(argv)
    if args.threads < 1:
        parser.error('--threads must be positive')
    if args.phase == 'fit':
        result = fit_bundle(args.bundle, args.protocol, args.work_dir, args.threads,
                            field_protocol_dir=args.field_protocol, include_field_train=args.include_field_train)
    else:
        if args.include_field_train:
            parser.error('--include-field-train applies only to fit; finalize uses frozen fit provenance')
        result = finalize_bundle(args.bundle, args.protocol, args.work_dir, args.threads,
                                 field_protocol_dir=args.field_protocol)
    print(json.dumps({'phase': args.phase, 'model_sha256': result['model_sha256'],
                      'source_acceptance_qualified': result['source_acceptance_qualified'],
                      'report': str(args.work_dir/('fit_receipt.json' if args.phase == 'fit' else 'source_evaluation.json'))}, indent=2))


if __name__ == '__main__':
    main()
