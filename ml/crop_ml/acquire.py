"""Acquire only the selected RGB classes, with pinned Git blob verification."""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import hashlib
import io
import json
import random
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

from .common import DEFAULT_DATA, SOURCE_COMMIT, SOURCE_REPO, labels, write_json, write_jsonl


def get_bytes(url: str, limit: int = 8_000_000) -> bytes:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=40) as response:
                content = response.read(limit + 1)
            if len(content) > limit:
                raise ValueError(f"Artifact exceeds {limit} byte limit")
            return content
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(min(30, float(exc.headers.get("Retry-After", 2 ** attempt))))
        except (TimeoutError, ConnectionError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Download failed")


def inventory(data_root: Path, prior_inventory: Path | None = None) -> list[dict]:
    chosen = {x["source_label"]: x for x in labels()}
    if prior_inventory:
        source = json.loads(prior_inventory.read_text())
        if source["commit"] != SOURCE_COMMIT:
            raise ValueError("Prior inventory commit differs from pinned source")
        entries = source["entries"]
    else:
        gitmeta = data_root / "source.git"
        if not gitmeta.exists():
            subprocess.run(["git", "clone", "--bare", "--filter=blob:none", "--depth", "1", SOURCE_REPO, str(gitmeta)], check=True)
        head = subprocess.check_output(["git", f"--git-dir={gitmeta}", "rev-parse", "HEAD"], text=True).strip()
        if head != SOURCE_COMMIT:
            subprocess.run(["git", f"--git-dir={gitmeta}", "fetch", "--depth", "1", "origin", SOURCE_COMMIT], check=True)
        tree = subprocess.check_output(["git", f"--git-dir={gitmeta}", "ls-tree", "-rz", SOURCE_COMMIT])
        entries = []
        for item in tree.split(b"\0"):
            if item:
                meta, path = item.split(b"\t", 1)
                entries.append({"path": path.decode(), "blob": meta.decode().split()[2]})

    leaf_path = data_root / "source_leaf_map.json"
    if not leaf_path.exists():
        leaf_path.write_bytes(get_bytes(f"https://raw.githubusercontent.com/spMohanty/PlantVillage-Dataset/{SOURCE_COMMIT}/leaf_grouping/leaf-map.json"))
    source_map = json.loads(leaf_path.read_text())
    normal = lambda x: re.sub("[^a-z0-9]", "", x.lower())
    index: dict[str, set] = collections.defaultdict(set)
    for name, groups in source_map.items():
        index[normal(name)].update(groups)
    rows = []
    for entry in entries:
        parts = entry["path"].split("/")
        if len(parts) != 4 or parts[:2] != ["raw", "color"] or parts[2] not in chosen:
            continue
        label = chosen[parts[2]]
        ident = re.sub(r"\.(jpg|png|jpeg)$", "", parts[-1], flags=re.I).split("___")[-1].split("copy")[0]
        matches = [g for g in index[normal(ident)] if g.split(":::")[0] == label["source_label"]]
        rows.append({"source": "plantvillage", "source_commit": SOURCE_COMMIT, "source_path": entry["path"], "blob_sha1": entry["blob"], "label_index": label["index"], "label_id": label["id"], "crop_id": label["crop_id"], "leaf_group": matches[0] if len(matches) == 1 else None, "local_path": str(data_root / "images" / label["id"] / parts[-1])})
    return sorted(rows, key=lambda x: x["source_path"])


def acquire_one(row: dict) -> dict:
    path = Path(row["local_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        content = path.read_bytes() if path.exists() else get_bytes(f"https://raw.githubusercontent.com/spMohanty/PlantVillage-Dataset/{SOURCE_COMMIT}/" + urllib.parse.quote(row["source_path"], safe="/"))
        git_hash = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
        if git_hash != row["blob_sha1"]:
            raise ValueError("Downloaded bytes differ from pinned Git blob")
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            size = list(image.size)
        if not path.exists():
            temp = path.with_suffix(path.suffix + ".part")
            temp.write_bytes(content)
            temp.replace(path)
        return {**row, "sha256": hashlib.sha256(content).hexdigest(), "width": size[0], "height": size[1], "status": "verified"}
    except Exception as exc:
        return {**row, "status": "failed", "error": str(exc)}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--max-per-class", type=int, default=0, help="0 acquires the complete selected subset")
    args = parser.parse_args(argv)
    args.data_root.mkdir(parents=True, exist_ok=True)
    rows = inventory(args.data_root, args.inventory)
    if args.max_per_class:
        selected = []
        rng = random.Random(26)
        for label in labels():
            available = [x for x in rows if x["label_index"] == label["index"]]
            selected.extend(rng.sample(available, min(args.max_per_class, len(available))))
        rows = selected
    write_jsonl(args.data_root / "inventory.jsonl", rows)
    results = []
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(acquire_one, rows):
            results.append(result)
            if len(results) % 250 == 0:
                print(json.dumps({"completed": len(results), "total": len(rows), "verified": sum(x["status"] == "verified" for x in results), "seconds": round(time.monotonic() - started)}), flush=True)
    write_jsonl(args.data_root / "manifest.jsonl", results)
    summary = {"source_commit": SOURCE_COMMIT, "requested": len(rows), "verified": sum(x["status"] == "verified" for x in results), "failed": sum(x["status"] != "verified" for x in results), "complete_selected_corpus": not bool(args.max_per_class), "elapsed_seconds": round(time.monotonic() - started), "class_counts": dict(collections.Counter(x["label_id"] for x in results if x["status"] == "verified"))}
    write_json(args.data_root / "acquisition_receipt.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
