import copy
import json

import numpy as np
import pytest

from crop_ml.acceptance import evaluate_source_acceptance, fit_source_acceptance
from crop_ml.qualify import (
    CRITERIA,
    _exclusive_json,
    add_calibration_distance_gate,
    canonical_sha256,
    fit_train_centroids,
    normalize_embeddings,
    predicted_centroid_distances,
    qualification_decision,
)
from crop_ml.common import sha256, write_json, write_jsonl
import crop_ml.qualify as qualify


def test_train_centroids_use_unit_embeddings_and_preserve_label_order():
    result = fit_train_centroids([[20, 0], [2, 0], [0, 3], [0, 30]], np.array([0, 0, 1, 1]), ['a', 'b'])
    np.testing.assert_allclose(result['centroids'], [[1, 0], [0, 1]])
    assert result['train_class_counts'] == {'a': 2, 'b': 2}
    assert result['unknown_detection_validated'] is False
    distances = predicted_centroid_distances([[100, 0], [-3, 0], [0, 8]], np.array([0, 0, 1]), result['centroids'])
    np.testing.assert_allclose(distances, [0, 2, 0])


def test_zero_and_invalid_embeddings_do_not_manufacture_distances():
    with pytest.raises(ValueError, match='Zero-length'):
        normalize_embeddings([[0, 0]])
    with pytest.raises(ValueError, match='finite'):
        normalize_embeddings([[np.nan, 0]])
    with pytest.raises(ValueError, match='unit length'):
        predicted_centroid_distances([[1, 0]], np.array([0]), [[2, 0]])
    with pytest.raises(ValueError, match='No train centroid support'):
        fit_train_centroids([[1, 0]], np.array([0]), ['a', 'b'])


def test_frozen_distance_gate_rejects_far_features_even_with_high_confidence():
    logits = np.array([[8., 0.]]*12+[[0., 8.]]*12)
    truth = np.array([0]*12+[1]*12)
    features = np.array([[1., 0.]]*12+[[0., 1.]]*12)
    policy = fit_source_acceptance(logits, truth, ['a', 'b'], model_sha256='a'*64,
                                    calibration_manifest_sha256='b'*64)
    original = copy.deepcopy(policy)
    gated = add_calibration_distance_gate(policy, logits, features, truth,
                                          [str(i) for i in range(24)], [[1., 0.], [0., 1.]])
    assert policy == original
    assert gated['calibration_report']['coverage'] == 1
    assert gated['distance_gate']['unknown_detection_validated'] is False
    report = evaluate_source_acceptance(np.array([[100., 0.]]), np.array([0]), gated,
                                         ['a', 'b'], embedding_distances=np.array([2.]))
    assert report['uncertain_predictions'] == 1
    assert report['accepted_predictions'] == 0
    with pytest.raises(ValueError, match='requires predicted-class embedding distances'):
        evaluate_source_acceptance(np.array([[100., 0.]]), np.array([0]), gated, ['a', 'b'])


def test_combined_distance_gate_does_not_keep_a_class_with_less_than_five_cases():
    logits = np.array([[8., 0.]]*5+[[0., 8.]]*10)
    truth = np.array([0]*5+[1]*10)
    features = np.array([[1., 0.]]*4+[[-1., 0.]]+[[0., 1.]]*10)
    policy = fit_source_acceptance(logits, truth, ['a', 'b'], model_sha256='a'*64,
                                    calibration_manifest_sha256='b'*64)
    assert policy['class_thresholds']['a']['enabled']
    gated = add_calibration_distance_gate(policy, logits, features, truth,
                                          [str(i) for i in range(15)], [[1., 0.], [0., 1.]])
    assert not gated['class_thresholds']['a']['enabled']
    assert gated['calibration_report']['per_class']['a']['accepted_predictions'] == 0


