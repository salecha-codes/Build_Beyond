#!/usr/bin/env python3
"""Install a self-describing, hash-checked shared model bundle."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def sync(source: Path) -> None:
    metadata = json.loads((source / "model_metadata.json").read_text())
    policy = json.loads((source / "decision_policy.json").read_text())
    labels = json.loads((source / "labels.json").read_text())
    expected_labels = json.loads((ROOT / "contracts/labels.json").read_text())
    if labels != expected_labels:
        raise ValueError("Bundle labels disagree with the stable application contract")
    if metadata["model_version"] != policy["model_version"]:
        raise ValueError("Model and policy versions disagree")
    name = metadata["model_file"]
    if name != "crop_model.onnx":
        raise ValueError("Unexpected model asset name")
    actual = hashlib.sha256((source / name).read_bytes()).hexdigest()
    if actual != metadata["model_sha256"]:
        raise ValueError("Model checksum verification failed")
    if policy.get("model_sha256", actual) != actual:
        raise ValueError("Policy belongs to a different model")
    evidence_names = ["source_evaluation.json", "embedding_centroids.json"]
    leaf_name = "leaf_validation.json"
    leaf_gate = metadata.get("leaf_gate", {})
    if leaf_gate.get("enabled"):
        if leaf_gate.get("receipt_file") != leaf_name:
            raise ValueError("Unexpected leaf-validation asset name")
        leaf_path = source / leaf_name
        if hashlib.sha256(leaf_path.read_bytes()).hexdigest() != leaf_gate.get("receipt_sha256"):
            raise ValueError("Leaf-validation checksum differs")
        leaf_report = json.loads(leaf_path.read_text())
        if (leaf_report.get("model_sha256") != actual or leaf_report.get("model_version") != metadata["model_version"]
                or leaf_report.get("output_name") != leaf_gate.get("output_name")
                or leaf_report.get("minimum_leaf_probability") != leaf_gate.get("minimum_leaf_probability")):
            raise ValueError("Leaf-validation identity/threshold differs")
    has_evaluation = metadata.get("source_evaluated") is True or policy.get("source_evaluated") is True
    if has_evaluation:
        evidence = {}
        for file in evidence_names:
            prefix = file.removesuffix(".json")
            if policy.get(f"{prefix}_file") != file:
                raise ValueError(f"Missing fixed asset reference: {file}")
            evidence_hash = hashlib.sha256((source / file).read_bytes()).hexdigest()
            if evidence_hash != policy.get(f"{prefix}_sha256"):
                raise ValueError(f"Evidence checksum verification failed: {file}")
            item = json.loads((source / file).read_text())
            if item.get("model_sha256") != actual or item.get("model_version") != metadata["model_version"]:
                raise ValueError(f"Evidence belongs to a different model: {file}")
            evidence[file] = item
        frozen = evidence["source_evaluation.json"].get("frozen_policy")
        if frozen != {"temperature": policy["temperature"], "class_thresholds": policy["class_thresholds"]}:
            raise ValueError("Acceptance thresholds differ from their evaluated frozen policy")
        if evidence["source_evaluation.json"].get("scope") != "source_domain_only":
            raise ValueError("Unexpected evaluation scope")
    parent = ROOT / "models/assets"
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / "model"
    names = [name, "model_metadata.json", "labels.json", "decision_policy.json", "MODEL_CARD.md", "export_receipt.json", *evidence_names, leaf_name]
    if destination.exists() and any(item.name not in names for item in destination.iterdir()):
        raise ValueError("Refusing to overwrite unexpected files in the model asset directory")
    with tempfile.TemporaryDirectory(dir=parent, prefix=".model-") as temp:
        staging = Path(temp)
        for file in names:
            if (source / file).exists():
                shutil.copy2(source / file, staging / file)
        destination.mkdir(exist_ok=True)
        # App reads a fully packaged APK, not this development directory mid-sync.
        for file in staging.iterdir():
            file.replace(destination / file.name)
        for file in [*evidence_names, leaf_name]:
            if not (staging / file).exists() and not (source / file).exists():
                (destination / file).unlink(missing_ok=True)
    print(json.dumps({"installed": str(destination), "architecture": metadata["architecture"],
        "training_status": metadata["training_status"], "diagnosis_validated": metadata["diagnosis_validated"],
        "source_acceptance_qualified": policy.get("source_acceptance_qualified", False),
        "model_sha256": actual, "bytes": (destination / name).stat().st_size}, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("source", type=Path)
    sync(parser.parse_args().source)
