"""Audit pinned ImageNet sample negatives for an offline leaf-input gate.

Images remain external training/research inputs. This script does not download,
train, fit thresholds, or open leaf calibration/test data.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from PIL import Image, ImageOps
from torchvision.models import MobileNet_V3_Large_Weights

COMMIT = "bc69043e2862758a1906c6a24a792bb28c6bb2ff"
SOURCE = "https://github.com/EliSchwartz/imagenet-sample-images"
FORCE_TEST = {"n03793489", "n02342885", "n02123045", "n03642806", "n03782006"}
# Fish, mammals, human subjects and manufactured objects. Birds, reptiles,
# invertebrates/insects, plants, food and landscapes are conservatively excluded.
ALLOWED = set(range(0, 7)) | set(range(151, 299)) | set(range(330, 916)) | {981, 982, 983, 999}
AMBIGUOUS = re.compile(r"flower|greenhouse|vase|pot$|plant|garden|mushroom|hay|coral|reef|tree|leaf|birdhouse|birdbath|bee|butterfly|spider|web|water lily|moss|fung", re.I)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def dhash(image):
    gray = np.asarray(image.convert("L").resize((9, 8), Image.Resampling.BILINEAR))
    return int.from_bytes(np.packbits(gray[:, 1:] > gray[:, :-1]).tobytes(), "big")


def prepare(repo: Path, output: Path, seed="nonleaf-2601"):
    if any((output / f"{name}.jsonl").exists() for name in ["train", "tune", "test"]):
        raise FileExistsError("Refusing to overwrite frozen nonleaf manifests")
    actual_commit = run(repo, "rev-parse", "HEAD")
    if actual_commit != COMMIT:
        raise ValueError("Unexpected source commit")
    tree = {}
    for line in run(repo, "ls-tree", "-r", COMMIT).splitlines():
        metadata, name = line.split("\t", 1)
        if re.fullmatch(r"n\d{8}_.+\.JPEG", name):
            tree[name] = metadata.split()[2]
    ordered = sorted(tree)
    if len(ordered) != 1000 or not ordered[0].startswith("n01440764_") or not ordered[-1].startswith("n15075141_"):
        raise ValueError("ImageNet synset ordering is not the expected 1000-class inventory")
    categories = MobileNet_V3_Large_Weights.IMAGENET1K_V2.meta["categories"]
    if ordered[673] != "n03793489_mouse.JPEG" or categories[673] != "mouse":
        raise ValueError("Computer mouse class contract mismatch")
    rows, excluded, quarantined = [], [], []
    hashes = {}
    for index, name in enumerate(ordered):
        category = categories[index]
        if index not in ALLOWED or AMBIGUOUS.search(category):
            excluded.append({"source_path": name, "class_index": index, "class_name": category,
                             "reason": "Conservative category exclusion: ambiguous plant/background/food/nature/invertebrate"})
            continue
        path = repo / name
        data = path.read_bytes()
        if hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != tree[name]:
            raise ValueError(f"Git blob verification failed: {name}")
        digest = sha256(data)
        if digest in hashes:
            quarantined.append({"source_path": name, "sha256": digest, "reason": "Exact duplicate", "duplicate_of": hashes[digest]})
            continue
        with Image.open(path) as opened:
            opened.load()
            image = ImageOps.exif_transpose(opened).convert("RGB")
            width, height = image.size
            if min(width, height) < 96:
                quarantined.append({"source_path": name, "sha256": digest, "reason": "Too small for negative corpus"})
                continue
            similarity = dhash(image)
        hashes[digest] = name
        synset = name.split("_", 1)[0]
        rows.append({"id": f"imagenet_sample:{COMMIT[:12]}:{synset}", "local_path": str(path.resolve()),
                     "sha256": digest, "git_blob_sha1": tree[name], "bytes": len(data), "width": width, "height": height,
                     "class_id": synset, "class_index": index, "class_name": category, "label": 0,
                     "label_name": "non_leaf_object", "source": "imagenet_sample_images", "source_commit": COMMIT,
                     "source_path": name, "source_url": f"https://raw.githubusercontent.com/EliSchwartz/imagenet-sample-images/{COMMIT}/{name}",
                     "dhash64": f"{similarity:016x}", "negative_label_status": "ImageNet foreground-category-derived; not individually visually reviewed",
                     "image_license_status": "No blanket image license in sample repository; underlying ImageNet image rights vary; retained as internal research inputs, not redistributed in app"})
    parent = list(range(len(rows)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, row in enumerate(rows):
        value = int(row["dhash64"], 16)
        for j in range(i):
            if (value ^ int(rows[j]["dhash64"], 16)).bit_count() <= 4:
                parent[find(i)] = find(j)
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(find(i), []).append(row)
    group_count = Counter()
    for grouped in groups.values():
        ids = sorted(r["class_id"] for r in grouped)
        group = "nonleaf_group_" + sha256("|".join(ids).encode())[:20]
        value = int(sha256(f"{seed}:{group}".encode())[:16], 16) / 2**64
        split = "test" if FORCE_TEST.intersection(ids) else "train" if value < .70 else "tune" if value < .85 else "test"
        group_count[split] += 1
        for row in grouped:
            row.update(split=split, group_id=group)
    partitions = {name: [r for r in rows if r["split"] == name] for name in ["train", "tune", "test"]}
    for a, b in [("train", "tune"), ("train", "test"), ("tune", "test")]:
        for key in ["sha256", "class_id", "group_id"]:
            assert {r[key] for r in partitions[a]}.isdisjoint(r[key] for r in partitions[b])
    assert any(r["class_index"] == 673 for r in partitions["test"])
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, data in {**partitions, "excluded": excluded, "quarantine": quarantined}.items():
        path = output / f"{name}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in data))
        files[name] = {"path": str(path.resolve()), "rows": len(data), "sha256": sha256(path.read_bytes())}
    receipt = {"schema_version": 1, "source_repository": SOURCE, "source_commit": COMMIT, "source_images": 1000,
               "eligible_images": len(rows), "files": files, "group_counts": dict(group_count),
               "split_seed": seed, "split_method": "sha256-stable group split 70/15/15; exact/class and dHash<=4 groups kept together",
               "forced_locked_test_synsets": sorted(FORCE_TEST), "computer_mouse_class_index": 673,
               "verified_git_blob_and_decoded": len(rows), "calibration_or_test_inference_executed": False,
               "limitations": ["One public sample per ImageNet class; category labels are inherited, not image-by-image expert review.",
                               "This does not establish universal unknown-image rejection.", "No leaf CAL/TUNE/test image was read by this data preparation.",
                               "Photographs remain external internal-research inputs; do not copy them into app assets."]}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=Path("/workspace/crop-data/nonleaf/source"))
    p.add_argument("--output", type=Path, default=Path("/workspace/crop-data/nonleaf"))
    args = p.parse_args()
    print(json.dumps(prepare(args.repo, args.output), indent=2))


if __name__ == "__main__":
    main()
