from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
LABELS_PATH = PROJECT / "contracts" / "labels.json"
DEFAULT_DATA = Path(os.environ.get("CROP_DATA_DIR", "/workspace/crop-data"))
MODEL_NAME = "mobilenetv4_conv_small.e2400_r224_in1k"
SOURCE_COMMIT = "7f7ecc7e1eaca78107e3affe7cb5abd9427e139a"
SOURCE_REPO = "https://github.com/spMohanty/PlantVillage-Dataset.git"


def labels() -> list[dict]:
    return json.loads(LABELS_PATH.read_text())["labels"]


def read_jsonl(path: Path) -> list[dict]:
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
