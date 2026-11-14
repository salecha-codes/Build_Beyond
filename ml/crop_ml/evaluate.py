"""Evaluate the exact exported artifact on an untouched source-test subset."""
from __future__ import annotations

import argparse
import collections
import json
import random
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from .common import DEFAULT_DATA, labels, read_jsonl, sha256, write_json
from .model import prepare_image


def run_model(path: Path, tensors: list[np.ndarray], truth: list[int], threads: int):
    options = ort.SessionOptions();options.intra_op_num_threads = threads;options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
    predicted = []
    elapsed = []
    for tensor in tensors:
        start = time.perf_counter();logits, _ = session.run(None, {"image": tensor[None]});elapsed.append((time.perf_counter() - start) * 1000)
        predicted.append(int(logits.argmax()))
    return {"model_sha256": sha256(path), "samples": len(truth), "accuracy": float(accuracy_score(truth, predicted)), "macro_f1": float(f1_score(truth, predicted, labels=list(range(17)), average="macro", zero_division=0)), "per_class": classification_report(truth, predicted, labels=list(range(17)), target_names=[x["id"] for x in labels()], output_dict=True, zero_division=0), "confusion_matrix": confusion_matrix(truth, predicted, labels=list(range(17))).tolist(), "desktop_inference_only_latency_ms": {"p50": float(np.median(elapsed)), "p95": float(np.percentile(elapsed, 95))}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--compare-smoke", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-per-class", type=int, default=32)
    parser.add_argument("--threads", type=int, default=3)
    args = parser.parse_args(argv)
    test_rows = [r for r in read_jsonl(args.data_root / "splits.jsonl") if r["split"] == "test"]
    rng = random.Random(2718)
    rows = []
    for label in labels():
        candidates = [r for r in test_rows if r["label_index"] == label["index"]]
        rows.extend(rng.sample(candidates, min(args.max_per_class, len(candidates))) if args.max_per_class else candidates)
    if not rows:
        raise ValueError("No test data")
    tensors = []
    for row in rows:
        with Image.open(row["local_path"]) as image:
            tensors.append(prepare_image(image))
    truth = [r["label_index"] for r in rows]
    metrics = run_model(args.bundle / "crop_model.onnx", tensors, truth, args.threads)
    report = {"evaluation_scope": "Held-out source-domain test; not a field-photo trial or phone benchmark", "limited_subset": bool(args.max_per_class), "split_manifest_sha256": sha256(args.data_root / "splits.jsonl"), "source_test_samples": len(test_rows), "evaluated_samples": len(rows), "class_counts": dict(collections.Counter(r["label_id"] for r in rows)), "exact_artifact": metrics, "uniform_random_expected_accuracy": 1 / 17, "diagnosis_validated": False, "grouping_limitation": "Known source leaf groups and exact duplicates were kept together; unmatched physical-leaf groups remain unresolved."}
    if args.compare_smoke:
        report["untrained_same_architecture_comparison"] = run_model(args.compare_smoke / "crop_model.onnx", tensors, truth, args.threads)
    write_json(args.output, report)
    print(json.dumps({"samples": len(rows), "trained_accuracy": metrics["accuracy"], "trained_macro_f1": metrics["macro_f1"], "untrained_accuracy": report.get("untrained_same_architecture_comparison", {}).get("accuracy"), "report": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
