import numpy as np

from crop_ml.leaf_gate import select_threshold


def test_threshold_maximizes_leaf_recall_after_rejecting_all_objects():
    source = np.array([.8, .9])
    field = np.array([.56, .63, .78, .95])
    negative = np.array([.01, .34])
    threshold, report, interval = select_threshold(source, field, negative)
    assert .34 < threshold < .56
    assert report['nonleaf_rejection']['correct'] == 2
    assert report['field_leaf_recall']['correct'] == 4
    assert interval['representative'] == 'midpoint'


def test_tied_leaf_and_object_score_respects_leaf_recall_floor():
    threshold, report, _ = select_threshold([.8], [.4, .4, .9], [.4])
    assert threshold <= .4
    assert report['field_leaf_recall']['rate'] == 1
    assert report['nonleaf_rejection']['correct'] == 0
