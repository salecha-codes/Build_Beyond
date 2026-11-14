"""Train a real V4 model and write transparent training/validation receipts."""
from __future__ import annotations

import argparse
import collections
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from torch.utils.data import DataLoader, Dataset

from .common import DEFAULT_DATA, MODEL_NAME, labels, read_jsonl, sha256, write_json, write_jsonl
from .model import CropModel, prepare_image


class Images(Dataset):
    def __init__(self, rows: list[dict], augment: bool = False):
        self.rows = rows
        self.augment = augment

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(row["local_path"]) as image:
            image = image.convert("RGB")
            if self.augment:
                from torchvision.transforms import functional as F
                image = F.adjust_brightness(image, random.uniform(0.85, 1.15))
                image = F.adjust_contrast(image, random.uniform(0.85, 1.15))
                if random.random() < 0.5:
                    image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                image = image.rotate(random.uniform(-15, 15), fillcolor=(124, 116, 104))
            tensor = torch.from_numpy(prepare_image(image))
        return tensor, int(row["label_index"])


def evaluate(model, loader):
    truth, predicted, all_logits = [], [], []
    model.eval()
    with torch.inference_mode():
        for x, y in loader:
            logits, _ = model(x)
            truth.extend(y.tolist())
            predicted.extend(logits.argmax(1).tolist())
            all_logits.extend(logits.tolist())
    metrics = {"samples": len(truth), "accuracy": float(accuracy_score(truth, predicted)), "macro_f1": float(f1_score(truth, predicted, labels=list(range(17)), average="macro", zero_division=0)), "per_class": classification_report(truth, predicted, labels=list(range(17)), target_names=[x["id"] for x in labels()], output_dict=True, zero_division=0), "confusion_matrix": confusion_matrix(truth, predicted, labels=list(range(17))).tolist()}
    return metrics, {"logits": all_logits, "labels": truth}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--pretrained", action="store_true")
    p.add_argument("--pretrained-checkpoint", type=Path)
    p.add_argument("--resume-checkpoint", type=Path, help="Warm-start a prior crop checkpoint; optimizer is restarted and provenance recorded")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--threads", type=int, default=3)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--max-per-class", type=int, default=0)
    p.add_argument("--freeze-backbone", action="store_true")
    p.add_argument("--seed", type=int, default=26)
    args = p.parse_args(argv)
    if args.resume_checkpoint and (args.pretrained or args.pretrained_checkpoint):
        raise ValueError("Choose either a crop checkpoint continuation or ImageNet initialization")
    if args.freeze_backbone and not (args.pretrained or args.pretrained_checkpoint):
        raise ValueError("A frozen random backbone is not a valid transfer-learning baseline")
    torch.set_num_threads(args.threads)
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    rows = read_jsonl(args.data_root / "splits.jsonl")
    partitions = {}
    for split in ["train", "validation"]:
        selected = [r for r in rows if r["split"] == split]
        if args.max_per_class:
            selected = [r for label in labels() for r in random.sample([x for x in selected if x["label_index"] == label["index"]], min(args.max_per_class if split == "train" else max(8, args.max_per_class // 4), sum(x["label_index"] == label["index"] for x in selected)))]
        partitions[split] = selected
    if not all(partitions.values()):
        raise ValueError("Training and validation data required")
    train_loader = DataLoader(Images(partitions["train"], True), batch_size=args.batch_size, shuffle=True, num_workers=args.workers)
    val_loader = DataLoader(Images(partitions["validation"]), batch_size=args.batch_size, num_workers=args.workers)
    model = CropModel(args.pretrained, args.pretrained_checkpoint)
    parent_receipt = None
    base_epochs = 0
    if args.resume_checkpoint:
        saved = torch.load(args.resume_checkpoint, map_location="cpu", weights_only=True)
        if saved.get("model_name") != MODEL_NAME:
            raise ValueError("Resume checkpoint architecture differs")
        model.load_state_dict(saved["state_dict"], strict=True)
        parent_receipt = json.loads((args.resume_checkpoint.parent / "training_receipt.json").read_text())
        base_epochs = int(saved.get("epoch", max(parent_receipt["history"], key=lambda x: x["validation_macro_f1"])["epoch"]))
    if args.freeze_backbone:
        model.freeze_backbone()
    counts = collections.Counter(r["label_index"] for r in partitions["train"])
    weights = torch.tensor([1 / max(1, counts[i]) for i in range(17)], dtype=torch.float32)
    weights /= weights.mean()
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights, label_smoothing=0.05)
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-3 if args.freeze_backbone else 1e-4)
    args.output.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output / "training_subset.jsonl", partitions["train"])
    write_jsonl(args.output / "validation_subset.jsonl", partitions["validation"])
    started = time.monotonic(); history = []; best = -1.0
    if args.resume_checkpoint:
        initial_metrics, initial_outputs = evaluate(model, val_loader)
        best = initial_metrics["macro_f1"]
        torch.save({"state_dict": model.state_dict(), "model_name": MODEL_NAME, "seed": args.seed, "epoch": base_epochs}, args.output / "best.pt")
        write_json(args.output / "validation_metrics.json", initial_metrics)
        write_json(args.output / "validation_predictions.json", initial_outputs)
    for epoch in range(args.epochs):
        model.train()
        if args.freeze_backbone:
            model.backbone.eval();model.backbone.get_classifier().train()
        loss_sum = 0.0; seen = 0
        for step, (x, y) in enumerate(train_loader):
            optimizer.zero_grad(set_to_none=True)
            logits, _ = model(x)
            loss = loss_fn(logits, y);loss.backward();optimizer.step()
            loss_sum += loss.item() * len(y);seen += len(y)
            if step % 20 == 0:
                print({"epoch": epoch + 1, "step": step, "loss": round(loss.item(), 4), "seen": seen}, flush=True)
        metrics, outputs = evaluate(model, val_loader)
        record = {"epoch": epoch + 1 + base_epochs, "train_loss": loss_sum / seen, "validation_accuracy": metrics["accuracy"], "validation_macro_f1": metrics["macro_f1"], "elapsed_seconds": round(time.monotonic() - started)}
        history.append(record);print(record, flush=True)
        write_json(args.output / "progress.json", {"history": history, "additional_epochs": args.epochs, "training_files": len(partitions["train"]), "validation_files": len(partitions["validation"]), "running": epoch + 1 < args.epochs})
        if metrics["macro_f1"] > best:
            best = metrics["macro_f1"]
            torch.save({"state_dict": model.state_dict(), "model_name": MODEL_NAME, "seed": args.seed, "epoch": epoch + 1 + base_epochs}, args.output / "best.pt")
            write_json(args.output / "validation_metrics.json", metrics)
            write_json(args.output / "validation_predictions.json", outputs)
    training_mode = parent_receipt["training_mode"] if parent_receipt else "imagenet_transfer_learning" if args.pretrained or args.pretrained_checkpoint else "supervised_from_scratch"
    receipt = {"model_name": MODEL_NAME, "training_mode": training_mode, "pretrained_checkpoint_sha256": sha256(args.pretrained_checkpoint) if args.pretrained_checkpoint else None, "resume_checkpoint_sha256": sha256(args.resume_checkpoint) if args.resume_checkpoint else None, "resumed_from_epoch": base_epochs, "optimizer_restarted": bool(args.resume_checkpoint), "parent_training_receipt": parent_receipt, "training_files": len(partitions["train"]), "validation_files": len(partitions["validation"]), "train_validation_only": True, "held_out_test_executed": False, "limited_subset": bool(args.max_per_class), "max_per_class": args.max_per_class, "epochs": args.epochs, "total_epochs_in_lineage": base_epochs + args.epochs, "seed": args.seed, "history": history, "elapsed_seconds": round(time.monotonic() - started), "application_diagnosis_validated": False, "limitations": "Validation is used during model selection. It is not a held-out test or field trial. The app must remain Uncertain until its declared release criteria are evaluated."}
    write_json(args.output / "training_receipt.json", receipt)


if __name__ == "__main__":
    main()
