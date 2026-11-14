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
    parent = ROOT / "models/assets"
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / "model"
    names = [name, "model_metadata.json", "labels.json", "decision_policy.json", "MODEL_CARD.md", "export_receipt.json"]
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
    print(json.dumps({"installed": str(destination), "architecture": metadata["architecture"],
        "training_status": metadata["training_status"], "diagnosis_validated": metadata["diagnosis_validated"],
        "model_sha256": actual, "bytes": (destination / name).stat().st_size}, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("source", type=Path)
    sync(parser.parse_args().source)
