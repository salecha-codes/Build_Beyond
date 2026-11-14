"""Fit temperature to actual exported-model source-validation logits; keep release gate false."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from PIL import Image

from .common import DEFAULT_DATA, read_jsonl, sha256, write_json
from .model import prepare_image


def fit_temperature(logits: np.ndarray, targets: np.ndarray) -> dict:
    x = torch.tensor(logits, dtype=torch.float64)
    y = torch.tensor(targets, dtype=torch.long)
    log_temperature = torch.nn.Parameter(torch.zeros((), dtype=torch.float64))
    before = float(torch.nn.functional.cross_entropy(x, y))
    optimizer = torch.optim.LBFGS([log_temperature], max_iter=60, line_search_fn="strong_wolfe")

    def closure():
        optimizer.zero_grad()
        temperature = log_temperature.clamp(-3.0, 3.0).exp()
        loss = torch.nn.functional.cross_entropy(x / temperature, y)
        loss.backward()
        return loss

    optimizer.step(closure)
    temperature = float(log_temperature.detach().clamp(-3.0, 3.0).exp())
    after = float(torch.nn.functional.cross_entropy(x / temperature, y))
    if not np.isfinite(after) or after > before + 1e-8:
        temperature, after = 1.0, before
    return {"temperature": temperature, "nll_before": before, "nll_after": after}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--threads", type=int, default=3)
    args = p.parse_args(argv)
    torch.set_num_threads(args.threads)
    predictions = args.bundle / "validation_predictions.json"
    # Use the same declared validation subset as the training experiment.
    training_receipt = json.loads((args.bundle / "training_receipt.json").read_text())
    rows = [x for x in read_jsonl(args.data_root / "splits.jsonl") if x["split"] == "validation"]
    # The exact training subset identity is saved by current training runs.
    subset_path = args.bundle / "validation_subset.jsonl"
    if not subset_path.exists():
        raise ValueError("Bundle needs the exact validation_subset.jsonl, not a guessed calibration partition")
    rows = read_jsonl(subset_path)
    options = ort.SessionOptions();options.intra_op_num_threads = args.threads;options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(args.bundle / "crop_model.onnx"), options, providers=["CPUExecutionProvider"])
    logits, truth = [], []
    for row in rows:
        with Image.open(row["local_path"]) as image:
            inputs = prepare_image(image)[None]
        output, _ = session.run(None, {"image": inputs})
        logits.append(output[0]);truth.append(row["label_index"])
    parity_checked = False
    if predictions.exists():
        reference = json.loads(predictions.read_text())
        if reference["labels"] != truth:
            raise ValueError("Reference validation labels differ from reconstructed subset")
        np.testing.assert_allclose(np.asarray(logits), np.asarray(reference["logits"]), rtol=1e-4, atol=1e-4)
        parity_checked = True
    result = fit_temperature(np.asarray(logits), np.asarray(truth))
    receipt = {"scope": "Source-validation fit on a subset also used for model selection, not independent test or field calibration", "samples": len(rows), "actual_model_sha256": sha256(args.bundle / "crop_model.onnx"), "subset_manifest_sha256": sha256(subset_path), "all_reference_logits_parity_checked": parity_checked, **result, "thresholds_calibrated": False, "diagnosis_validated": False, "training_mode": training_receipt["training_mode"]}
    policy = json.loads((args.bundle / "decision_policy.json").read_text())
    policy.update(temperature=result["temperature"], validated=False, thresholds_calibrated=False, calibration_receipt="calibration_receipt.json", note="Temperature fitted to actual exported-model source-validation logits. Acceptance thresholds remain provisional; diagnosis remains unvalidated.")
    write_json(args.bundle / "decision_policy.json", policy)
    write_json(args.bundle / "calibration_receipt.json", receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
