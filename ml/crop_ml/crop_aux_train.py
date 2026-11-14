"""Isolated V4 experiment: improve field crop recognition with crop-mass loss.

The deployed classifier still has 17 global logits. This trainer adds no runtime
head and never renormalizes predictions to the farmer's selected crop. It uses
source/field TRAIN for gradients, source/field TUNE for selection, no CAL/test.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import random
import time

import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score
from torch.utils.data import DataLoader, Sampler

from .common import MODEL_NAME, read_jsonl
from .model import CropModel
from .training_improved import CachedImages, evaluate, normalize_batch


def sha(path: Path) -> str:
    digest = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, data) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def crop_index(class_indices: torch.Tensor) -> torch.Tensor:
    # Canonical global order: maize 0..3, potato 4..6, tomato 7..16.
    return torch.where(class_indices < 4, 0, torch.where(class_indices < 7, 1, 2))


def crop_mass_logits(logits: torch.Tensor) -> torch.Tensor:
    # log(sum(exp(logit))) preserves the exact three crop probability masses
    # of the same 17-way softmax. No crop masking or score reinterpretation.
    return torch.stack([torch.logsumexp(logits[:, :4], dim=1),
                        torch.logsumexp(logits[:, 4:7], dim=1),
                        torch.logsumexp(logits[:, 7:], dim=1)], dim=1)


class BalancedCropBatches(Sampler[list[int]]):
    def __init__(self, rows: list[dict], steps: int = 150):
        self.steps = steps
        self.source = [[], [], []]
        self.field = [[], [], []]
        for index, row in enumerate(rows):
            target = self.field if row.get('source') == 'plantdoc' else self.source
            target[0 if row['label_index'] < 4 else 1 if row['label_index'] < 7 else 2].append(index)
        if any(not group for domain in [self.source, self.field] for group in domain):
            raise ValueError('Every crop needs TRAIN support in both domains')
    def __len__(self): return self.steps
    def __iter__(self):
        for _ in range(self.steps):
            # Eighteen source + eighteen field images, six of each crop/domain.
            batch = [random.choice(group) for group in self.source for _ in range(6)]
            batch += [random.choice(group) for group in self.field for _ in range(6)]
            yield batch


def metrics(model, loader, field_classes=None) -> dict:
    _, outputs = evaluate(model, loader)
    truth = np.asarray(outputs['labels'], dtype=np.int64)
    predicted = np.asarray(outputs['logits']).argmax(1)
    crop_truth = np.where(truth < 4, 0, np.where(truth < 7, 1, 2))
    crop_pred = np.where(predicted < 4, 0, np.where(predicted < 7, 1, 2))
    report = {'accuracy': float(accuracy_score(truth, predicted)),
              'macro_f1_all_17': float(f1_score(truth, predicted, labels=list(range(17)), average='macro', zero_division=0)),
              'crop_accuracy': float(accuracy_score(crop_truth, crop_pred)),
              'crop_recall': {name: float((crop_pred[crop_truth == index] == index).mean())
                              for index, name in enumerate(['maize', 'potato', 'tomato'])
                              if (crop_truth == index).any()}}
    if field_classes:
        report['macro_f1_supported_10'] = float(f1_score(truth, predicted, labels=field_classes,
                                                         average='macro', zero_division=0))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path,
                        default=Path('/workspace/crop-artifacts/full_training/field_extension/best.pt'))
    parser.add_argument('--cache', type=Path,
                        default=Path('/workspace/crop-artifacts/full_training/field_adaptation/cache'))
    parser.add_argument('--output', type=Path,
                        default=Path('/workspace/crop-artifacts/field_experiments/crop_aux'))
    parser.add_argument('--threads', type=int, default=3)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.manual_seed(2604); np.random.seed(2604); random.seed(2604)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    names = {'train': 'mixed_train', 'source_tune': 'source_tune', 'field_tune': 'field_tune'}
    manifests = {key: args.cache / f'{name}_rows.jsonl' for key, name in names.items()}
    pixels = {key: args.cache / f'{name}_uint8.npy' for key, name in names.items()}
    rows = {key: read_jsonl(path) for key, path in manifests.items()}
    if [len(rows[key]) for key in names] != [6956, 2228, 138]:
        raise ValueError('Frozen partition sizes differ')
    if [r.get('source') == 'plantdoc' for r in rows['train']] != [False]*6324 + [True]*632:
        raise ValueError('Unexpected TRAIN domain order')
    image_hashes = {key: {r['sha256'] for r in values} for key, values in rows.items()}
    if image_hashes['train'] & (image_hashes['source_tune'] | image_hashes['field_tune']) or \
       image_hashes['source_tune'] & image_hashes['field_tune']:
        raise ValueError('TRAIN/TUNE image overlap')
    field_classes = sorted({r['label_index'] for r in rows['field_tune']})
    protocol = {'schema_version': 1, 'experiment': 'v4_crop_auxiliary_mass_loss',
                'base_checkpoint_sha256': sha(args.checkpoint),
                'manifest_sha256': {key: sha(path) for key, path in manifests.items()},
                'source_train': 6324, 'field_train': 632, 'source_tune': 2228, 'field_tune': 138,
                'field_supported_classes': field_classes,
                'global_logit_count': 17,
                'loss_weights': {'source_disease': .35, 'field_disease': .45, 'field_crop_mass': .20},
                'crop_mass_groups': [[0, 1, 2, 3], [4, 5, 6], list(range(7, 17))],
                'sampling': '18_source_and_18_field_equal_crop_counts_with_replacement',
                'epochs_max': 3, 'steps_per_epoch': 150,
                'optimizer': 'AdamW', 'learning_rate': .00007, 'label_smoothing': .02,
                'source_accuracy_floor': .90, 'source_macro_f1_floor': .90,
                'field_accuracy_gain_for_release': .01,
                'field_supported_macro_f1_gain_for_release': .05,
                'selection_order': ['field_supported_macro_f1', 'source_macro_f1'],
                'seed': 2604, 'calibration_or_final_test_used': False}
    protocol_path = out / 'protocol.json'
    if protocol_path.exists() and json.loads(protocol_path.read_text()) != protocol:
        raise ValueError('Existing frozen protocol changed')
    if not protocol_path.exists(): atomic_json(protocol_path, protocol)
    checkpoint = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
    if checkpoint.get('model_name') != MODEL_NAME:
        raise ValueError('Wrong MobileNetV4 checkpoint')
    model = CropModel().to(memory_format=torch.channels_last)
    model.load_state_dict(checkpoint['state_dict'], strict=True)
    loaders = {
        'train': DataLoader(CachedImages(pixels['train'], rows['train']),
                            batch_sampler=BalancedCropBatches(rows['train']),
                            num_workers=2, persistent_workers=True),
        'source_tune': DataLoader(CachedImages(pixels['source_tune'], rows['source_tune']),
                                  batch_size=48, num_workers=2, persistent_workers=True),
        'field_tune': DataLoader(CachedImages(pixels['field_tune'], rows['field_tune']),
                                 batch_size=48, num_workers=2, persistent_workers=True),
    }
    base_source = metrics(model, loaders['source_tune'])
    base_field = metrics(model, loaders['field_tune'], field_classes)
    if abs(base_source['accuracy']-.9528725314183124) > .00001 or \
       abs(base_field['accuracy']-.2971014492753623) > .00001:
        raise ValueError('Frozen model baseline does not reproduce selected checkpoint')
    baseline = {'source': base_source, 'field': base_field}
    print(json.dumps({'event': 'baseline', **baseline}), flush=True)
    loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=.02)
    optimizer = torch.optim.AdamW(model.parameters(), lr=protocol['learning_rate'], weight_decay=1e-4)
    history, best_key = [], (base_field['macro_f1_supported_10'], base_source['macro_f1_all_17'])
    started = time.monotonic()
    for epoch in range(1, protocol['epochs_max']+1):
        model.train()
        for layer in model.modules():
            if isinstance(layer, torch.nn.modules.batchnorm._BatchNorm): layer.eval()
        loss_sum = 0.
        for images, truth in loaders['train']:
            scores, _ = model(normalize_batch(images, True))
            source_loss = loss_fn(scores[:18], truth[:18])
            field_loss = loss_fn(scores[18:], truth[18:])
            field_crop_loss = loss_fn(crop_mass_logits(scores[18:]), crop_index(truth[18:]))
            loss = .35*source_loss + .45*field_loss + .20*field_crop_loss
            optimizer.zero_grad(set_to_none=True); loss.backward(); optimizer.step()
            loss_sum += float(loss.item())
        source = metrics(model, loaders['source_tune'])
        field = metrics(model, loaders['field_tune'], field_classes)
        eligible = (source['accuracy'] >= .90 and source['macro_f1_all_17'] >= .90 and
                    field['accuracy'] >= base_field['accuracy']+.01 and
                    field['macro_f1_supported_10'] >= base_field['macro_f1_supported_10']+.05)
        key = (field['macro_f1_supported_10'], source['macro_f1_all_17'])
        chosen = eligible and key > best_key
        record = {'epoch': epoch, 'source': source, 'field': field,
                  'loss': loss_sum/len(loaders['train']), 'eligible': eligible,
                  'selected': chosen, 'elapsed_seconds': time.monotonic()-started}
        history.append(record)
        print(json.dumps({'event': 'epoch_complete', **record}), flush=True)
        if chosen:
            best_key = key
            torch.save({'state_dict': model.state_dict(), 'model_name': MODEL_NAME,
                        'epoch': checkpoint['epoch']+epoch,
                        'base_checkpoint_sha256': protocol['base_checkpoint_sha256']}, out/'best.pt')
        atomic_json(out/'history.json', {'baseline': baseline, 'history': history, 'best_key': best_key})
    print(json.dumps({'event': 'complete', 'best_key': best_key,
                      'field_macro_gain': best_key[0]-base_field['macro_f1_supported_10']}), flush=True)


if __name__ == '__main__': main()
