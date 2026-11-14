"""Calibrate a source-domain *demo* gate without declaring diagnoses validated.

Call ``fit_source_acceptance`` only after locking a checkpoint/export, on the
CAL manifest. Apply the returned policy unchanged to the final source test with
``evaluate_source_acceptance``. Neither function trains a model or runs inference.
All scores are global softmax scores, never crop-renormalized probabilities.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class AcceptanceConfig:
    target_precision: float = 0.90
    minimum_class_accepted: int = 5
    confidence_grid: tuple[float, ...] = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.925, 0.95, 0.975, 0.99)
    margin_grid: tuple[float, ...] = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)

    def __post_init__(self):
        if not 0 < self.target_precision <= 1:
            raise ValueError('target_precision must be in (0, 1]')
        if self.minimum_class_accepted < 5:
            raise ValueError('At least five accepted calibration predictions are required per enabled class')
        for name, values in [('confidence_grid', self.confidence_grid), ('margin_grid', self.margin_grid)]:
            if not values or not all(math.isfinite(x) and 0 < x < 1 for x in values):
                raise ValueError(f'{name} must contain finite, strictly positive thresholds below one')


def _arrays(logits, targets, label_ids: Sequence[str]):
    x = np.asarray(logits, dtype=np.float64)
    y_raw = np.asarray(targets)
    names = list(label_ids)
    if len(names) < 2 or len(set(names)) != len(names):
        raise ValueError('At least two unique stable label IDs are required')
    if x.ndim != 2 or x.shape[1] != len(names) or not len(x):
        raise ValueError('Logits must be a nonempty [samples, labels] array')
    if not np.isfinite(x).all():
        raise ValueError('Non-finite logits are not accepted')
    if y_raw.shape != (len(x),) or not np.issubdtype(y_raw.dtype, np.integer):
        raise ValueError('Targets must be an integer [samples] array')
    y = y_raw.astype(np.int64)
    if not ((y >= 0) & (y < len(names))).all():
        raise ValueError('Target outside the stable label range')
    return x, y, names


def _groups(group_ids, size):
    if group_ids is None:
        return None
    groups = list(group_ids)
    if len(groups) != size or any(not isinstance(g, str) or not g for g in groups):
        raise ValueError('group_ids must contain one nonempty source group ID per sample')
    return np.asarray(groups)


def _nll(logits, truth, temperature):
    values = logits / temperature
    maximum = np.max(values, axis=1)
    logsum = maximum + np.log(np.exp(values - maximum[:, None]).sum(axis=1))
    return float(np.mean(logsum - values[np.arange(len(truth)), truth]))


def fit_calibration_temperature(logits, targets, label_ids: Sequence[str]) -> dict:
    """Bounded one-dimensional NLL fit on CAL, independent of Torch/ONNX imports."""
    x, y, _ = _arrays(logits, targets, label_ids)
    left, right = -3.0, 3.0
    ratio = (math.sqrt(5) - 1) / 2
    a, b = right-ratio*(right-left), left+ratio*(right-left)
    fa, fb = _nll(x, y, math.exp(a)), _nll(x, y, math.exp(b))
    for _ in range(80):
        if fa < fb:
            right, b, fb = b, a, fa
            a = right-ratio*(right-left)
            fa = _nll(x, y, math.exp(a))
        else:
            left, a, fa = a, b, fb
            b = left+ratio*(right-left)
            fb = _nll(x, y, math.exp(b))
    best = (left+right)/2
    temperature = math.exp(best)
    before, after = _nll(x, y, 1.0), _nll(x, y, temperature)
    if after > before + 1e-10:
        temperature, after = 1.0, before
    return {'temperature': temperature, 'nll_before': before, 'nll_after': after,
            'log_temperature_bounds': [-3.0, 3.0], 'fit_partition': 'calibration_only',
            'at_search_boundary': abs(best) > 2.99}


def _probabilities(logits, temperature):
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError('Temperature must be finite and positive')
    values = logits / temperature
    values -= values.max(axis=1, keepdims=True)
    exp = np.exp(values)
    return exp / exp.sum(axis=1, keepdims=True)


def _scores(probabilities):
    predicted = probabilities.argmax(axis=1)
    top = probabilities[np.arange(len(probabilities)), predicted]
    second = np.partition(probabilities, -2, axis=1)[:, -2]
    return predicted, top, top-second


def wilson_interval(correct: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    """Descriptive 95% binomial interval; dependence/group selection limit its scope."""
    if total < 0 or correct < 0 or correct > total:
        raise ValueError('Invalid successes/trials')
    if not total:
        return None
    p = correct/total
    denominator = 1+z*z/total
    center = (p+z*z/(2*total))/denominator
    radius = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/denominator
    return [max(0.0, center-radius), min(1.0, center+radius)]


def _ece(confidence, correct, bins=15):
    result = 0.0
    for index in range(bins):
        mask = (confidence >= index/bins) & ((confidence <= 1) if index == bins-1 else (confidence < (index+1)/bins))
        if mask.any():
            result += float(mask.mean()) * abs(float(confidence[mask].mean())-float(correct[mask].mean()))
    return result


def _accepted(predicted, confidence, margin, policy, names, embedding_distances=None):
    accepted = np.zeros(len(predicted), dtype=bool)
    if not policy.get('source_acceptance_enabled', False):
        return accepted
    thresholds = policy['class_thresholds']
    for index, label in enumerate(names):
        row = thresholds[label]
        if row['enabled']:
            c, m = row['minimum_confidence'], row['minimum_margin']
            if not (0 < c < 1 and 0 < m < 1):
                raise ValueError('Enabled classes require nonzero confidence and margin thresholds')
            mask = (predicted == index) & (confidence >= c) & (margin >= m)
            if row.get('max_embedding_distance') is not None:
                maximum = row['max_embedding_distance']
                if embedding_distances is None:
                    raise ValueError('Frozen policy requires predicted-class embedding distances')
                if not math.isfinite(maximum) or maximum < 0:
                    raise ValueError('Embedding distance threshold must be finite and nonnegative')
                mask &= embedding_distances <= maximum
            accepted |= mask
    return accepted


def _classification_summary(truth, predicted, names):
    matrix = np.zeros((len(names), len(names)), dtype=np.int64)
    np.add.at(matrix, (truth, predicted), 1)
    f1_values = []
    for index in range(len(names)):
        denominator = matrix[index].sum()+matrix[:, index].sum()
        f1_values.append(float(2*matrix[index, index]/denominator) if denominator else 0.0)
    supported = matrix.sum(axis=1) > 0
    return {'accuracy': float(np.mean(truth == predicted)), 'macro_f1_all_labels': float(np.mean(f1_values)),
            'macro_f1_supported_labels': float(np.mean(np.asarray(f1_values)[supported])),
            'supported_labels': int(supported.sum()),
            'confusion_matrix': matrix.tolist()}


def evaluate_source_acceptance(logits, targets, policy: dict, label_ids: Sequence[str], *,
                               group_ids=None, model_sha256: str | None = None,
                               embedding_distances=None) -> dict:
    """Evaluate a frozen source-only policy. This function never refits thresholds."""
    x, y, names = _arrays(logits, targets, label_ids)
    groups = _groups(group_ids, len(x))
    if list(policy['label_ids']) != names:
        raise ValueError('Policy label order differs from model logits')
    if model_sha256 is not None and model_sha256 != policy['model_sha256']:
        raise ValueError('Policy is bound to a different exported model SHA256')
    if policy.get('diagnosis_validated') or policy.get('validated'):
        raise ValueError('A source-domain demo gate must not claim diagnosis validation')
    distances = None
    if embedding_distances is not None:
        distances = np.asarray(embedding_distances, dtype=np.float64)
        if distances.shape != (len(x),) or not np.isfinite(distances).all() or (distances < 0).any():
            raise ValueError('Embedding distances must be finite nonnegative [samples] values')
    probabilities = _probabilities(x, float(policy['temperature']))
    predicted, confidence, margin = _scores(probabilities)
    correct = predicted == y
    accepted = _accepted(predicted, confidence, margin, policy, names, distances)
    total, successes = int(accepted.sum()), int((accepted & correct).sum())
    per_class = {}
    for index, label in enumerate(names):
        true_class, predicted_class = y == index, predicted == index
        class_accepted = accepted & predicted_class
        count, good = int(class_accepted.sum()), int((class_accepted & correct).sum())
        support = int(true_class.sum())
        per_class[label] = {
            'truth_support': support, 'raw_predicted_support': int(predicted_class.sum()),
            'raw_correct': int((true_class & correct).sum()), 'accepted_predictions': count,
            'accepted_correct': good, 'accepted_errors': count-good,
            'accepted_precision': good/count if count else None,
            'accepted_precision_wilson95': wilson_interval(good, count),
            'correct_accepted_recall': good/support if support else None,
            'truth_class_coverage': int((accepted & true_class).sum())/support if support else None,
            'truth_groups': len(set(groups[true_class])) if groups is not None else None,
            'accepted_predicted_groups': len(set(groups[class_accepted])) if groups is not None else None,
            'threshold': dict(policy['class_thresholds'][label]),
        }
    group_result = None
    if groups is not None:
        accepted_groups = set(groups[accepted])
        groups_all_correct = sum(bool(correct[accepted & (groups == g)].all()) for g in accepted_groups)
        group_result = {'source_groups': len(set(groups)), 'accepted_groups': len(accepted_groups),
                        'accepted_groups_with_no_accepted_error': groups_all_correct,
                        'all_accepted_predictions_correct_group_fraction': groups_all_correct/len(accepted_groups) if accepted_groups else None,
                        'all_correct_group_wilson95': wilson_interval(groups_all_correct, len(accepted_groups))}
    return {
        'scope': 'Source-domain image evaluation of frozen global-softmax thresholds; not field diagnosis validation',
        'samples': len(x), **_classification_summary(y, predicted, names),
        'temperature': float(policy['temperature']), 'nll': _nll(x, y, float(policy['temperature'])),
        'expected_calibration_error_15_bins': _ece(confidence, correct),
        'accepted_predictions': total, 'accepted_correct': successes, 'accepted_errors': total-successes,
        'accepted_precision': successes/total if total else None,
        'accepted_precision_wilson95': wilson_interval(successes, total),
        'coverage': total/len(x), 'uncertain_predictions': len(x)-total,
        'per_class': per_class, 'groups': group_result,
        'interval_limitations': 'Wilson intervals are descriptive. Image dependence, incomplete physical-leaf grouping, historical selection exposure and CAL threshold search are not covered by binomial intervals.',
        'diagnosis_validated': False,
    }


def fit_source_acceptance(logits, targets, label_ids: Sequence[str], *, model_sha256: str,
                          calibration_manifest_sha256: str, group_ids=None,
                          config: AcceptanceConfig = AcceptanceConfig()) -> dict:
    """Fit CAL temperature and class gates; preserve unsupported classes as uncertain.

    Each enabled class must meet the requested observed CAL precision with at
    least five accepted predictions. The finite grid maximizes accepted count;
    ties favor higher precision and then stricter thresholds. This is selection,
    not an independent guarantee. Inspect the final-test report before shipping.
    """
    x, y, names = _arrays(logits, targets, label_ids)
    groups = _groups(group_ids, len(x))
    for name, value in [('model_sha256', model_sha256), ('calibration_manifest_sha256', calibration_manifest_sha256)]:
        if not re.fullmatch('[a-fA-F0-9]{64}', value):
            raise ValueError(f'{name} must be the actual 64-character SHA256')
    temperature_fit = fit_calibration_temperature(x, y, names)
    probabilities = _probabilities(x, temperature_fit['temperature'])
    predicted, confidence, margin = _scores(probabilities)
    correct = predicted == y
    thresholds = {}
    for index, label in enumerate(names):
        winner, best = None, None
        for c in sorted(set(config.confidence_grid)):
            for m in sorted(set(config.margin_grid)):
                mask = (predicted == index) & (confidence >= c) & (margin >= m)
                count = int(mask.sum())
                if count < config.minimum_class_accepted:
                    continue
                good = int((mask & correct).sum())
                precision = good/count
                if precision+1e-12 < config.target_precision:
                    continue
                rank = (count, precision, c+m, c)
                if best is None or rank > best:
                    winner, best = (c, m, count, good), rank
        if winner is None:
            thresholds[label] = {'enabled': False, 'minimum_confidence': None, 'minimum_margin': None,
                                 'reason': 'No CAL grid point meets observed precision and minimum accepted support',
                                 'calibration_truth_support': int((y == index).sum()),
                                 'calibration_raw_predicted_support': int((predicted == index).sum())}
        else:
            c, m, count, good = winner
            thresholds[label] = {'enabled': True, 'minimum_confidence': c, 'minimum_margin': m,
                                 'calibration_accepted': count, 'calibration_correct': good,
                                 'calibration_precision': good/count,
                                 'calibration_precision_wilson95': wilson_interval(good, count),
                                 'calibration_truth_support': int((y == index).sum()),
                                 'calibration_accepted_groups': len(set(groups[(predicted == index) & (confidence >= c) & (margin >= m)])) if groups is not None else None}
    policy = {
        'schema_version': 1, 'policy_scope': 'source_domain_demo_only',
        'validated': False, 'diagnosis_validated': False,
        'source_acceptance_enabled': any(r['enabled'] for r in thresholds.values()),
        'source_thresholds_calibrated': True, 'model_sha256': model_sha256.lower(),
        'calibration_manifest_sha256': calibration_manifest_sha256.lower(),
        'label_ids': names, 'temperature': temperature_fit['temperature'], 'temperature_fit': temperature_fit,
        'class_thresholds': thresholds, 'selection_config': asdict(config),
        'selection_scope': 'Temperature and thresholds selected on CAL only after locking model. Observed CAL precision is selection-biased; report frozen final source-test results once.',
        'field_limitations': 'No field-photo, diagnosis, treatment or severity validation. Unknown plants and other crops may still produce high softmax scores; source thresholds do not establish out-of-distribution detection.',
    }
    policy['calibration_report'] = evaluate_source_acceptance(x, y, policy, names, group_ids=group_ids, model_sha256=model_sha256.lower())
    return policy