def test_predeclared_qualification_checks_report_each_failure_without_adjustment():
    good = {'accuracy': .85, 'macro_f1_all_labels': .80, 'accepted_precision': .90, 'coverage': .30}
    assert qualification_decision(good)['source_acceptance_qualified']
    for key in good:
        bad = dict(good, **{key: good[key]-.001})
        result = qualification_decision(bad)
        assert not result['source_acceptance_qualified']
        assert result['failure_reasons'] == [key]
        assert result['criteria'] == CRITERIA
    assert not qualification_decision(dict(good, accepted_precision=None))['source_acceptance_qualified']


def test_model_bound_freeze_hash_detects_numerical_changes_and_ignores_key_order():
    a = {'temperature': .8, 'class_thresholds': {'a': {'enabled': True, 'minimum_confidence': .9}}}
    b = {'class_thresholds': a['class_thresholds'], 'temperature': .8}
    assert canonical_sha256(a) == canonical_sha256(b)
    b['temperature'] = .81
    assert canonical_sha256(a) != canonical_sha256(b)


def test_exclusive_test_stamp_prevents_silent_second_evaluation(tmp_path):
    path = tmp_path/'test_started.json'
    _exclusive_json(path, {'model_sha256': 'a'*64})
    with pytest.raises(FileExistsError):
        _exclusive_json(path, {'model_sha256': 'b'*64})
    assert json.loads(path.read_text()) == {'model_sha256': 'a'*64}


def small_protocols(tmp_path, monkeypatch, *, mixed=False):
    """Pure orchestration fixture: inference is replaced; no image/model is used."""
    bundle, protocol_dir, field_dir, work = [tmp_path/n for n in ['bundle', 'source_protocol', 'field_protocol', 'work']]
    for directory in [bundle, protocol_dir, field_dir]:
        directory.mkdir()
    def rows(name, count, split):
        return [{'label_index': i % 2, 'label_id': ['a', 'b'][i % 2], 'split': split,
                 'sha256': f'{name}_{i}', 'group_id': f'{name}_leaf_{i}'} for i in range(count)]
    train, tune, cal, test = rows('pv_train', 4, 'train'), rows('pv_tune', 2, 'validation'), rows('pv_cal', 24, 'validation'), rows('pv_test', 4, 'test')
    source = tmp_path/'source.jsonl'
    write_jsonl(source, train+tune+cal+test)
    files = {}
    for name, members in [('tune', tune), ('calibration', cal), ('test_locked', test)]:
        path = protocol_dir/f'{name}.jsonl'
        write_jsonl(path, members)
        files[name] = {'path': str(path), 'sha256': sha256(path), 'images': len(members)}
    write_json(protocol_dir/'protocol_receipt.json', {'source_split_manifest': str(source), 'source_split_sha256': sha256(source),
        'files': files, 'source_counts': {'train': len(train), 'test': len(test)}, 'boundaries': ['Synthetic unit-test fixture only.']})
    field_files = {}
    for name, count in [('train', 4), ('tune', 2), ('calibration', 12), ('external_test_locked', 4)]:
        path = field_dir/f'{name}.jsonl'
        write_jsonl(path, rows(f'field_{name}', count, name))
        field_files[name] = {'file': path.name, 'sha256': sha256(path), 'rows': count}
    write_json(field_dir/'partition_receipt.json', {'files': field_files, 'label_status': 'Unreviewed synthetic labels.'})
    metadata = {'model_version': 'synthetic_unit_test', 'model_sha256': 'a'*64}
    write_json(bundle/'decision_policy.json', {'validated': False, 'thresholds_calibrated': False})
    write_json(bundle/'model_metadata.json', metadata)
    write_json(bundle/'training_receipt.json', {'field_training_used': mixed,
        'field_train_manifest_sha256': field_files['train']['sha256'] if mixed else None})
    monkeypatch.setattr(qualify, '_load_bundle', lambda _: (dict(metadata), [{'id': 'a'}, {'id': 'b'}]))
    calls = []
    def infer(_, members, threads, role):
        calls.append((role, len(members)))
        truth = np.array([row['label_index'] for row in members])
        # External results are deliberately wrong to prove they remain visible,
        # separate from source qualification, and never tune the frozen policy.
        predicted = 1-truth if role == 'external_field_like_test' else truth
        logits = np.array([[8., 0.] if x == 0 else [0., 8.] for x in predicted])
        features = np.array([[1., 0.] if x == 0 else [0., 1.] for x in predicted])
        return logits, features, {'samples': len(members)}
    monkeypatch.setattr(qualify, '_infer_rows', infer)
    return bundle, protocol_dir, field_dir, work, calls


