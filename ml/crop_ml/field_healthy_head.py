"""Final bounded healthy-only field transfer on a frozen V3 linear disease head.

Only independently audited Healthy -> maize_healthy is used. Broad Blight/Spot
photos never enter the 17-way loss. All backbone and leaf-check bytes stay fixed.
"""
import argparse
import copy
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from .common import read_jsonl
from .field_tail_finetune import CACHE, HEAD, LEAF, WEIGHTS, PreservedLeafTail, metrics, sha, write

AUX = Path('/workspace/crop-artifacts/field_aux')
AUDIT = Path('/workspace/research/field_data_next/kandahar_aux')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('/workspace/crop-artifacts/field_healthy_head'))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Fresh run directory required')
    receipt = json.loads((args.data / 'receipt.json').read_text())
    assert receipt['training_ready'] is True
    paths = {k: args.data / f'{k}.jsonl' for k in ('train', 'valid')}
    rows = {k: read_jsonl(p) for k, p in paths.items()}
    for key in paths:
        assert receipt['manifest_sha256'][key] == sha(paths[key])
        assert all(r['label_index'] == 3 and r['label_id'] == 'maize_healthy' and r['aux_label'] == 'Healthy' for r in rows[key])
    assert (len(rows['train']), len(rows['valid'])) == (448, 18)
    assert not {r['sha256'] for r in rows['train']}.intersection(r['sha256'] for r in rows['valid'])
    assert not {r['group_id'] for r in rows['train']}.intersection(r['group_id'] for r in rows['valid'])
    aux_protocol = json.loads((AUX / 'protocol.json').read_text())
    old_paths = {key: CACHE / name for key, name in {'train': 'mixed_train_rows.jsonl', 'source': 'source_tune_rows.jsonl', 'field': 'field_tune_rows.jsonl'}.items()}
    old_rows = {key: read_jsonl(path) for key, path in old_paths.items()}
    teacher_file = Path('/workspace/crop-artifacts/v4_distill/teacher_train_features.npy')
    teacher_receipt = json.loads(teacher_file.with_name('teacher_cache_receipt.json').read_text())
    assert teacher_receipt['feature_cache_sha256'] == sha(teacher_file)
    assert teacher_receipt['train_manifest_sha256'] == sha(old_paths['train'])
    assert teacher_receipt['teacher_weights_sha256'] == sha(WEIGHTS)
    protocol = {
        'schema_version': 1, 'method': 'healthy_only_frozen_V3_linear17_head', 'seed': 2615,
        'configs': [{'healthy_loss_weight': weight, 'steps': 100, 'learning_rate': 5e-5} for weight in (.25, .5, 1.)],
        'old_loss': '.5*source_CE + .5*field_CE + 1.0*KL(old_logits || current_logits), temperature2',
        'source_accuracy_floor': .90, 'source_macro_f1_floor': .90,
        'field_accuracy_floor': .5072463768115942, 'field_macro_f1_floor': .5239292100447007,
        'new_healthy_valid_min_additional_correct': 4, 'healthy_selection_includes_original_leaf_gate': True, 'new_valid_count': 18,
        'checkpoint_selection': 'new healthy VALID correct then old field F1 then source F1',
        'source_train_count': 6324, 'old_field_train_count': 632, 'new_healthy_train_count': 448,
        'broad_Blight_Spot_used': False, 'backbone_trainable': False, 'leaf_head_trainable': False,
        'audit_sha256': sha(args.data / 'receipt.json'), 'manifest_sha256': {k: sha(p) for k, p in paths.items()},
        'old_manifest_sha256': {k: sha(p) for k, p in old_paths.items()},
        'base_head_sha256': sha(HEAD), 'weights_sha256': sha(WEIGHTS), 'leaf_head_sha256': sha(LEAF),
        'calibration_or_test_used': False,
    }
    args.output.mkdir(parents=True)
    write(args.output / 'protocol.json', protocol)
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.manual_seed(2615)
    model = PreservedLeafTail().eval()
    # Only use original frozen tail to turn previously audited shared features into
    # complete original embeddings; no auxiliary fine-tuned weights are loaded.
    def extract(key):
        aux_key = 'aux_' + key
        aux_rows_path = AUDIT / f'{key}.jsonl'
        assert sha(aux_rows_path) == aux_protocol['aux_manifest_sha256'][key]
        aux_rows = read_jsonl(aux_rows_path)
        lookup = {r['sha256']: i for i, r in enumerate(aux_rows)}
        indices = []
        for row in rows[key]:
            original = aux_rows[lookup[row['sha256']]]
            assert original['aux_label'] == 'Healthy' and original['aux_label_index'] == 1
            assert original['group_id'] == row['group_id']
            indices.append(lookup[row['sha256']])
        features = np.load(AUX / (aux_key + '_early.npy'), mmap_mode='r')
        assert features.shape == (len(aux_rows), 160, 7, 7)
        result = []
        with torch.inference_mode():
            for start in range(0, len(indices), 64):
                spatial = torch.from_numpy(np.array(features[indices[start:start + 64]], copy=True))
                result.append(model.leaf_tail(spatial).mean((2, 3)).numpy())
        return np.concatenate(result)
    raw = {key: extract(key) for key in paths}
    leaf = dict(np.load(LEAF))
    leaf_values = np.clip((raw['valid'] - leaf['mean']) / leaf['std'], -6, 6)
    leaf_logits = leaf_values @ leaf['coef'] + leaf['bias']
    leaf_probabilities = 1 / (1 + np.exp(-np.clip(leaf_logits, -80, 80)))
    leaf_pass = torch.from_numpy(np.asarray(leaf_probabilities >= float(leaf['threshold'])).reshape(-1))
    np.save(args.output / 'healthy_valid_raw_features.npy', raw['valid'])
    np.save(args.output / 'healthy_train_raw_features.npy', raw['train'])
    saved = torch.load(HEAD, map_location='cpu', weights_only=True)
    def normalize(values):
        return torch.from_numpy(np.ascontiguousarray(np.clip((values - saved['feature_mean'].numpy()) / saved['feature_std'].numpy(), -6, 6), dtype=np.float32))
    x = normalize(np.load(teacher_file))
    source = normalize(np.load('/workspace/crop-artifacts/v3_comparator/source_tune_features.npy'))
    field_cache = np.load('/workspace/research/pretrained-v4/field_tune_v3_features.npz')
    field = normalize(field_cache['features'])
    healthy = normalize(raw['train'])
    valid = normalize(raw['valid'])
    target = torch.tensor([r['label_index'] for r in old_rows['train']])
    sy = np.array([r['label_index'] for r in old_rows['source']])
    fy = np.array([r['label_index'] for r in old_rows['field']])
    assert np.array_equal(fy, field_cache['targets'])
    classes = sorted(set(fy))
    base = nn.Linear(960, 17)
    base.load_state_dict(saved['state_dict'])
    base.eval()
    with torch.no_grad():
        baseline_source = metrics(base(source).numpy(), sy, list(range(17)))
        baseline_field = metrics(base(field).numpy(), fy, classes)
        baseline_valid_raw_correct = int((base(valid).argmax(1) == 3).sum())
        baseline_valid_correct = int(((base(valid).argmax(1) == 3) & leaf_pass).sum())
        teacher_probs = F.softmax(base(x) / 2, dim=1)
    assert abs(baseline_field['accuracy'] - protocol['field_accuracy_floor']) < 1e-9
    assert abs(baseline_source['accuracy'] - .9245960502692998) < 1e-9
    write(args.output / 'baseline.json', {'source': baseline_source, 'field': baseline_field,
          'healthy_valid_correct': baseline_valid_correct, 'healthy_valid_raw_correct': baseline_valid_raw_correct, 'healthy_valid_leaf_pass': int(leaf_pass.sum()), 'healthy_valid_total': 18})
    print(json.dumps({'event': 'baseline', 'source': baseline_source, 'field': baseline_field,
                     'healthy_valid_correct': baseline_valid_correct, 'healthy_valid_raw_correct': baseline_valid_raw_correct, 'healthy_valid_leaf_pass': int(leaf_pass.sum()), 'healthy_valid_total': 18}), flush=True)
    if baseline_valid_correct >= 15:
        write(args.output / 'complete.json', {'best_key': None, 'reason': 'baseline_already_too_high_for_predeclared_gain'})
        return
    history, best, started = [], None, time.monotonic()
    for index, config in enumerate(protocol['configs']):
        head = copy.deepcopy(base)
        optimizer = torch.optim.AdamW(head.parameters(), lr=config['learning_rate'], weight_decay=1e-4)
        for step in range(100):
            prediction = head(x)
            old_ce = .5 * F.cross_entropy(prediction[:6324], target[:6324]) + .5 * F.cross_entropy(prediction[6324:], target[6324:])
            kl = F.kl_div(F.log_softmax(prediction / 2, dim=1), teacher_probs, reduction='batchmean') * 4
            healthy_ce = F.cross_entropy(head(healthy), torch.full((len(healthy),), 3, dtype=torch.long))
            loss = old_ce + kl + config['healthy_loss_weight'] * healthy_ce
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        with torch.no_grad():
            sm = metrics(head(source).numpy(), sy, list(range(17)))
            fm = metrics(head(field).numpy(), fy, classes)
            raw_correct = int((head(valid).argmax(1) == 3).sum())
            correct = int(((head(valid).argmax(1) == 3) & leaf_pass).sum())
        eligible = (sm['accuracy'] >= .90 and sm['macro_f1'] >= .90
                    and fm['accuracy'] >= protocol['field_accuracy_floor'] and fm['macro_f1'] >= protocol['field_macro_f1_floor']
                    and correct >= baseline_valid_correct + 4)
        record = {'config': index, **config, 'source': sm, 'field': fm, 'healthy_valid_correct': correct,
                  'healthy_valid_raw_correct': raw_correct, 'healthy_valid_leaf_pass': int(leaf_pass.sum()), 'healthy_valid_total': 18, 'eligible': eligible, 'elapsed_seconds': time.monotonic() - started}
        history.append(record)
        key = (correct, fm['macro_f1'], sm['macro_f1'])
        if eligible and (best is None or key > best):
            best = key
            torch.save({**saved, 'state_dict': head.state_dict(), 'healthy_only_training': True,
                        'healthy_transfer_protocol_sha256': sha(args.output / 'protocol.json'), 'config': config,
                        'source': sm, 'field': fm, 'healthy_valid_correct': correct, 'step': 100}, args.output / 'best_head.pt')
        write(args.output / 'history.json', {'history': history, 'best_key': best})
        print(json.dumps(record), flush=True)
    # This experiment only ever mutates a separate nn.Linear copy.
    assert sha(WEIGHTS) == protocol['weights_sha256'] and sha(LEAF) == protocol['leaf_head_sha256']
    write(args.output / 'complete.json', {'best_key': best, 'elapsed_seconds': time.monotonic() - started,
                                        'backbone_and_leaf_files_unchanged': True, 'calibration_or_test_used': False})


if __name__ == '__main__':
    main()
