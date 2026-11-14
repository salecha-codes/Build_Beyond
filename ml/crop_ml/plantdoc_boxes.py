"""Build a TRAIN-only PlantDoc leaf-box manifest from pinned official VOC XML.

The object-detection and classification releases contain the *same photos*.
Joining by Git blob, checking XML object labels, and excluding reserved
near-duplicates prevents treating these boxes as new independent images.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
from urllib.parse import quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

COMMIT = "4730a233a555b30ee98e0879c63ad25d82407455"
OWNER = "pratikkayal/PlantDoc-Object-Detection-Dataset"


def git(repo: Path, *arguments: str) -> bytes:
    return subprocess.check_output(["git", *arguments], cwd=repo)


def rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def tree(repo: Path) -> dict[str, str]:
    result = {}
    for line in git(repo, "ls-tree", "-r", "-z", "HEAD").split(b"\0"):
        if line:
            info, name = line.split(b"\t", 1)
            result[name.decode("utf-8")] = info.decode().split()[2]
    return result


def parse_xml(data: bytes, csv_width: int, csv_height: int) -> tuple[int, int, list[dict], str]:
    root = ET.fromstring(data)
    width = int(root.findtext("size/width", "0"))
    height = int(root.findtext("size/height", "0"))
    if width < 1 or height < 1:
        width, height = csv_width, csv_height
        dimension_source = "pinned_train_labels_CSV_missing_VOC_size"
    else:
        dimension_source = "pinned_VOC_XML"
    boxes = []
    for item in root.findall("object"):
        name = (item.findtext("name") or "").strip()
        rect = item.find("bndbox")
        if rect is None:
            raise ValueError("VOC object has no bounding box")
        box = {axis: int(rect.findtext(axis, "-1")) for axis in ("xmin", "ymin", "xmax", "ymax")}
        if not (0 <= box["xmin"] < box["xmax"] <= width and 0 <= box["ymin"] < box["ymax"] <= height):
            raise ValueError("VOC bounding box lies outside its image")
        boxes.append({"class": name, **box})
    return width, height, boxes, dimension_source


def download_xml(path: str, expected_blob: str) -> tuple[bytes, str]:
    url = f"https://raw.githubusercontent.com/{OWNER}/{COMMIT}/{quote(path, safe='/')}"
    request = Request(url, headers={"User-Agent": "BuildBeyond-PlantDoc-VOC-audit/1.0"})
    with urlopen(request, timeout=25) as response:
        data = response.read(256_000 + 1)
    if len(data) > 256_000 or git_blob(data) != expected_blob:
        raise ValueError(f"Pinned VOC XML hash/size differs: {path}")
    return data, url


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object-repo", type=Path, required=True)
    parser.add_argument("--plantdoc-partitions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args(argv)
    if args.workers < 1 or args.output.exists():
        raise ValueError("Use positive workers and a new output directory")
    if git(args.object_repo, "rev-parse", "HEAD").decode().strip() != COMMIT:
        raise ValueError("Object-detection repository is not pinned to the audited commit")
    objects = tree(args.object_repo)
    train = rows(args.plantdoc_partitions / "train.jsonl")
    reserved = []
    for name in ("tune", "calibration", "external_test_locked"):
        reserved += rows(args.plantdoc_partitions / f"{name}.jsonl")
    reserved_hashes = {row["sha256"] for row in reserved}
    reserved_groups = {row["group_id"] for row in reserved}
    reserved_dhash = [int(row["dhash64"], 16) for row in reserved if row.get("dhash64")]
    od_test_blobs = {blob for path, blob in objects.items()
                     if path.startswith("TEST/") and path.lower().endswith((".jpg", ".jpeg", ".png"))}
    source_csv = git(args.object_repo, "show", "HEAD:train_labels.csv")
    if git_blob(source_csv) != objects["train_labels.csv"]:
        raise ValueError("Training CSV differs from pinned Git tree")
    csv_by_name = defaultdict(list)
    for item in csv.DictReader(io.StringIO(source_csv.decode("utf-8-sig"))):
        csv_by_name[item["filename"]].append(item)
    by_blob = defaultdict(list)
    for path, blob in objects.items():
        if path.startswith("TRAIN/") and path.lower().endswith((".jpg", ".jpeg", ".png")):
            by_blob[blob].append(path)
    selected, quarantined = [], []
    for row in train:
        sha = row["sha256"]
        if sha in reserved_hashes or row["group_id"] in reserved_groups or (
            row.get("dhash64") and any((int(row["dhash64"], 16) ^ value).bit_count() <= 4 for value in reserved_dhash)
        ):
            quarantined.append({"id": row["id"], "reason": "reserved_exact_group_or_near_duplicate"})
            continue
        choices = by_blob.get(row["blob_sha1"], [])
        if not choices:
            quarantined.append({"id": row["id"], "reason": "no_exact_object_repository_photo"})
            continue
        if row["blob_sha1"] in od_test_blobs:
            quarantined.append({"id": row["id"], "reason": "same_photo_in_object_original_test"})
            continue
        path = sorted(choices)[0]
        annotations = csv_by_name.get(path.split("/", 1)[1], [])
        if not annotations or {item["class"] for item in annotations} != {row["raw_label"]}:
            quarantined.append({"id": row["id"], "reason": "mixed_or_conflicting_VOC_classes"})
            continue
        xml_path = path.rsplit(".", 1)[0] + ".xml"
        if xml_path not in objects:
            quarantined.append({"id": row["id"], "reason": "missing_pinned_VOC_XML"})
            continue
        selected.append((row, path, xml_path, annotations))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        downloads = {pool.submit(download_xml, xml_path, objects[xml_path]): (row, photo_path, xml_path, annotations)
                     for row, photo_path, xml_path, annotations in selected}
        manifested = []
        for future in as_completed(downloads):
            row, photo_path, xml_path, annotations = downloads[future]
            data, url = future.result()
            try:
                width, height, boxes, dimension_source = parse_xml(data, int(annotations[0]["width"]),
                                                                    int(annotations[0]["height"]))
            except (ValueError, ET.ParseError):
                quarantined.append({"id": row["id"], "reason": "invalid_VOC_XML_box_or_size"})
                continue
            expected = sorted(tuple(int(a[k]) for k in ("xmin", "ymin", "xmax", "ymax")) for a in annotations)
            observed = sorted(tuple(b[k] for k in ("xmin", "ymin", "xmax", "ymax")) for b in boxes)
            if expected != observed or {b["class"] for b in boxes} != {row["raw_label"]}:
                quarantined.append({"id": row["id"], "reason": "VOC_XML_CSV_or_class_disagreement"})
                continue
            if width != int(annotations[0]["width"]) or height != int(annotations[0]["height"]):
                quarantined.append({"id": row["id"], "reason": "VOC_dimensions_disagree_with_CSV"})
                continue
            manifested.append({"id": row["id"], "local_path": row["local_path"], "image_sha256": row["sha256"],
                "image_git_blob_sha1": row["blob_sha1"], "group_id": row["group_id"], "dhash64": row.get("dhash64"),
                "label_id": row["label_id"], "label_index": row["label_index"], "crop_id": row["crop_id"],
                "original_partition": "train", "original_split": "train", "width": width, "height": height,
                "dimension_source": dimension_source,
                "boxes": [{k: b[k] for k in ("xmin", "ymin", "xmax", "ymax")} for b in boxes],
                "annotation_class": row["raw_label"], "voc_xml_path": xml_path,
                "voc_xml_git_blob_sha1": objects[xml_path], "voc_xml_url": url,
                "object_image_path": photo_path, "object_repository_commit": COMMIT,
                "license": "CC-BY-4.0", "derived_photo": True})
    manifested.sort(key=lambda row: row["id"])
    quarantined.sort(key=lambda row: row["id"])
    args.output.mkdir(parents=True)
    output = args.output / "train_boxes.jsonl"
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in manifested))
    (args.output / "quarantine.jsonl").write_text("".join(json.dumps(row) + "\n" for row in quarantined))
    result = {"schema_version": 1, "scope": "existing_PlantDoc_train_photos_only", "new_independent_images": 0,
        "source": f"https://github.com/{OWNER}/tree/{COMMIT}", "source_commit": COMMIT,
        "license": "CC-BY-4.0", "source_train_manifest_sha256": sha256(args.plantdoc_partitions / "train.jsonl"),
        "reserved_manifest_sha256": {name: sha256(args.plantdoc_partitions / f"{name}.jsonl")
            for name in ("tune", "calibration", "external_test_locked")},
        "source_csv_git_blob_sha1": objects["train_labels.csv"], "photos_considered": len(train),
        "photos_with_verified_boxes": len(manifested), "boxes": sum(len(row["boxes"]) for row in manifested),
        "photos_by_crop": dict(Counter(row["crop_id"] for row in manifested)),
        "boxes_by_crop": dict(Counter(row["crop_id"] for row in manifested for box in row["boxes"])),
        "quarantine_reasons": dict(Counter(row["reason"] for row in quarantined)),
        "manifest_sha256": sha256(output), "quarantine_sha256": sha256(args.output / "quarantine.jsonl"),
        "limitations": ["These are box annotations of already used PlantDoc TRAIN photos, not new images.",
                        "Image labels are source dataset candidates, not agronomist-reviewed diagnoses.",
                        "Do not count multiple boxes from one photo as independent train/test samples."]}
    (args.output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
