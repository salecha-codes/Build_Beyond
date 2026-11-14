import copy
import hashlib

import numpy as np
from PIL import Image

from crop_ml.common import labels
from crop_ml.model import PADDING_RGB, MEAN, STD, prepare_image
from crop_ml.prepare import split_rows
from crop_ml.calibrate import fit_temperature


def test_labels_are_stable_and_unique():
    values = labels()
    assert [x["index"] for x in values] == list(range(17))
    assert len({x["id"] for x in values}) == 17
    assert {x["crop_id"] for x in values} == {"maize", "potato", "tomato"}


def test_letterbox_preserves_aspect_and_normalizes_padding():
    image = Image.new("RGB", (448, 224), (255, 0, 0))
    array = prepare_image(image)
    assert array.shape == (3, 224, 224)
    assert array.dtype == np.float32
    expected = (np.asarray(PADDING_RGB) / 255.0 - MEAN) / STD
    np.testing.assert_allclose(array[:, 0, 0], expected, atol=1e-6)
    np.testing.assert_allclose(array[:, 112, 112], (np.array([1, 0, 0]) - MEAN) / STD, atol=1e-6)


def test_group_split_has_no_leaf_or_exact_copy_leakage():
    rows = []
    for label in labels():
        for group in range(8):
            for capture in range(2):
                value = f"{label['id']}-{group}-{capture}"
                rows.append({"status": "verified", "label_index": label["index"], "label_id": label["id"], "sha256": hashlib.sha256(value.encode()).hexdigest(), "leaf_group": f"{label['id']}-{group}"})
    duplicate = dict(rows[0]);duplicate["leaf_group"] = None;rows.append(duplicate)
    split, receipt = split_rows(rows)
    for key in ["sha256", "group_id", "leaf_group"]:
        seen = {}
        for row in split:
            if row.get(key):
                seen.setdefault(row[key], set()).add(row["split"])
        assert all(len(x) == 1 for x in seen.values())
    assert receipt["exact_duplicates_excluded"] == 1
    assert split == split_rows(copy.deepcopy(rows))[0]


def test_temperature_fit_reduces_overconfident_validation_loss_without_changing_labels():
    logits = np.array([[5.0, -5.0]] * 8)
    targets = np.array([0, 1] * 4)
    result = fit_temperature(logits, targets)
    assert np.isfinite(result["temperature"]) and result["temperature"] > 0
    assert result["nll_after"] < result["nll_before"]
    np.testing.assert_array_equal(logits.argmax(1), (logits / result["temperature"]).argmax(1))
