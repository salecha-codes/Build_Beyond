import copy
import json

import numpy as np
import pytest

from crop_ml.acceptance import (
    AcceptanceConfig,
    evaluate_source_acceptance,
    fit_calibration_temperature,
    fit_source_acceptance,
    wilson_interval,
)


LABELS = ['condition_a', 'condition_b']
MODEL_SHA = 'a'*64
MANIFEST_SHA = 'b'*64


def fit(logits, targets, **kwargs):
    return fit_source_acceptance(logits, targets, LABELS,
                                 model_sha256=MODEL_SHA,
                                 calibration_manifest_sha256=MANIFEST_SHA, **kwargs)


def good_policy():
    logits = np.array([[6., 0.]]*10+[[0., 6.]]*10)
    return fit(logits, np.array([0]*10+[1]*10), group_ids=[f'leaf_{i//2}' for i in range(20)])


def test_cal_gate_keeps_field_validation_false_and_reports_small_support_bounds():
    policy = good_policy()
    assert policy['source_acceptance_enabled']
    assert not policy['diagnosis_validated'] and not policy['validated']
    assert policy['calibration_report']['accepted_precision'] == 1
    assert policy['calibration_report']['coverage'] == 1
    assert policy['calibration_report']['groups']['accepted_groups'] == 10
    assert policy['class_thresholds']['condition_a']['calibration_accepted_groups'] == 5
    # Perfect observed precision on ten cases is still a wide interval.
    assert policy['class_thresholds']['condition_a']['calibration_precision_wilson95'][0] < .8
    assert all(x['minimum_confidence'] > 0 and x['minimum_margin'] > 0
               for x in policy['class_thresholds'].values())
    json.dumps(policy, allow_nan=False)


def test_final_evaluation_preserves_bad_results_and_never_refits_policy():
    policy = good_policy()
    original = copy.deepcopy(policy)
    result = evaluate_source_acceptance(np.array([[100., 0.], [0., 100.]]),
                                        np.array([1, 0]), policy, LABELS, model_sha256=MODEL_SHA)
    assert result['accepted_errors'] == 2
    assert result['accepted_precision'] == 0
    assert result['coverage'] == 1
    assert policy == original
    assert not result['diagnosis_validated']


def test_insufficient_class_evidence_remains_uncertain_despite_high_logits():
    logits = np.array([[50., 0.]]*4+[[0., 50.]]*10)
    policy = fit(logits, np.array([0]*4+[1]*10))
    assert not policy['class_thresholds']['condition_a']['enabled']
    assert policy['class_thresholds']['condition_b']['enabled']
    assert policy['calibration_report']['accepted_predictions'] == 10
    assert policy['calibration_report']['uncertain_predictions'] == 4


def test_failed_calibration_never_enables_a_zero_threshold_fallback():
    policy = fit(np.array([[6., 0.]]*10), np.array([0, 1]*5))
    assert not policy['source_acceptance_enabled']
    assert all(not x['enabled'] for x in policy['class_thresholds'].values())
    assert policy['calibration_report']['coverage'] == 0
    assert policy['calibration_report']['accepted_precision'] is None
    assert policy['calibration_report']['accepted_precision_wilson95'] is None
    json.dumps(policy, allow_nan=False)


def test_temperature_fits_cal_nll_without_changing_ranking():
    logits = np.array([[5., -5.]]*8)
    targets = np.array([0, 1]*4)
    result = fit_calibration_temperature(logits, targets, LABELS)
    assert result['nll_after'] < result['nll_before']
    assert result['fit_partition'] == 'calibration_only'
    np.testing.assert_array_equal(logits.argmax(1), (logits/result['temperature']).argmax(1))


@pytest.mark.parametrize('bad', [np.nan, np.inf, -np.inf])
def test_nonfinite_logits_are_rejected(bad):
    with pytest.raises(ValueError, match='Non-finite'):
        fit(np.array([[bad, 0.]]), np.array([0]))


def test_exact_artifact_and_label_order_binding():
    policy = good_policy()
    x, y = np.array([[2., 0.]]), np.array([0])
    with pytest.raises(ValueError, match='SHA256'):
        evaluate_source_acceptance(x, y, policy, LABELS, model_sha256='c'*64)
    with pytest.raises(ValueError, match='label order'):
        evaluate_source_acceptance(x, y, policy, LABELS[::-1])
    policy['diagnosis_validated'] = True
    with pytest.raises(ValueError, match='diagnosis validation'):
        evaluate_source_acceptance(x, y, policy, LABELS)


def test_no_zero_threshold_or_too_small_support_configuration():
    with pytest.raises(ValueError, match='positive'):
        AcceptanceConfig(confidence_grid=(0.0,))
    with pytest.raises(ValueError, match='five'):
        AcceptanceConfig(minimum_class_accepted=1)
    policy = good_policy()
    policy['class_thresholds']['condition_a']['minimum_confidence'] = 0.0
    with pytest.raises(ValueError, match='nonzero'):
        evaluate_source_acceptance(np.array([[2., 0.]]), np.array([0]), policy, LABELS)


def test_wilson_zero_support_and_invalid_counts():
    assert wilson_interval(0, 0) is None
    assert wilson_interval(5, 5)[0] < .6
    with pytest.raises(ValueError):
        wilson_interval(6, 5)
