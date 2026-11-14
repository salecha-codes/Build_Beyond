"""Export V4 to a self-describing Android bundle and check actual ONNX execution."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from .common import LABELS_PATH, MODEL_NAME, labels, sha256, write_json
from .model import CropModel, IMAGE_SIZE, MEAN, PADDING_RGB, STD


def export_bundle(output: Path, checkpoint: Path | None = None, threads: int = 3) -> dict:
    torch.set_num_threads(threads)
    torch.manual_seed(26)
    model = CropModel().eval()
    training_receipt = None
    selected_epoch = None
    if checkpoint:
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        model.load_state_dict(state["state_dict"], strict=True)
        receipt_path = checkpoint.parent / "training_receipt.json"
        if not receipt_path.exists():
            raise ValueError("A training checkpoint must have its training receipt")
        training_receipt = json.loads(receipt_path.read_text())
        selected_epoch = state.get("epoch", max(training_receipt["history"], key=lambda x: x["validation_macro_f1"])["epoch"])
    output.mkdir(parents=True, exist_ok=True)
    example = torch.zeros(1, 3, IMAGE_SIZE, IMAGE_SIZE)
    with torch.inference_mode():
        expected_logits, expected_embeddings = model(example)
        torch.onnx.export(model, example, str(output / "crop_model.onnx"), input_names=["image"], output_names=["logits", "embeddings"], opset_version=17, do_constant_folding=True, dynamo=False)
    exported = onnx.load(output / "crop_model.onnx")
    onnx.checker.check_model(exported, full_check=True)
    options = ort.SessionOptions();options.intra_op_num_threads = threads;options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(output / "crop_model.onnx"), options, providers=["CPUExecutionProvider"])
    actual_logits, actual_embeddings = session.run(None, {"image": example.numpy()})
    max_error = max(float(np.abs(actual_logits - expected_logits.numpy()).max()), float(np.abs(actual_embeddings - expected_embeddings.numpy()).max()))
    if not np.isfinite(actual_logits).all():
        raise ValueError(f"Export failed real runtime parity check: {max_error}")
    np.testing.assert_allclose(actual_logits, expected_logits.numpy(), rtol=1e-4, atol=1e-4)
    np.testing.assert_allclose(actual_embeddings, expected_embeddings.numpy(), rtol=1e-4, atol=1e-4)
    # A nonzero input catches accidental constant-output tracing better than zeros alone.
    probe = np.random.default_rng(26).normal(size=(1, 3, 224, 224)).astype(np.float32)
    with torch.inference_mode():
        reference = model(torch.from_numpy(probe))
    actual = session.run(None, {"image": probe})
    probe_error = max(float(np.abs(a - b.numpy()).max()) for a, b in zip(actual, reference))
    for exported_output, reference_output in zip(actual, reference):
        np.testing.assert_allclose(exported_output, reference_output.numpy(), rtol=1e-4, atol=1e-4)
    measured = []
    for _ in range(10):
        start = time.perf_counter();session.run(None, {"image": probe});measured.append((time.perf_counter() - start) * 1000)
    model_path = output / "crop_model.onnx"
    artifact_hash = sha256(model_path)
    training_mode = training_receipt["training_mode"] if training_receipt else "untrained_smoke"
    model_version = f"mnv4-conv-small-{training_mode}-{artifact_hash[:12]}"
    metadata = {"schema_version": 1, "model_version": model_version, "architecture": "MobileNetV4-Conv-Small", "timm_model": MODEL_NAME, "model_file": model_path.name, "model_sha256": artifact_hash, "model_size_bytes": model_path.stat().st_size, "class_count": 17, "embedding_dimension": int(actual_embeddings.shape[1]), "input": {"name": "image", "dtype": "float32", "shape": [1, 3, 224, 224], "layout": "NCHW", "color_order": "RGB", "width": 224, "height": 224, "resize": "letterbox", "resize_rounding": "half_up", "interpolation": "bilinear", "padding_rgb": list(PADDING_RGB), "pixel_scale": 255.0, "mean": list(MEAN), "std": list(STD), "exif_orientation": True}, "outputs": {"logits": {"name": "logits", "shape": [1, 17]}, "embeddings": {"name": "embeddings", "shape": [1, int(actual_embeddings.shape[1])]}}, "labels_file": "labels.json", "policy_file": "decision_policy.json", "precision": "fp32", "onnx_opset": 17, "onnx_ir_version": exported.ir_version, "runtime_tested": f"onnxruntime-python-{ort.__version__}-cpu", "training_status": "trained_prototype" if checkpoint else "untrained_pipeline_smoke_only", "diagnosis_validated": False, "test_scope": "Desktop CPU export/runtime parity only. This is not phone performance or clinical/field validation."}
    policy = {"schema_version": 1, "model_version": metadata["model_version"], "validated": False, "validation_status": "not_validated_for_diagnosis", "temperature": 1.0, "min_confidence": 0.75, "min_margin": 0.15, "thresholds_calibrated": False, "reason": "MODEL_NOT_VALIDATED", "allow_condition_specific_advice": False, "note": "Thresholds are provisional plumbing values, not calibrated acceptance criteria. All predictions must remain uncertain until the validated gate is enabled through an independently evaluated artifact."}
    write_json(output / "model_metadata.json", metadata)
    write_json(output / "decision_policy.json", policy)
    shutil.copyfile(LABELS_PATH, output / "labels.json")
    if checkpoint:
        write_json(output / "training_receipt.json", training_receipt)
        validation_metrics = checkpoint.parent / "validation_metrics.json"
        if validation_metrics.exists():
            shutil.copyfile(validation_metrics, output / "validation_metrics.json")
        validation_subset = checkpoint.parent / "validation_subset.jsonl"
        if validation_subset.exists():
            shutil.copyfile(validation_subset, output / "validation_subset.jsonl")
    receipt = {"architecture": metadata["architecture"], "checkpoint": str(checkpoint) if checkpoint else None, "initialized_model_only": checkpoint is None, "selected_training_epoch": selected_epoch, "training_receipt": training_receipt, "onnx_checker_passed": True, "zero_input_max_abs_error": max_error, "nonzero_input_max_abs_error": probe_error, "output_shapes": [list(x.shape) for x in actual], "desktop_cpu_latency_ms": {"iterations": len(measured), "p50": float(np.median(measured)), "p95": float(np.percentile(measured, 95))}, "phone_benchmark_executed": False, "diagnosis_validated": False, "model_sha256": metadata["model_sha256"]}
    write_json(output / "export_receipt.json", receipt)
    (output / "MODEL_CARD.md").write_text(f"# MobileNetV4-Conv-Small prototype\n\nTraining status: **{metadata['training_status']}**.\n\nThis bundle contains a real executable V4 model, but is **not validated for disease diagnosis**. The decision policy deliberately keeps predictions uncertain. Export parity is a pipeline check, not evidence of recognition quality. No phone latency or RAM result is claimed.\n\nClasses: 17; pooled embedding dimension: {metadata['embedding_dimension']}; preprocessing and hashes are in model_metadata.json. Raw scores must not be presented as validated probabilities or pesticide instructions.\n\nSee training/export receipts for exact executed work.\n")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--threads", type=int, default=3)
    args = parser.parse_args(argv)
    print(json.dumps(export_bundle(args.output, args.checkpoint, args.threads), indent=2))


if __name__ == "__main__":
    main()
