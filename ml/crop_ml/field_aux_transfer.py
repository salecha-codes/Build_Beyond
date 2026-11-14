"""Train-only broad field-symptom auxiliary transfer; never relabel as diseases.

The original V3 leaf/object branch remains immutable. An auxiliary 3-way head
is used only for training and is deliberately excluded from deployment models.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from .common import read_jsonl
from .field_tail_finetune import CACHE, HEAD, LEAF, WEIGHTS, PreservedLeafTail, cache_early, evaluate, metrics, sha, write
from .training_improved import cache_images

OLD_EARLY = Path('/workspace/crop-artifacts/field_tail')
DATA = Path('/workspace/research/field_data_next/kandahar_aux')
LABEL_MAPPING = {'Blight': 0, 'Healthy': 1, 'Spot': 2}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train', type=Path, default=DATA / 'train.jsonl')
    parser.add_argument('--valid', type=Path, default=DATA / 'valid.jsonl')
    parser.add_argument('--audit', type=Path, default=DATA / 'receipt.json')
    parser.add_argument('--output', type=Path, default=Path('/workspace/crop-artifacts/field_aux'))
    parser.add_argument('--threads', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.threads <= 3:
        raise ValueError('At most three CPU threads')
    if args.output.exists():
        raise FileExistsError('Fresh output directory required')
    audit = json.loads(args.audit.read_text())
    assert audit['training_ready'] is True, 'Await completed independent data audit'
    assert audit['aux_label_mapping'] == LABEL_MAPPING
    for key in ('train', 'valid'):
        assert audit['manifest_sha256'][key] == sha(getattr(args, key))
    aux = {'aux_train': read_jsonl(args.train), 'aux_valid': read_jsonl(args.valid)}
    paths = {name: CACHE / filename for name, filename in {
        'train': 'mixed_train_rows.jsonl', 'source': 'source_tune_rows.jsonl',
        'field': 'field_tune_rows.jsonl',
    }.items()}
    rows = {key: read_jsonl(path) for key, path in paths.items()}
    all_rows = {**rows, **aux}
    for key, values in aux.items():
        assert values
        assert {r['aux_label_index'] for r in values} == {0, 1, 2}
        assert all(r.get('split', r.get('published_split')) == ('train' if key == 'aux_train' else 'valid') for r in values)
    # Check exact hashes and audited family IDs across every train/selection set.
    for index, (key, values) in enumerate(all_rows.items()):
        for other_key, others in list(all_rows.items())[index + 1:]:
            assert not {r['sha256'] for r in values}.intersection(r['sha256'] for r in others), (key, other_key)
            assert not {r['group_id'] for r in values}.intersection(r['group_id'] for r in others), (key, other_key)
    source_indices = np.array([i for i, r in enumerate(rows['train']) if r['source'] == 'plantvillage'])
    field_indices = np.array([i for i, r in enumerate(rows['train']) if r['source'] != 'plantvillage'])
    assert (len(source_indices), len(field_indices)) == (6324, 632)
    protocol = {
        'schema_version': 1, 'method': 'frozen_leaf_branch_broad_field_auxiliary_transfer',
        'seed': 2614, 'epochs': 3, 'steps_per_epoch': 150,
        'main_batch_source': 8, 'main_batch_field': 8, 'aux_batch_new_field': 16,
        'aux_label_mapping': LABEL_MAPPING, 'aux_label_index_never_mapped_to_main17': True,
        'aux_head_deployed': False, 'aux_loss_weight': .3, 'main_label_smoothing': .03,
        'disease_tail_learning_rate': 1e-5, 'main_head_learning_rate': 5e-5,
        'aux_head_learning_rate': 1e-3, 'batchnorm_running_stats': 'frozen',
        'source_accuracy_floor': .90, 'source_macro_f1_floor': .90,
        'field_accuracy_floor': .5472, 'field_macro_f1_floor': .55393,
        'selection': 'old field TUNE accuracy/F1 plus source TUNE floors only',
        'new_aux_valid': 'reported descriptively; not the main disease selection criterion',
        'weights_sha256': sha(WEIGHTS), 'base_head_sha256': sha(HEAD), 'leaf_head_sha256': sha(LEAF),
        'manifest_sha256': {key: sha(path) for key, path in paths.items()},
        'aux_manifest_sha256': {key: sha(getattr(args, key)) for key in ('train', 'valid')},
        'audit_receipt_sha256': sha(args.audit), 'calibration_or_test_used': False,
        'leaf_path_trainable': False, 'inference_preprocessing_changed': False,
    }
    args.output.mkdir(parents=True)
    write(args.output / 'protocol.json', protocol)
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.manual_seed(2614)
    rng = np.random.default_rng(2614)
    model = PreservedLeafTail().eval()
    auxiliary = nn.Linear(960, 3)
    original_leaf = {key: value.clone() for key, value in model.state_dict().items()
                     if key.startswith(('early.', 'leaf_tail.', 'leaf_'))}
    old_protocol = json.loads((OLD_EARLY / 'protocol.json').read_text())
    cached = {}
    for key in rows:
        assert old_protocol['manifest_sha256'][key] == protocol['manifest_sha256'][key]
        assert old_protocol['weights_sha256'] == protocol['weights_sha256']
        cached[key] = np.load(OLD_EARLY / (key + '_early.npy'), mmap_mode='r')
        assert cached[key].shape == (len(rows[key]), 160, 7, 7)
    print(json.dumps({'event': 'aux_early_cache_start', 'counts': {k: len(v) for k, v in aux.items()}}), flush=True)
    for key, values in aux.items():
        pixels = cache_images(values, args.output / 'cache', key, args.threads)
        cached[key] = cache_early(model, pixels, args.output / (key + '_early.npy'))
    labels = {key: np.array([r['label_index'] for r in values]) for key, values in rows.items()}
    labels.update({key: np.array([r['aux_label_index'] for r in values]) for key, values in aux.items()})
    classes = sorted(set(labels['field']))
    def measure():
        source = evaluate(model, cached['source'], labels['source'], list(range(17)))
        field = evaluate(model, cached['field'], labels['field'], classes)
        model.eval()
        auxiliary.eval()
        predictions = []
        with torch.inference_mode():
            for start in range(0, len(cached['aux_valid']), 64):
                spatial = torch.from_numpy(np.array(cached['aux_valid'][start:start + 64], copy=True))
                _, embedding = model.disease(spatial)
                predictions.append(auxiliary(embedding).numpy())
        aux_metrics = metrics(np.concatenate(predictions), labels['aux_valid'], [0, 1, 2])
        return source, field, aux_metrics
    source, field, aux_metrics = measure()
    assert abs(source['accuracy'] - .9245960502692998) < 1e-9
    assert abs(field['accuracy'] - .5072463768115942) < 1e-9
    print(json.dumps({'event': 'baseline', 'source': source, 'field': field, 'aux_valid': aux_metrics}), flush=True)
    optimizer = torch.optim.AdamW([
        {'params': model.disease_tail.parameters(), 'lr': 1e-5},
        {'params': model.head.parameters(), 'lr': 5e-5},
        {'params': auxiliary.parameters(), 'lr': 1e-3},
    ], weight_decay=1e-4)
    trainable = list(model.disease_tail.parameters()) + list(model.head.parameters()) + list(auxiliary.parameters())
    started, history, best = time.monotonic(), [], None
    for epoch in range(1, 4):
        model.disease_tail.train()
        model.head.train()
        auxiliary.train()
        for module in model.disease_tail.modules():
            if isinstance(module, nn.BatchNorm2d):
                module.eval()
        losses = []
        for step in range(150):
            main_index = np.concatenate([rng.choice(source_indices, 8), rng.choice(field_indices, 8)])
            aux_index = rng.integers(0, len(aux['aux_train']), 16)
            spatial = np.concatenate([cached['train'][main_index], cached['aux_train'][aux_index]])
            scores, embeddings = model.disease(torch.from_numpy(spatial.copy()))
            main_loss = F.cross_entropy(scores[:16], torch.from_numpy(labels['train'][main_index]), label_smoothing=.03)
            aux_loss = F.cross_entropy(auxiliary(embeddings[16:]), torch.from_numpy(labels['aux_train'][aux_index]))
            loss = main_loss + .3 * aux_loss
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite training loss')
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(trainable, 5.)
            optimizer.step()
            losses.append([float(main_loss.detach()), float(aux_loss.detach())])
        source, field, aux_metrics = measure()
        for key, value in original_leaf.items():
            assert torch.equal(value, model.state_dict()[key]), f'Frozen leaf tensor changed: {key}'
        eligible = (source['accuracy'] >= .90 and source['macro_f1'] >= .90
                    and field['accuracy'] >= .5472 and field['macro_f1'] >= .55393)
        key = (field['macro_f1'], field['accuracy'], source['macro_f1'])
        record = {'epoch': epoch, 'source': source, 'field': field, 'aux_valid': aux_metrics,
                  'eligible': eligible, 'mean_main_loss': float(np.mean(losses, axis=0)[0]),
                  'mean_aux_loss': float(np.mean(losses, axis=0)[1]),
                  'elapsed_seconds': time.monotonic() - started, 'leaf_path_tensors_identical': True}
        history.append(record)
        if eligible and (best is None or key > best):
            best = key
            # Aux head intentionally excluded from deployment state_dict.
            torch.save({'state_dict': model.state_dict(), 'epoch': epoch, 'protocol': protocol,
                        'source': source, 'field': field, 'aux_valid': aux_metrics}, args.output / 'best.pt')
        write(args.output / 'history.json', {'history': history, 'best_key': best})
        print(json.dumps(record), flush=True)
    write(args.output / 'complete.json', {'best_key': best, 'leaf_path_tensors_identical': True,
                                        'elapsed_seconds': time.monotonic() - started})


if __name__ == '__main__':
    main()
