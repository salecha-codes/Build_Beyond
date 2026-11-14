"""Create reproducible class-stratified group splits without exact-image leakage."""
from __future__ import annotations

import argparse
import collections
import random
from pathlib import Path

from .common import DEFAULT_DATA, labels, read_jsonl, write_json, write_jsonl


class UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def split_rows(rows: list[dict], seed: int = 26) -> tuple[list[dict], dict]:
    rows = [dict(x) for x in rows if x.get("status") == "verified"]
    uf = UnionFind(len(rows))
    seen: dict[tuple[str, str], int] = {}
    for i, row in enumerate(rows):
        keys = [("exact", row["sha256"])]
        if row.get("leaf_group"):
            keys.append(("leaf", row["leaf_group"]))
        for key in keys:
            if key in seen:
                uf.union(i, seen[key])
            else:
                seen[key] = i
    grouped: dict[int, list[int]] = collections.defaultdict(list)
    for i in range(len(rows)):
        grouped[uf.find(i)].append(i)
    by_class: dict[int, list[list[int]]] = collections.defaultdict(list)
    for group in grouped.values():
        classes = {rows[i]["label_index"] for i in group}
        if len(classes) != 1:
            raise ValueError("Conflicting labels within an exact/leaf group require review")
        by_class[next(iter(classes))].append(group)
    rng = random.Random(seed)
    counts: dict[str, dict] = {}
    for label in labels():
        groups = by_class[label["index"]]
        rng.shuffle(groups)
        if len(groups) < 3:
            raise ValueError(f"At least three independent groups required for {label['id']}")
        n = len(groups)
        n_val = max(1, round(n * 0.15))
        n_test = max(1, round(n * 0.15))
        for j, group in enumerate(groups):
            partition = "validation" if j < n_val else "test" if j < n_val + n_test else "train"
            group_id = f"source_group_{min(group):06d}"
            for i in group:
                rows[i]["split"] = partition
                rows[i]["group_id"] = group_id
        class_rows = [rows[i] for group in groups for i in group]
        counts[label["id"]] = {"files": len(class_rows), "groups": n, "partitions": dict(collections.Counter(x["split"] for x in class_rows))}
    # Exact copies remain in the manifest for traceability, but use one in training/evaluation.
    unique = []
    selected = set()
    for row in rows:
        if row["sha256"] not in selected:
            unique.append(row)
            selected.add(row["sha256"])
    receipt = {"seed": seed, "verified_files": len(rows), "unique_files": len(unique), "exact_duplicates_excluded": len(rows) - len(unique), "known_leaf_group_files": sum(bool(x.get("leaf_group")) for x in rows), "grouping_limitations": "Source leaf metadata is incomplete; exact deduplication does not establish independence of unmatched physical leaves. No full perceptual/manual review is claimed.", "class_counts": counts, "split_counts": dict(collections.Counter(x["split"] for x in unique))}
    return unique, receipt


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    p.add_argument("--seed", type=int, default=26)
    args = p.parse_args(argv)
    rows, receipt = split_rows(read_jsonl(args.data_root / "manifest.jsonl"), args.seed)
    write_jsonl(args.data_root / "splits.jsonl", rows)
    write_json(args.data_root / "split_receipt.json", receipt)
    print(receipt["split_counts"], flush=True)


if __name__ == "__main__":
    main()
