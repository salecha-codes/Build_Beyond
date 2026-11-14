"""Pinned, external-only Kandahar field data preparation.

No model inference. Broad source labels are auxiliary-only by default. The
explicit healthy command is the sole permitted mapping into the17-class task.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import urllib.request
import zipfile

REPOSITORY = "RafiullahRafi/MaizeLeafDisease-Kandahar-FieldData-DeepLearningModels"
COMMIT = "33d0e081240535f6d70cca99b343517dc75e92eb"
ARCHIVE_BYTES = 19_339_390
ARCHIVE_SHA256 = "69b4e2d7cb31d7098a61cbad699fc57403242b5ef9d0a5c1bce300ad7aa5162f"
ARCHIVE_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/Kdr_field_Dataset.zip"
AUX_LABELS = {"Blight": 0, "Healthy": 1, "Spot": 2}
ROLES = {"train": "train", "valid": "valid", "test_locked": "test"}
LICENSE = "GPL-3.0 repository-wide as published; image-specific terms not separately documented"
LIMITATIONS = [
    "Original dataset labels are not independently expert verified.",
    "Blight and Spot do not establish exact disease species and must not map into17 labels.",
    "Perceptual and temporal grouping does not prove farm-level or date-level independence.",
    "Source repository GPL terms retained as published; image-specific provenance separately undocumented.",
    "Photos remain external research data and must not be distributed in the app.",
    "No model output may be used to select rows from the reserved test.",
]


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def provenance() -> dict:
    return {"source_repository": f"https://github.com/{REPOSITORY}",
            "source_commit": COMMIT, "zip_sha256": ARCHIVE_SHA256,
            "archive_url": ARCHIVE_URL, "license": LICENSE,
            "limitations": LIMITATIONS}


def download(args: argparse.Namespace) -> None:
    """Verify pinned archive before guarded extraction. Never follow symlinks."""
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "Kdr_field_Dataset.zip"
    if not archive.exists():
        partial = root / "Kdr_field_Dataset.zip.partial"
        try:
            with urllib.request.urlopen(ARCHIVE_URL, timeout=60) as source, partial.open("wb") as target:
                count = 0
                while block := source.read(1024 * 1024):
                    count += len(block)
                    if count > ARCHIVE_BYTES:
                        raise ValueError("Pinned archive exceeded expected byte length")
                    target.write(block)
            if partial.stat().st_size != ARCHIVE_BYTES or sha(partial) != ARCHIVE_SHA256:
                raise ValueError("Pinned archive size/SHA-256 mismatch")
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
    if archive.stat().st_size != ARCHIVE_BYTES or sha(archive) != ARCHIVE_SHA256:
        raise ValueError("Existing archive fails pinned size/SHA-256 check")
    destination = root / "kandahar"
    if destination.exists():
        raise ValueError("Extraction destination already exists; use existing data or a fresh root")
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > 10_000 or sum(m.file_size for m in members) > 250_000_000:
            raise ValueError("Unexpected archive expansion")
        for member in members:
            name = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if (name.is_absolute() or ".." in name.parts or "\\" in member.filename
                    or not name.parts or name.parts[0] not in {"train", "valid", "test"}
                    or stat.S_ISLNK(mode) or "\x00" in member.filename):
                raise ValueError(f"Unsafe archive entry: {member.filename!r}")
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("Archive entry escapes destination")
        bundle.extractall(destination)
    write_json(root / "download_receipt.json", {**provenance(), "archive_bytes": ARCHIVE_BYTES})


def prior_inputs(args: argparse.Namespace) -> tuple[list[dict], set[str], dict]:
    """Exact comparison uses all rows; perceptual PV comparison uses maize only."""
    near_rows, exact, receipts = [], set(), {}
    for kind, paths in (("maize", args.prior_maize_manifest), ("field", args.prior_field_manifest)):
        for path in paths:
            receipts[str(path.resolve())] = sha(path)
            for original in read_rows(path):
                row = dict(original)
                exact.add(row["sha256"])
                if kind == "maize" and row.get("crop_id") != "maize":
                    continue
                row["manifest"] = str(path.resolve())
                near_rows.append(row)
    return near_rows, exact, receipts


def inspect(args: argparse.Namespace) -> None:
    """Initial broad-label quarantine and exact duplicate audit. Decodes pixels."""
    from PIL import Image, ImageOps
    root = args.root.resolve()
    archive = root / "Kdr_field_Dataset.zip"
    if sha(archive) != ARCHIVE_SHA256:
        raise ValueError("Archive SHA mismatch")
    _, old_sha, inputs = prior_inputs(args)
    rows, encoded, pixels, families = [], defaultdict(list), defaultdict(list), defaultdict(list)
    for path in sorted((root / "kandahar").rglob("*.jpg")):
        relative = path.relative_to(root / "kandahar")
        split, label = relative.parts[:2]
        if split not in ROLES.values() or label not in AUX_LABELS:
            raise ValueError(f"Unknown published split/label: {relative}")
        digest = sha(path)
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            width, height = image.size
            pixel_sha = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
        family = re.sub(r"_(?:jpg|jpeg|png)\.rf\..*", "", path.stem, flags=re.I)
        row = {**provenance(), "source": "kandahar", "source_path": str(relative),
               "local_path": str(path), "published_split": split, "published_label": label,
               "sha256": digest, "pixel_sha256": pixel_sha, "width": width, "height": height,
               "original_group": family, "status": "quarantined",
               "exact_prior_overlap": digest in old_sha,
               "reason": "Broad labels not yet cleared for auxiliary or compatible healthy supervision"}
        rows.append(row)
        encoded[digest].append(str(relative)); pixels[pixel_sha].append(str(relative))
        families[family].append(split)
    write_rows(root / "kandahar_quarantined.jsonl", rows)
    write_json(root / "kandahar_audit.json", {**provenance(), "total_files": len(rows),
               "unique_byte_hashes": len(encoded), "unique_decoded_images": len(pixels),
               "exact_overlap_existing": sum(r["exact_prior_overlap"] for r in rows),
               "original_filename_groups": len(families),
               "cross_split_filename_groups": sum(len(set(v)) > 1 for v in families.values()),
               "split_label_counts": dict(Counter(r["published_split"] + "/" + r["published_label"] for r in rows)),
               "prior_manifest_sha256": inputs, "training_eligible_now": 0})


def audit_aux(args: argparse.Namespace) -> None:
    """Decode all splits for duplicate exclusion only; do not run any model."""
    import numpy as np
    from PIL import Image, ImageOps
    root = args.root.resolve(); output = root / "kandahar_aux"; output.mkdir(exist_ok=True)
    manifest = root / "kandahar_quarantined.jsonl"
    rows = read_rows(manifest)
    old, old_sha, inputs = prior_inputs(args)

    def dhash(image):
        array = np.asarray(image.resize((9, 8), Image.Resampling.LANCZOS), dtype=np.int16)
        return int.from_bytes(np.packbits((array[:, 1:] > array[:, :-1]).ravel()).tobytes(), "big")

    def hashes(path, dihedral=False):
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("L")
            return ([dhash(image)] + [dhash(image.transpose(t)) for t in Image.Transpose]
                    if dihedral else dhash(image))

    new_hash = np.array([hashes(r["local_path"], True) for r in rows], dtype=np.uint64)
    old_hash = np.array([hashes(r["local_path"]) for r in old], dtype=np.uint64)
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[b] = a

    families = {}
    for i, row in enumerate(rows):
        family = re.sub(r"_(?:jpg|jpeg|png)\.rf\..*", "", Path(row["source_path"]).stem, flags=re.I)
        row["original_group"] = family
        if family in families:
            union(i, families[family])
        families[family] = i
    lut = np.array([i.bit_count() for i in range(256)], dtype=np.uint8)

    def distances(a, b):
        xor = np.bitwise_xor(a[:, None], b[None, :])
        return lut[xor.view(np.uint8).reshape(*xor.shape, 8)].sum(2).min(0)

    near_old, near_pairs = {}, 0
    for i, row in enumerate(rows):
        distance = distances(new_hash[i], old_hash)
        hits = np.flatnonzero(distance <= 4)
        if len(hits):
            near_old[i] = [{"source_path": old[j].get("source_path", old[j]["local_path"]),
                            "split": old[j].get("split", old[j].get("partition")),
                            "distance": int(distance[j]), "manifest": old[j]["manifest"]} for j in hits]
        if i:
            distance = distances(new_hash[i], new_hash[:i, 0])
            for j in np.flatnonzero(distance <= 4):
                union(i, int(j)); near_pairs += 1
    captures = defaultdict(list)
    for i, row in enumerate(rows):
        match = re.match(r"(\d{8})_(\d{6})", row["original_group"])
        if match:
            timestamp = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).timestamp()
            captures[(match[1], row["published_label"])].append((timestamp, i))
    for capture in captures.values():
        capture.sort()
        for (first, i), (second, j) in zip(capture, capture[1:]):
            if second - first <= 3:
                union(i, j)
    components = defaultdict(list)
    for i in range(len(rows)):
        components[find(i)].append(i)
    excluded, cross_split = {}, 0
    for indices in components.values():
        reasons = []
        if len({rows[i]["published_split"] for i in indices}) > 1:
            reasons.append("cross_published_split_family_or_dhash_or_3sec_capture"); cross_split += 1
        if len({rows[i]["published_label"] for i in indices}) > 1:
            reasons.append("conflicting_original_aux_labels_in_near_family")
        if any(i in near_old or rows[i]["sha256"] in old_sha for i in indices):
            reasons.append("near_or_exact_overlap_prior_data")
        group = "kandahar_family_" + hashlib.sha256("|".join(sorted(rows[j]["original_group"] for j in indices)).encode()).hexdigest()[:20]
        for i in indices:
            rows[i]["group_id"] = group
            if reasons:
                excluded[i] = reasons
    output_rows, seen = defaultdict(list), set()
    for i, row in enumerate(rows):
        row.update(source="kandahar_original_aux_only", split=row["published_split"], crop_id="maize",
                   aux_label_index=AUX_LABELS[row["published_label"]], aux_label=row["published_label"],
                   status="aux_training_audited", label_review_status="original_source_labels_not_expert_verified",
                   label_taxonomy="original_three_way_auxiliary_only_not_17_condition_mapping")
        if i in excluded:
            row.update(status="quarantined", exclusion_reasons=excluded[i]); output_rows["quarantine"].append(row)
        elif row["pixel_sha256"] in seen:
            row["status"] = "duplicate_removed"; output_rows["duplicates"].append(row)
        else:
            seen.add(row["pixel_sha256"]); row.pop("reason", None)
            output_rows[{v: k for k, v in ROLES.items()}[row["published_split"]]].append(row)
    for role in [*ROLES, "quarantine", "duplicates"]:
        write_rows(output / (role + ".jsonl"), output_rows[role])
    write_json(output / "receipt.json", {**provenance(), "schema_version": 1,
               "training_ready": bool(output_rows["train"] and output_rows["valid"]),
               "aux_label_mapping": AUX_LABELS, "counts": {k: len(v) for k, v in output_rows.items()},
               "label_counts": {k: dict(Counter(r["aux_label"] for r in v)) for k, v in output_rows.items()},
               "manifest_sha256": {k: sha(output / (k + ".jsonl")) for k in ROLES},
               "input_quarantine_manifest_sha256": sha(manifest), "prior_manifest_sha256": inputs,
               "audit": {"near_threshold_hamming": 4, "hash": "Pillow grayscale Lanczos9x8 dhash64, all8dihedral views",
                         "prior_rows": len(old), "new_near_prior_rows": len(near_old), "new_near_prior_hits": near_old,
                         "new_near_pairs": near_pairs, "cross_published_split_components": cross_split,
                         "capture_temporal_grouping_seconds": 3, "cross_split_remaining_groups": 0},
               "usage": "Original3way auxiliary TRAIN/VALID only; originaltest stays locked; no17mapping"})


def healthy(args: argparse.Namespace) -> None:
    """Metadata-only explicit compatible-label protocol. Does not decode pixels."""
    root = args.root.resolve(); auxiliary = root / "kandahar_aux"; output = root / "kandahar_healthy"
    receipt = json.loads((auxiliary / "receipt.json").read_text())
    if receipt.get("training_ready") is not True:
        raise ValueError("Auxiliary audit is not training-ready")
    old, old_hash, old_group, old_inputs = [], set(), set(), {}
    if args.old_source_splits_manifest:
        path = args.old_source_splits_manifest
        old_inputs[str(path.resolve())] = sha(path)
        old.extend(row for row in read_rows(path) if row.get("split") == "train")
    for path in args.old_train_tune_manifest:
        old_inputs[str(path.resolve())] = sha(path)
        old.extend(read_rows(path))
    for row in old:
        old_hash.add(row["sha256"]); old_group.add(row.get("group_id"))
    new_rows = {}
    for role, original_split in ROLES.items():
        path = auxiliary / (role + ".jsonl")
        if sha(path) != receipt["manifest_sha256"][role]:
            raise ValueError("Auxiliary manifest no longer matches receipt")
        rows = [row for row in read_rows(path) if row["published_label"] == "Healthy"]
        for row in rows:
            if (row["crop_id"] != "maize" or row["published_split"] != original_split
                    or row["sha256"] in old_hash or row["group_id"] in old_group):
                raise ValueError("Healthy-compatible row fails crop/split/old-data exclusion")
            row.update(source="kandahar_healthy_compatible_main", label_index=3, label_id="maize_healthy",
                       canonical_class_index=3, canonical_condition_id="maize_healthy", condition_id="maize_healthy",
                       label_taxonomy="only_Healthy_plus_explicit_maize_mapped_to_maize_healthy",
                       mapping_status="source_label_compatible_not_expert_verified", status="healthy_main_training_audited",
                       split=original_split, partition=role, label_review_status="dataset_provided_Healthy_not_expert_verified",
                       usage_scope="main17way_healthy_only_" + role)
        new_rows[role] = rows
    for role, rows in new_rows.items():
        for other, other_rows in new_rows.items():
            if role != other and ({r["sha256"] for r in rows} & {r["sha256"] for r in other_rows}
                                  or {r["group_id"] for r in rows} & {r["group_id"] for r in other_rows}):
                raise ValueError("Healthy protocol contains cross-split exact/group overlap")
    output.mkdir(exist_ok=True)
    for role, rows in new_rows.items():
        write_rows(output / (role + ".jsonl"), rows)
    write_json(output / "receipt.json", {**provenance(), "schema_version": 1,
               "training_ready": bool(new_rows["train"] and new_rows["valid"]),
               "usage_protocol": "Healthy-only compatible main17way supervision; Blight/Spot remain unmapped",
               "source_aux_receipt_sha256": sha(auxiliary / "receipt.json"),
               "counts": {k: len(v) for k, v in new_rows.items()},
               "manifest_sha256": {k: sha(output / (k + ".jsonl")) for k in ROLES},
               "label_mapping": {"Healthy": {"crop_id": "maize", "label_id": "maize_healthy", "label_index": 3}},
               "old_train_tune_manifest_sha256": old_inputs,
               "old_main_train_tune_disjointness": {"rows_checked": len(old), "sha256_overlap": 0, "group_id_overlap": 0},
               "perceptual_audit_inherited": {k: v for k, v in receipt["audit"].items() if k != "new_near_prior_hits"},
               "no_new_image_pixels_decoded_for_this_filter": True,
               "no_model_outputs_used_for_selection": True,
               "test_status": "Original publishedtest healthy subset remains locked; metadata-only filtering",
               "usage": "TRAIN optionalmainhead;VALID predeclaredselection;TEST onlyafterfreeze, healthy-only not disease accuracy"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, function, help_text in [
        ("download", download, "Download verified pinned ZIP and safely extract outside repository"),
        ("inspect", inspect, "Decode photos for exact audit; quarantine all broad labels"),
        ("audit-aux", audit_aux, "Perceptual/group audit; original3way auxiliary-only manifests"),
        ("healthy", healthy, "Explicit metadata-only Healthy→maize_healthy protocol"),
    ]:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--root", type=Path, required=True, help="External working root; do not use app/assets or repository")
        sub.set_defaults(function=function)
        if name in {"inspect", "audit-aux"}:
            sub.add_argument("--prior-maize-manifest", type=Path, action="append", required=True,
                             help="PlantVillage manifest; repeat as needed, allSHA checked, maize pixels used for near audit")
            sub.add_argument("--prior-field-manifest", type=Path, action="append", required=True,
                             help="Existing field partition manifest; repeat for every TRAIN/TUNE/CAL/TEST partition")
        elif name == "healthy":
            sub.add_argument("--old-source-splits-manifest", type=Path,
                             help="Optional source split manifest; only split=train rows checked (TUNE supplied separately)")
            sub.add_argument("--old-train-tune-manifest", type=Path, action="append", required=True,
                             help="Existing main TRAIN/TUNE manifest; repeat for all source/field pools; metadata only")
    args = parser.parse_args()
    # Refuse accidental raw image creation anywhere inside this Git checkout.
    repository = Path(__file__).resolve().parents[2]
    if args.root.resolve().is_relative_to(repository):
        parser.error("--root must be outside the Git repository; raw photos are research-only")
    args.function(args)


if __name__ == "__main__":
    main()
