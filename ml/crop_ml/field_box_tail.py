"""TRAIN-only V3 disease-tail adaptation with photo-balanced verified leaf boxes.

Original leaf branch is frozen; selection uses unchanged whole-photo TUNE only.
No calibration or test manifests are read by this experiment.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image
import torch
from torch import nn
from torch.nn import functional as F

from .box_crop_train import cache_box_views
from .common import read_jsonl
from .field_tail_finetune import (
    CACHE, HEAD, LEAF, WEIGHTS, PreservedLeafTail, cache_early, evaluate, sha, write,
)

BOX_MANIFEST = Path('/workspace/crop-data/plantdoc-boxes/train_boxes.jsonl')
BOX_RECEIPT = BOX_MANIFEST.with_name('receipt.json')
BOX_CACHE = Path('/workspace/crop-artifacts/box_crop_v2/cache')
OLD_EARLY = Path('/workspace/crop-artifacts/field_tail')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/workspace/crop-artifacts/field_box_tail'))
    parser.add_argument('--threads', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.threads <= 3:
        raise ValueError('Use at most three CPU threads')
    if args.output.exists():
        raise FileExistsError('Use a fresh experiment directory')
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.manual_seed(2613)
    rng = np.random.default_rng(2613)
    paths = {name: CACHE / filename for name, filename in {
        'train': 'mixed_train_rows.jsonl', 'source': 'source_tune_rows.jsonl',
        'field': 'field_tune_rows.jsonl',
    }.items()}
    rows = {key: read_jsonl(path) for key, path in paths.items()}
    source_indices = np.array([i for i, row in enumerate(rows['train']) if row['source'] == 'plantvillage'])
    field_indices = np.array([i for i, row in enumerate(rows['train']) if row['source'] != 'plantvillage'])
    assert (len(source_indices), len(field_indices)) == (6324, 632)
    train_sha = {r['sha256'] for r in rows['train']}
    train_groups = {r['group_id'] for r in rows['train']}
    for split in ('source', 'field'):
        assert not train_sha.intersection(r['sha256'] for r in rows[split])
        assert not train_groups.intersection(r['group_id'] for r in rows[split])
    field_by_sha = {rows['train'][i]['sha256']: rows['train'][i] for i in field_indices}
    receipt = json.loads(BOX_RECEIPT.read_text())
    assert receipt['manifest_sha256'] == sha(BOX_MANIFEST)
    boxes = read_jsonl(BOX_MANIFEST)
    usable, excluded = [], []
    for row in boxes:
        source = field_by_sha[row['image_sha256']]
        assert row['original_partition'] == 'train'
        assert all(row[key] == source[key] for key in ('label_id', 'label_index', 'group_id'))
        with Image.open(row['local_path']) as image:
            valid = image.getexif().get(274, 1) in (0, 1) and image.size == (row['width'], row['height'])
        (usable if valid else excluded).append(row)
    flattened, photo_boxes = [], []
    for row in usable:
        indices = []
        for index, box in enumerate(row['boxes']):
            indices.append(len(flattened))
            flattened.append({**{k: v for k, v in row.items() if k != 'boxes'}, 'box': box, 'box_index': index})
        photo_boxes.append(np.array(indices))
    assert (len(usable), len(excluded), len(flattened)) == (604, 12, 1472)
    # This verifies the complete flattened row hash and RGB224 cache shape/dtype.
    pixels = cache_box_views(flattened, BOX_CACHE, args.threads)
    args.output.mkdir(parents=True)
    protocol = {
        'schema_version': 1, 'method': 'frozen_leaf_branch_last3_disease_tail_verified_box_context',
        'seed': 2613, 'epochs': 3, 'steps_per_epoch': 150,
        'batch_source': 16, 'batch_field_whole': 8, 'batch_field_box': 8,
        'box_sampling': 'uniform eligible original TRAIN photo then uniform box within photo',
        'box_context_fraction': .1, 'box_train_photos': 604, 'box_train_views': 1472,
        'excluded_EXIF_or_dimensions_photos': 12,
        'excluded_photo_ids': [r['id'] for r in excluded],
        'disease_tail_learning_rate': 1e-5, 'head_learning_rate': 5e-5,
        'label_smoothing': .03, 'batchnorm_running_stats': 'frozen',
        'source_accuracy_floor': .90, 'source_macro_f1_floor': .90,
        'field_accuracy_floor': .5472, 'field_macro_f1_floor': .55393,
        'weights_sha256': sha(WEIGHTS), 'base_head_sha256': sha(HEAD), 'leaf_head_sha256': sha(LEAF),
        'manifest_sha256': {key: sha(path) for key, path in paths.items()},
        'box_manifest_sha256': sha(BOX_MANIFEST), 'box_cache_receipt_sha256': sha(BOX_CACHE / 'box_views_uint8.json'),
        'calibration_or_test_used': False, 'tune_views': 'original whole photographs only',
        'leaf_path_trainable': False, 'inference_preprocessing_changed': False,
        'train_tune_sha_and_group_disjoint': True,
    }
    write(args.output / 'protocol.json', protocol)
    model = PreservedLeafTail().eval()
    original_leaf = {key: value.clone() for key, value in model.state_dict().items()
                     if key.startswith(('early.', 'leaf_tail.', 'leaf_'))}
    cached = {}
    old_protocol = json.loads((OLD_EARLY / 'protocol.json').read_text())
    for key in paths:
        assert old_protocol['manifest_sha256'][key] == protocol['manifest_sha256'][key]
        assert old_protocol['weights_sha256'] == protocol['weights_sha256']
        original = OLD_EARLY / (key + '_early.npy')
        cached[key] = np.load(original, mmap_mode='r')
        assert cached[key].shape == (len(rows[key]), 160, 7, 7)
    print(json.dumps({'event': 'box_early_cache_start', 'photos': 604, 'boxes': 1472}), flush=True)
    cached['boxes'] = cache_early(model, pixels, args.output / 'boxes_early.npy')
    labels = {key: np.array([r['label_index'] for r in value]) for key, value in rows.items()}
    labels['boxes'] = np.array([r['label_index'] for r in flattened])
    classes = sorted(set(labels['field']))
    def measure():
        return (evaluate(model, cached['source'], labels['source'], list(range(17))),
                evaluate(model, cached['field'], labels['field'], classes))
    source, field = measure()
    assert abs(source['accuracy'] - .9245960502692998) < 1e-9
    assert abs(field['accuracy'] - .5072463768115942) < 1e-9
    print(json.dumps({'event': 'baseline', 'source': source, 'field': field}), flush=True)
    optimizer = torch.optim.AdamW([
        {'params': model.disease_tail.parameters(), 'lr': 1e-5},
        {'params': model.head.parameters(), 'lr': 5e-5},
    ], weight_decay=1e-4)
    trainable = list(model.disease_tail.parameters()) + list(model.head.parameters())
    started, history, best = time.monotonic(), [], None
    for epoch in range(1, 4):
        model.disease_tail.train()
        model.head.train()
        for module in model.disease_tail.modules():
            if isinstance(module, nn.BatchNorm2d):
                module.eval()
        losses = []
        for step in range(150):
            whole = np.concatenate([rng.choice(source_indices, 16), rng.choice(field_indices, 8)])
            selected_photos = rng.integers(0, len(photo_boxes), 8)
            boxed = np.array([rng.choice(photo_boxes[i]) for i in selected_photos])
            features = np.concatenate([cached['train'][whole], cached['boxes'][boxed]])
            target = np.concatenate([labels['train'][whole], labels['boxes'][boxed]])
            scores, _ = model.disease(torch.from_numpy(features.copy()))
            loss = F.cross_entropy(scores, torch.from_numpy(target), label_smoothing=.03)
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite training loss')
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(trainable, 5.)
            optimizer.step()
            losses.append(float(loss.detach()))
        source, field = measure()
        for key, value in original_leaf.items():
            assert torch.equal(value, model.state_dict()[key]), f'Frozen leaf tensor changed: {key}'
        eligible = (source['accuracy'] >= .90 and source['macro_f1'] >= .90
                    and field['accuracy'] >= .5472 and field['macro_f1'] >= .55393)
        key = (field['macro_f1'], field['accuracy'], source['macro_f1'])
        record = {'epoch': epoch, 'source': source, 'field': field, 'eligible': eligible,
                  'loss': float(np.mean(losses)), 'elapsed_seconds': time.monotonic() - started,
                  'leaf_path_tensors_identical': True}
        history.append(record)
        if eligible and (best is None or key > best):
            best = key
            torch.save({'state_dict': model.state_dict(), 'epoch': epoch, 'protocol': protocol,
                        'source': source, 'field': field}, args.output / 'best.pt')
        write(args.output / 'history.json', {'history': history, 'best_key': best})
        print(json.dumps(record), flush=True)
    write(args.output / 'complete.json', {'best_key': best, 'leaf_path_tensors_identical': True,
                                        'elapsed_seconds': time.monotonic() - started})


if __name__ == '__main__':
    main()