def test_two_phase_fit_never_reads_test_and_finalization_keeps_domains_separate(tmp_path, monkeypatch):
    bundle, protocol_dir, field_dir, work, calls = small_protocols(tmp_path, monkeypatch)
    fit = qualify.fit_bundle(bundle, protocol_dir, work, field_protocol_dir=field_dir)
    assert calls == [('train_centroids', 4), ('calibration', 36)]
    assert fit['fit_domain_counts']['calibration'] == {'plantvillage': 24, 'plantdoc_field_like': 12}
    assert fit['calibration_domains']['plantvillage']['samples'] == 24
    assert fit['calibration_domains']['plantdoc_field_like']['samples'] == 12
    assert not (work/'test_started.json').exists()
    candidate = json.loads((work/'candidate_policy.json').read_text())
    final = qualify.finalize_bundle(bundle, protocol_dir, work, field_protocol_dir=field_dir)
    assert calls[-2:] == [('final_source_test', 4), ('external_field_like_test', 4)]
    assert final['source_acceptance_qualified']
    assert final['source_test']['accuracy'] == 1
    assert final['external_field_test']['accuracy'] == 0
    assert final['external_field_test']['accepted_precision'] == 0
    assert not final['external_field_test']['qualification_criterion']
    packaged = json.loads((bundle/'decision_policy.json').read_text())
    assert packaged['source_acceptance_qualified'] and packaged['source_acceptance_enabled']
    assert not packaged['validated'] and not packaged['diagnosis_validated'] and not packaged['thresholds_calibrated']
    assert packaged['source_evaluation_sha256'] == sha256(bundle/'source_evaluation.json')
    assert final['frozen_policy'] == {'temperature': packaged['temperature'], 'class_thresholds': packaged['class_thresholds']}
    assert candidate == json.loads((work/'candidate_policy.json').read_text())
    prior_calls = list(calls)
    with pytest.raises(FileExistsError):
        qualify.finalize_bundle(bundle, protocol_dir, work, field_protocol_dir=field_dir)
    assert calls == prior_calls


def test_field_training_centroids_require_matching_selected_model_provenance(tmp_path, monkeypatch):
    bundle, protocol_dir, field_dir, work, calls = small_protocols(tmp_path, monkeypatch, mixed=True)
    with pytest.raises(ValueError, match='training provenance'):
        qualify.fit_bundle(bundle, protocol_dir, work, field_protocol_dir=field_dir)
    assert not calls
    receipt = qualify.fit_bundle(bundle, protocol_dir, work, field_protocol_dir=field_dir, include_field_train=True)
    assert calls[0] == ('train_centroids', 8)
    assert receipt['fit_domain_counts']['train'] == {'plantvillage': 4, 'plantdoc_field_like': 4}


def test_policy_mutation_after_calibration_blocks_test_inference(tmp_path, monkeypatch):
    bundle, protocol_dir, field_dir, work, calls = small_protocols(tmp_path, monkeypatch)
    qualify.fit_bundle(bundle, protocol_dir, work, field_protocol_dir=field_dir)
    candidate = json.loads((work/'candidate_policy.json').read_text())
    candidate['temperature'] *= 1.1
    write_json(work/'candidate_policy.json', candidate)
    with pytest.raises(ValueError, match='changed after CAL'):
        qualify.finalize_bundle(bundle, protocol_dir, work, field_protocol_dir=field_dir)
    assert calls == [('train_centroids', 4), ('calibration', 36)]
    assert not (work/'test_started.json').exists()
