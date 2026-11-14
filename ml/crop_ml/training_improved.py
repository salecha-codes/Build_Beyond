"""Full-data V4 training with cached Pillow pixels and a held-out calibration split.

Validation-selection rows alone select checkpoints. Calibration and test rows never
enter this trainer. All arrays/checkpoints/logs belong in an external output path.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import json
import math
from pathlib import Path
import random
import time

import numpy as np
from PIL import Image, ImageOps
import torch
from torch.utils.data import DataLoader, Dataset
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from .common import DEFAULT_DATA, MODEL_NAME, labels, read_jsonl, sha256, write_jsonl
from .model import CropModel


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def cache_images(rows: list[dict], directory: Path, name: str, workers: int = 4) -> Path:
    """Cache exact unnormalized RGB letterbox pixels, never augmented validation."""
    directory.mkdir(parents=True, exist_ok=True)
    path, receipt = directory / f"{name}_uint8.npy", directory / f"{name}_uint8.json"
    rows_path = directory / f"{name}_rows.jsonl"
    canonical = "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
    rows_hash = hashlib.sha256(canonical.encode()).hexdigest()
    if path.exists() and receipt.exists():
        prior = json.loads(receipt.read_text())
        array = np.load(path, mmap_mode="r")
        if prior.get("rows_sha256") == rows_hash and array.shape == (len(rows), 224, 224, 3) and array.dtype == np.uint8:
            return path
        raise ValueError(f"Existing {name} cache has a different ordered source manifest")
    array = np.lib.format.open_memmap(path, mode="w+", dtype=np.uint8, shape=(len(rows), 224, 224, 3))
    started = time.monotonic()
    def prepare(pair):
        index, row = pair
        with Image.open(row["local_path"]) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            scale = min(224 / image.width, 224 / image.height)
            size = (max(1, int(image.width * scale + .5)), max(1, int(image.height * scale + .5)))
            image = image.resize(size, Image.Resampling.BILINEAR)
            canvas = Image.new("RGB", (224, 224), (124, 116, 104))
            canvas.paste(image, ((224 - size[0]) // 2, (224 - size[1]) // 2))
            array[index] = np.asarray(canvas, dtype=np.uint8)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in pool.map(prepare, enumerate(rows)):
            pass
    array.flush()
    rows_path.write_text(canonical)
    atomic_json(receipt, {"samples": len(rows), "shape": list(array.shape), "dtype": "uint8", "layout": "NHWC",
        "rows_sha256": rows_hash, "preprocessing": "Pillow RGB BILINEAR half-up224letterbox with124,116,104padding",
        "elapsed_seconds": time.monotonic() - started})
    return path


class CachedImages(Dataset):
    def __init__(self, path: Path, rows: list[dict]):
        self.path, self.rows = str(path), rows
        self.array = None
    def __len__(self):
        return len(self.rows)
    def __getitem__(self, index):
        if self.array is None:
            self.array = np.load(self.path, mmap_mode="r")
        # Read-only mmap must not be exposed to transforms/in-place tensor writes.
        return torch.from_numpy(np.array(self.array[index], copy=True)), int(self.rows[index]["label_index"])


def normalize_batch(pixels: torch.Tensor, augment: bool) -> torch.Tensor:
    images = pixels.permute(0, 3, 1, 2).to(dtype=torch.float32).contiguous(memory_format=torch.channels_last)
    images.div_(255.)
    if augment:
        # Leaf orientation varies in real captures. Per-image rotations/flips avoid
        # learning a fixed dataset pose, without cropping away diagnostic margins.
        for axis in [-1, -2]:
            mask = torch.rand(len(images)) < .5
            if mask.any():
                images[mask] = images[mask].flip(axis)
        rotations = torch.randint(0, 4, (len(images),))
        for k in [1, 2, 3]:
            mask = rotations == k
            if mask.any():
                images[mask] = torch.rot90(images[mask], k, (-2, -1))
        shape = (len(images), 1, 1, 1)
        brightness = torch.empty(shape).uniform_(.85, 1.15)
        contrast = torch.empty(shape).uniform_(.85, 1.15)
        saturation = torch.empty(shape).uniform_(.9, 1.1)
        gray = (images * torch.tensor([.299, .587, .114]).view(1, 3, 1, 1)).sum(1, keepdim=True)
        images = (images - gray) * saturation + gray
        center = images.mean((1, 2, 3), keepdim=True)
        images = ((images - center) * contrast + center) * brightness
        images.clamp_(0., 1.)
    mean = torch.tensor([.485, .456, .406], dtype=torch.float32).view(1, 3, 1, 1)
    std = torch.tensor([.229, .224, .225], dtype=torch.float32).view(1, 3, 1, 1)
    return images.sub_(mean).div_(std).contiguous(memory_format=torch.channels_last)


def evaluate(model, loader):
    truth, predicted, logits_out = [], [], []
    model.eval()
    with torch.inference_mode():
        for pixels, targets in loader:
            # Checkpoint selection is evaluated in FP32, matching eventual export.
            logits, embeddings = model(normalize_batch(pixels, False))
            if logits.shape[1] != 17 or embeddings.shape[1] != 960 or not torch.isfinite(logits).all():
                raise RuntimeError("Invalid V4 output contract during validation")
            truth.extend(targets.tolist()); predicted.extend(logits.argmax(1).tolist()); logits_out.extend(logits.tolist())
    metrics = {"samples": len(truth), "accuracy": float(accuracy_score(truth, predicted)),
        "macro_f1": float(f1_score(truth, predicted, labels=list(range(17)), average="macro", zero_division=0)),
        "per_class": classification_report(truth, predicted, labels=list(range(17)), target_names=[x["id"] for x in labels()], output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(truth, predicted, labels=list(range(17))).tolist()}
    return metrics, {"logits": logits_out, "labels": truth}


def assert_partition(rows, source_rows, train_rows):
    source_validation = {row["sha256"]: row for row in source_rows if row["split"] == "validation"}
    train_groups = {row["group_id"] for row in train_rows}
    seen = set()
    for row in rows:
        if row.get("sha256") not in source_validation or row["sha256"] in seen:
            raise ValueError("Selection rows must be unique members of original validation")
        expected = source_validation[row["sha256"]]
        for key in ["label_index", "label_id", "local_path", "group_id"]:
            if row.get(key) != expected[key]:
                raise ValueError(f"Selection manifest changed source {key}")
        if row["group_id"] in train_groups:
            raise ValueError("Training/selection group leakage")
        seen.add(row["sha256"])
    if {row["label_index"] for row in rows} != set(range(17)):
        raise ValueError("Selection partition must retain all17 supported classes")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["full", "field-audit", "field"], default="full")
    parser.add_argument("--field-train-manifest", type=Path)
    parser.add_argument("--field-tune-manifest", type=Path)
    parser.add_argument("--extension-protocol", type=Path)
    parser.add_argument("--origin-output", type=Path)
    parser.add_argument("--fallback-checkpoint", type=Path)
    parser.add_argument("--source-max-per-class", type=int, default=400)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument("--calibration-manifest", type=Path, required=True, help="Read only to verify disjointness; never evaluated or trained")
    parser.add_argument("--resume-checkpoint", type=Path)
    parser.add_argument("--pretrained-checkpoint", type=Path)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--precision", choices=["fp32", "bf16"], default="bf16")
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--patience", type=int, default=4)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)
    if args.mode != "full":
        return field_main(args)
    if bool(args.resume_checkpoint) == bool(args.pretrained_checkpoint):
        raise ValueError("Provide exactly one crop warm-start or ImageNet checkpoint")
    torch.set_num_threads(args.threads); torch.set_num_interop_threads(1)
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    source_rows = read_jsonl(args.data_root / "splits.jsonl")
    train_rows = [row for row in source_rows if row["split"] == "train"]
    selection_rows = read_jsonl(args.selection_manifest)
    calibration_rows = read_jsonl(args.calibration_manifest)
    assert_partition(selection_rows, source_rows, train_rows)
    assert_partition(calibration_rows, source_rows, train_rows)
    if {row["group_id"] for row in selection_rows} & {row["group_id"] for row in calibration_rows}:
        raise ValueError("Selection/calibration group overlap")
    if {row["sha256"] for row in selection_rows} & {row["sha256"] for row in calibration_rows}:
        raise ValueError("Selection/calibration duplicate image overlap")
    if len(selection_rows) + len(calibration_rows) != sum(row["split"] == "validation" for row in source_rows):
        raise ValueError("Selection and calibration must partition the original validation set")
    counts = Counter(row["label_index"] for row in train_rows)
    if set(counts) != set(range(17)):
        raise ValueError("Full training set must contain every supported class")
    cache = args.output / "cache"
    train_cache = cache_images(train_rows, cache, "train", args.threads)
    val_cache = cache_images(selection_rows, cache, "selection", args.threads)
    write_jsonl(args.output / "training_subset.jsonl", train_rows)
    write_jsonl(args.output / "validation_subset.jsonl", selection_rows)
    loader_options = {"batch_size": args.batch_size, "num_workers": args.workers,
        "persistent_workers": args.workers > 0}
    train_loader = DataLoader(CachedImages(train_cache, train_rows), shuffle=True, **loader_options)
    val_loader = DataLoader(CachedImages(val_cache, selection_rows), shuffle=False, **loader_options)
    model = CropModel(checkpoint=args.pretrained_checkpoint).to(memory_format=torch.channels_last)
    base_epochs = 0
    if args.resume_checkpoint:
        saved = torch.load(args.resume_checkpoint, map_location="cpu", weights_only=True)
        if saved.get("model_name") != MODEL_NAME:
            raise ValueError("Warm-start checkpoint architecture differs")
        model.load_state_dict(saved["state_dict"], strict=True)
        base_epochs = int(saved.get("epoch", 0))
    loss_weights = torch.tensor([1 / math.sqrt(counts[i]) for i in range(17)], dtype=torch.float32)
    loss_weights /= loss_weights.mean()
    loss_fn = torch.nn.CrossEntropyLoss(weight=loss_weights, label_smoothing=.03)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4, betas=(.9, .99))
    steps_total = args.epochs * len(train_loader)
    warmup_steps = max(1, len(train_loader) // 3)
    def set_lr(step):
        ratio = (step + 1) / warmup_steps if step < warmup_steps else .05 + .95 * .5 * (1 + math.cos(math.pi * (step - warmup_steps) / max(1, steps_total - warmup_steps)))
        lr = args.learning_rate * ratio
        for group in optimizer.param_groups: group["lr"] = lr
        return lr
    history, best_score, best_epoch, stale = [], -1., base_epochs, 0
    started = time.monotonic()
    parent_receipt = None
    if args.resume_checkpoint and (args.resume_checkpoint.parent / "training_receipt.json").exists():
        parent_receipt = json.loads((args.resume_checkpoint.parent / "training_receipt.json").read_text())
    receipt = {"model_name": MODEL_NAME, "training_mode": "imagenet_transfer_learning" if args.pretrained_checkpoint else "supervised_from_scratch",
        "field_training_used": False, "field_train_manifest_sha256": None,
        "initialization": "imagenet_checkpoint" if args.pretrained_checkpoint else "continued_from_prior_crop_checkpoint",
        "pretrained_checkpoint_sha256": sha256(args.pretrained_checkpoint) if args.pretrained_checkpoint else None,
        "resume_checkpoint_sha256": sha256(args.resume_checkpoint) if args.resume_checkpoint else None,
        "resumed_from_epoch": base_epochs, "parent_training_receipt": parent_receipt,
        "optimizer_restarted": True, "training_files": len(train_rows), "validation_files": len(selection_rows),
        "reserved_calibration_files": len(calibration_rows), "calibration_evaluated": False,
        "train_validation_only": True, "held_out_test_executed": False, "limited_subset": False,
        "source_split_sha256": sha256(args.data_root / "splits.jsonl"),
        "selection_manifest_sha256": sha256(args.selection_manifest), "calibration_manifest_sha256": sha256(args.calibration_manifest),
        "class_counts": dict(counts), "class_weighting": "inverse_sqrt_training_frequency", "label_smoothing": .03,
        "augmentation": "per-image horizontal/vertical flip;90degreeorientation; brightness/contrast0.85to1.15;saturation0.9to1.1",
        "optimizer": {"name": "AdamW", "learning_rate": args.learning_rate, "weight_decay": 1e-4, "schedule": "one-third-epochwarmupthen12-epochcosinefloor0.05"},
        "precision": args.precision, "memory_format": "channels_last", "batch_size": args.batch_size,
        "threads": args.threads, "workers": args.workers, "seed": args.seed, "max_epochs": args.epochs,
        "epochs": 0, "total_epochs_in_lineage": base_epochs, "history": history, "running": True,
        "application_diagnosis_validated": False,
        "limitations": "Source-selection validation selects checkpoints. Reserved calibration and final test are untouched by this trainer. Source-domain performance is not field validation."}
    atomic_json(args.output / "training_receipt.json", receipt)
    def save_best(epoch, metrics, outputs):
        temporary = args.output / "best.tmp"
        torch.save({"state_dict": model.state_dict(), "model_name": MODEL_NAME, "seed": args.seed, "epoch": epoch}, temporary)
        temporary.replace(args.output / "best.pt")
        atomic_json(args.output / "validation_metrics.json", metrics)
        atomic_json(args.output / "validation_predictions.json", outputs)
    initial_metrics, initial_outputs = evaluate(model, val_loader)
    best_score = initial_metrics["macro_f1"]
    save_best(base_epochs, initial_metrics, initial_outputs)
    atomic_json(args.output / "initial_selection_metrics.json", initial_metrics)
    print(json.dumps({"event": "initial_selection", "accuracy": initial_metrics["accuracy"], "macro_f1": best_score,
        "training_files": len(train_rows), "selection_files": len(selection_rows), "reserved_calibration_files": len(calibration_rows)}), flush=True)
    step_global = 0
    for epoch in range(1, args.epochs + 1):
        epoch_started = time.monotonic(); model.train(); loss_sum = 0.; correct = 0; seen = 0
        for step, (pixels, targets) in enumerate(train_loader):
            learning_rate = set_lr(step_global)
            images = normalize_batch(pixels, True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast("cpu", dtype=torch.bfloat16, enabled=args.precision == "bf16"):
                logits, _ = model(images)
                loss = loss_fn(logits.float(), targets)
            if not torch.isfinite(loss): raise RuntimeError("Training loss is not finite")
            loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 5.); optimizer.step()
            seen += len(targets); loss_sum += float(loss.detach()) * len(targets)
            correct += int((logits.detach().argmax(1) == targets).sum()); step_global += 1
            if step % 50 == 0:
                progress = {"event": "training_step", "epoch": epoch, "lineage_epoch": base_epochs + epoch,
                    "step": step, "steps": len(train_loader), "seen": seen, "training_files": len(train_rows),
                    "loss": loss_sum / seen, "learning_rate": learning_rate,
                    "epoch_elapsed_seconds": time.monotonic() - epoch_started, "running": True, "history": history}
                atomic_json(args.output / "progress.json", progress)
                print(json.dumps({key: value for key, value in progress.items() if key != "history"}), flush=True)
        metrics, outputs = evaluate(model, val_loader)
        improved = metrics["macro_f1"] > best_score + 1e-5
        record = {"epoch": base_epochs + epoch, "stage_epoch": epoch, "train_loss": loss_sum / seen,
            "train_accuracy_augmented": correct / seen, "validation_accuracy": metrics["accuracy"],
            "validation_macro_f1": metrics["macro_f1"], "learning_rate": learning_rate,
            "epoch_seconds": time.monotonic() - epoch_started, "elapsed_seconds": time.monotonic() - started,
            "checkpoint_improved": improved}
        history.append(record)
        if improved:
            best_score, best_epoch, stale = metrics["macro_f1"], base_epochs + epoch, 0
            save_best(best_epoch, metrics, outputs)
        else:
            stale += 1
        torch.save({"state_dict": model.state_dict(), "optimizer": optimizer.state_dict(), "model_name": MODEL_NAME,
            "seed": args.seed, "epoch": base_epochs + epoch}, args.output / "last.pt")
        stop = epoch >= 3 and stale >= args.patience
        receipt.update({"epochs": epoch, "total_epochs_in_lineage": base_epochs + epoch, "history": history,
            "best_epoch": best_epoch, "best_validation_macro_f1": best_score, "running": epoch < args.epochs and not stop,
            "elapsed_seconds": time.monotonic() - started, "early_stopped": stop})
        atomic_json(args.output / "training_receipt.json", receipt)
        atomic_json(args.output / "progress.json", {"history": history, "running": receipt["running"], "best_epoch": best_epoch})
        print(json.dumps({"event": "epoch_complete", **record, "best_epoch": best_epoch}), flush=True)
        if stop: break
    receipt["running"] = False
    receipt["best_checkpoint_sha256"] = sha256(args.output / "best.pt")
    atomic_json(args.output / "training_receipt.json", receipt)
    print(json.dumps({"event": "training_complete", "best_epoch": best_epoch, "best_macro_f1": best_score}), flush=True)

class MixedBatches:
    """Visit the capped source pool once; include ten field images per32-image batch."""
    def __init__(self, source_count, field_count, batch_size=32, field_fraction=.3):
        self.source_count, self.field_count = source_count, field_count
        self.field_per_batch = max(1, round(batch_size * field_fraction))
        self.source_per_batch = batch_size - self.field_per_batch
    def __len__(self):
        return math.ceil(self.source_count / self.source_per_batch)
    def __iter__(self):
        order = torch.randperm(self.source_count).tolist()
        for start in range(0, self.source_count, self.source_per_batch):
            source = order[start:start+self.source_per_batch]
            if len(source) < self.source_per_batch:
                source.extend(torch.randint(self.source_count, (self.source_per_batch-len(source),)).tolist())
            field = (torch.randint(self.field_count, (self.field_per_batch,)) + self.source_count).tolist()
            batch = source + field
            random.shuffle(batch)
            yield batch


def field_main(args):
    """Audit frozen TUNE partitions or fine-tune mixed TRAIN data; never read CAL pixels."""
    import shutil
    if not args.resume_checkpoint or not args.field_train_manifest or not args.field_tune_manifest:
        raise ValueError("Field mode requires a locked base crop checkpoint and field train/tune manifests")
    extension = bool(args.extension_protocol)
    max_epochs = 8 if extension else 4
    if args.epochs > max_epochs and args.mode == "field":
        raise ValueError("Mixed-domain stage exceeds its predeclared epoch limit")
    if extension and (not args.origin_output or not args.fallback_checkpoint):
        raise ValueError("Extension requires original frozen base audit and fallback checkpoint")
    fallback = args.fallback_checkpoint if extension else args.resume_checkpoint
    torch.set_num_threads(args.threads); torch.set_num_interop_threads(1)
    torch.manual_seed(args.seed); random.seed(args.seed); np.random.seed(args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    source_rows = read_jsonl(args.data_root / "splits.jsonl")
    source_train = [row for row in source_rows if row["split"] == "train"]
    source_tune = read_jsonl(args.selection_manifest)
    assert_partition(source_tune, source_rows, source_train)
    field_train, field_tune = read_jsonl(args.field_train_manifest), read_jsonl(args.field_tune_manifest)
    for part, expected in [(field_train, "train"), (field_tune, "tune")]:
        if not part or any(row.get("partition") != expected or row.get("source") != "plantdoc" or
            row.get("label_index") not in range(17) or labels()[row["label_index"]]["id"] != row.get("label_id") for row in part):
            raise ValueError("Invalid canonical field partition")
    for key in ["sha256", "group_id"]:
        if {row[key] for row in field_train} & {row[key] for row in field_tune}:
            raise ValueError(f"Field train/tune overlap: {key}")
        if {row[key] for row in source_train} & {row[key] for row in field_tune}:
            raise ValueError(f"Source training/field tune overlap: {key}")
    base_receipt_path = args.resume_checkpoint.parent / "training_receipt.json"
    if base_receipt_path.exists() and json.loads(base_receipt_path.read_text()).get("running"):
        raise ValueError("Finish the full source stage before auditing field TUNE")
    seed_rng = random.Random(args.seed)
    capped = []
    for index in range(17):
        pool = [row for row in source_train if row["label_index"] == index]
        capped.extend(seed_rng.sample(pool, min(args.source_max_per_class, len(pool))))
    field_classes = sorted({row["label_index"] for row in field_tune})
    protocol = {
        "schema_version": 1, "protocol": "predeclared_by_parent_before_field_tune_inference",
        "base_checkpoint_sha256": sha256(fallback),
        "source_tune_manifest_sha256": sha256(args.selection_manifest),
        "field_train_manifest_sha256": sha256(args.field_train_manifest),
        "field_tune_manifest_sha256": sha256(args.field_tune_manifest),
        "source_train_cap_per_class": args.source_max_per_class, "seed": args.seed,
        "field_macro_classes": field_classes, "global_logit_count": 17,
        "source_accuracy_max_drop": .02, "source_macro_f1_max_drop": .02,
        "required_field_accuracy_or_macro_f1_gain": .05,
        "selection_order": ["maximum_field_supported_class_macro_f1", "maximum_source_macro_f1"],
        "max_epochs": 4, "source_rows": len(capped), "field_train_rows": len(field_train),
        "field_fraction": .3, "batchnorm_running_statistics": "frozen_to_base",
        "calibration_evaluated": False, "final_test_evaluated": False,
        "field_labels": "source_dataset_candidates_mostly_not_visually_or_agronomist_reviewed",
    }
    if extension:
        amendment = json.loads(args.extension_protocol.read_text())
        if amendment.get("source_accuracy_absolute_floor") != .90 or amendment.get("source_macro_f1_absolute_floor") != .90:
            raise ValueError("Extension amendment does not contain authorized source floors")
        if sha256(fallback) != amendment.get("frozen_reference_source_checkpoint_sha256"):
            raise ValueError("Extension fallback is not the frozen original source base")
        origin_protocol = json.loads((args.origin_output / "field_selection_protocol.json").read_text())
        for key in ["base_checkpoint_sha256", "source_tune_manifest_sha256", "field_train_manifest_sha256", "field_tune_manifest_sha256"]:
            if protocol[key] != origin_protocol[key]:
                raise ValueError("Extension changed a frozen source or field manifest")
        protocol.pop("source_accuracy_max_drop"); protocol.pop("source_macro_f1_max_drop")
        protocol.update({"max_epochs": 8, "extension_amendment": amendment,
            "source_accuracy_absolute_floor": .90, "source_macro_f1_absolute_floor": .90,
            "initialization_checkpoint_sha256": sha256(args.resume_checkpoint),
            "extension_protocol_sha256": sha256(args.extension_protocol)})
    protocol_path = args.output / "field_selection_protocol.json"
    if protocol_path.exists():
        if json.loads(protocol_path.read_text()) != protocol:
            raise ValueError("Field protocol or manifest changed since frozen audit")
    else:
        atomic_json(protocol_path, protocol)
    cache = args.output / "cache"
    if extension and not cache.exists():
        cache.symlink_to((args.origin_output / "cache").resolve(), target_is_directory=True)
    source_val_path = cache_images(source_tune, cache, "source_tune", args.threads)
    field_val_path = cache_images(field_tune, cache, "field_tune", args.threads)
    options = {"batch_size": args.batch_size, "num_workers": args.workers, "persistent_workers": args.workers > 0}
    source_loader = DataLoader(CachedImages(source_val_path, source_tune), shuffle=False, **options)
    field_loader = DataLoader(CachedImages(field_val_path, field_tune), shuffle=False, **options)
    saved = torch.load(args.resume_checkpoint, map_location="cpu", weights_only=True)
    if saved.get("model_name") != MODEL_NAME:
        raise ValueError("Field warm-start is not the agreed V4 model")
    model = CropModel().to(memory_format=torch.channels_last)
    model.load_state_dict(saved["state_dict"], strict=True)
    base_source, source_outputs = evaluate(model, source_loader)
    base_field, field_outputs = evaluate(model, field_loader)
    def field_metrics(metrics, outputs):
        prediction = np.asarray(outputs["logits"]).argmax(1)
        metrics["macro_f1_all_17"] = metrics["macro_f1"]
        metrics["macro_f1"] = float(f1_score(outputs["labels"], prediction, labels=field_classes, average="macro", zero_division=0))
        metrics["macro_f1_scope"] = "field_tune_supported_canonical_classes"
        metrics["supported_class_indices"] = field_classes
        return metrics
    base_field = field_metrics(base_field, field_outputs)
    if extension:
        atomic_json(args.output / "initialization_source_tune_metrics.json", base_source)
        atomic_json(args.output / "initialization_field_tune_metrics.json", base_field)
        base_source = json.loads((args.origin_output / "base_source_tune_metrics.json").read_text())
        base_field = json.loads((args.origin_output / "base_field_tune_metrics.json").read_text())
    atomic_json(args.output / "base_source_tune_metrics.json", base_source)
    atomic_json(args.output / "base_field_tune_metrics.json", base_field)
    atomic_json(args.output / ("initialization_field_tune_predictions.json" if extension else "base_field_tune_predictions.json"), field_outputs)
    print(json.dumps({"event": "base_field_tune_audit", "source_accuracy": base_source["accuracy"],
        "source_macro_f1": base_source["macro_f1"], "field_accuracy": base_field["accuracy"],
        "field_macro_f1": base_field["macro_f1"], "field_samples": len(field_tune), "field_supported_classes": len(field_classes)}), flush=True)
    if args.mode == "field-audit":
        return
    combined_train = capped + field_train
    train_path = cache_images(combined_train, cache, "mixed_train", args.threads)
    write_jsonl(args.output / "mixed_training_rows.jsonl", combined_train)
    batches = MixedBatches(len(capped), len(field_train), args.batch_size)
    train_loader = DataLoader(CachedImages(train_path, combined_train), batch_sampler=batches,
        num_workers=args.workers, persistent_workers=args.workers > 0)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4, betas=(.9,.99))
    loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=.03)
    total_steps = args.epochs * len(train_loader); warmup = max(1, len(train_loader) // 5)
    history, best_key, best_path, stale = [], None, fallback, 0
    started = time.monotonic(); step_global = 0
    receipt = {"model_name": MODEL_NAME, "training_mode": "supervised_from_scratch_mixed_domain_continuation",
        "field_training_used": True, "field_train_manifest_sha256": protocol["field_train_manifest_sha256"],
        "base_checkpoint_sha256": protocol["base_checkpoint_sha256"], "field_selection_protocol": protocol,
        "training_files": len(combined_train), "source_training_files": len(capped), "field_training_files": len(field_train),
        "validation_files": len(source_tune), "field_validation_files": len(field_tune),
        "train_validation_only": True, "held_out_test_executed": False, "calibration_evaluated": False,
        "application_diagnosis_validated": False, "precision": args.precision, "learning_rate": args.learning_rate,
        "seed": args.seed, "history": history, "epochs": 0, "running": True,
        "field_label_limitations": protocol["field_labels"],
        "parent_training_receipt": json.loads(base_receipt_path.read_text()) if base_receipt_path.exists() else None}
    atomic_json(args.output / "training_receipt.json", receipt)
    for epoch in range(1, args.epochs+1):
        epoch_started = time.monotonic(); model.train()
        for module in model.modules():
            if isinstance(module, torch.nn.modules.batchnorm._BatchNorm):
                module.eval()
        loss_sum = 0.; seen = 0
        for pixels, targets in train_loader:
            ratio = (step_global+1)/warmup if step_global < warmup else .2+.8*.5*(1+math.cos(math.pi*(step_global-warmup)/max(1,total_steps-warmup)))
            for group in optimizer.param_groups: group["lr"] = args.learning_rate*ratio
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast("cpu",dtype=torch.bfloat16,enabled=args.precision=="bf16"):
                logits,_ = model(normalize_batch(pixels,True)); loss = loss_fn(logits.float(),targets)
            if not torch.isfinite(loss): raise RuntimeError("Mixed-domain loss is not finite")
            loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5.);optimizer.step()
            loss_sum += float(loss.detach())*len(targets); seen += len(targets);step_global += 1
        source,source_outputs = evaluate(model,source_loader)
        field,field_outputs = evaluate(model,field_loader);field = field_metrics(field,field_outputs)
        retained = (source["accuracy"] >= .90 and source["macro_f1"] >= .90) if extension else (source["accuracy"] >= base_source["accuracy"]-.02 and source["macro_f1"] >= base_source["macro_f1"]-.02)
        gained = field["accuracy"] >= base_field["accuracy"]+.05 or field["macro_f1"] >= base_field["macro_f1"]+.05
        eligible = retained and gained
        candidate_key = (field["macro_f1"],source["macro_f1"])
        selected = eligible and (best_key is None or candidate_key > best_key)
        record = {"stage_epoch":epoch,"train_loss":loss_sum/seen,"samples_seen":seen,
            "source_tune_accuracy":source["accuracy"],"source_tune_macro_f1":source["macro_f1"],
            "field_tune_accuracy":field["accuracy"],"field_tune_macro_f1":field["macro_f1"],
            "source_retained":retained,"field_gain_qualified":gained,"eligible":eligible,"selected":selected,
            "epoch_seconds":time.monotonic()-epoch_started,"elapsed_seconds":time.monotonic()-started}
        history.append(record)
        candidate_path = args.output/f"candidate_epoch_{epoch}.pt"
        torch.save({"state_dict":model.state_dict(),"model_name":MODEL_NAME,"seed":args.seed,
            "epoch":int(saved.get("epoch",0))+epoch,"field_training_used":True},candidate_path)
        atomic_json(args.output/f"candidate_epoch_{epoch}_source_tune.json",source)
        atomic_json(args.output/f"candidate_epoch_{epoch}_field_tune.json",field)
        if selected:
            best_key,best_path,stale = candidate_key,candidate_path,0
            shutil.copy2(candidate_path,args.output/"best.pt")
            atomic_json(args.output/"validation_metrics.json",source)
            atomic_json(args.output/"validation_predictions.json",source_outputs)
        else: stale += 1
        receipt.update({"epochs":epoch,"history":history,"running":epoch<args.epochs,"elapsed_seconds":time.monotonic()-started})
        atomic_json(args.output/"training_receipt.json",receipt)
        print(json.dumps({"event":"mixed_epoch_complete",**record}),flush=True)
        if not extension and epoch>=2 and stale>=2:
            break
    selected_path = args.output/"best.pt" if best_key is not None else fallback
    receipt["running"] = False
    receipt["selected_mixed_candidate"] = best_key is not None
    receipt["best_checkpoint_sha256"] = sha256(selected_path)
    atomic_json(args.output/"training_receipt.json",receipt)
    atomic_json(args.output/"selection_result.json",{"selected_checkpoint":str(selected_path),
        "selected_checkpoint_sha256":sha256(selected_path),"field_training_used":best_key is not None,
        "field_train_manifest_sha256":protocol["field_train_manifest_sha256"] if best_key is not None else None,
        "reason":"Predeclared source-retention and field-improvement criteria" if best_key is not None else "No mixed candidate qualified; retain frozen full-source base",
        "history":history,"calibration_evaluated":False,"held_out_test_executed":False})
    print(json.dumps({"event":"mixed_stage_complete","selected_checkpoint":str(selected_path),"field_training_used":best_key is not None}),flush=True)


if __name__ == "__main__":
    main()
