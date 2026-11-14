"""Fast, isolated V4 classifier-head adaptation on frozen TRAIN features.

This is an experiment, not an app release. Only PlantVillage TRAIN/TUNE and
PlantDoc TRAIN/TUNE are read. It never reads CAL or either final test split.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import time

import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score

from .common import MODEL_NAME, read_jsonl
from .model import CropModel
from .training_improved import normalize_batch


def digest(path: Path) -> str:
    h = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def features(model, images: Path, rows: list[dict], out: Path) -> tuple[np.ndarray, np.ndarray]:
    """Cache exact frozen-backbone pooled features from existing TRAIN/TUNE pixels."""
    if out.exists():
        saved = np.load(out)
        if saved.shape != (len(rows), 960):
            raise ValueError('Cached feature shape changed')
        return saved, np.asarray([r['label_index'] for r in rows], dtype=np.int64)
    pixels = np.load(images, mmap_mode='r')
    if pixels.shape != (len(rows), 224, 224, 3):
        raise ValueError(f'Image cache differs from frozen manifest: {images}')
    output = np.lib.format.open_memmap(out.with_suffix('.building.npy'), mode='w+', dtype=np.float32,
                                       shape=(len(rows), 960))
    model.eval()
    started = time.monotonic()
    with torch.inference_mode():
        for start in range(0, len(rows), 48):
            batch = torch.from_numpy(np.array(pixels[start:start+48], copy=True))
            spatial = model.backbone.forward_features(normalize_batch(batch, False))
            output[start:start+len(batch)] = spatial.mean((2, 3)).numpy()
            if (start//48) % 50 == 0:
                print(json.dumps({'phase':out.stem,'seen':start+len(batch),'total':len(rows),
                                  'elapsed_seconds':round(time.monotonic()-started,1)}), flush=True)
    del output
    out.with_suffix('.building.npy').replace(out)
    return np.load(out, mmap_mode='r'), np.asarray([r['label_index'] for r in rows], dtype=np.int64)


def logits(model, feature_array: np.ndarray) -> np.ndarray:
    out = np.empty((len(feature_array), 17), dtype=np.float32)
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(out), 512):
            feature = torch.from_numpy(np.array(feature_array[start:start+512], copy=True)).unsqueeze(-1).unsqueeze(-1)
            out[start:start+len(feature)] = model.backbone.forward_head(feature).numpy()
    return out


def assess(model, feature_array, targets, field_classes=None):
    predicted = logits(model, feature_array).argmax(1)
    result = {'accuracy':float(accuracy_score(targets, predicted)),
              'macro_f1_all_17':float(f1_score(targets, predicted, labels=list(range(17)),average='macro',zero_division=0))}
    if field_classes is not None:
        result['macro_f1_supported'] = float(f1_score(targets,predicted,labels=field_classes,
                                                     average='macro',zero_division=0))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',type=Path,default=Path('/workspace/crop-artifacts/full_training/field_extension/best.pt'))
    parser.add_argument('--cache-root',type=Path,default=Path('/workspace/crop-artifacts/full_training/field_adaptation/cache'))
    parser.add_argument('--output',type=Path,default=Path('/workspace/crop-artifacts/field_experiments/head_adaptation'))
    parser.add_argument('--threads',type=int,default=3)
    args=parser.parse_args()
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.manual_seed(2602);np.random.seed(2602)
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    root=args.cache_root
    paths={
        'mixed':(root/'mixed_train_rows.jsonl',root/'mixed_train_uint8.npy'),
        'source_tune':(root/'source_tune_rows.jsonl',root/'source_tune_uint8.npy'),
        'field_tune':(root/'field_tune_rows.jsonl',root/'field_tune_uint8.npy')}
    rows={key:read_jsonl(value[0]) for key,value in paths.items()}
    if len(rows['mixed']) != 6956 or len(rows['source_tune']) != 2228 or len(rows['field_tune']) != 138:
        raise ValueError('Unexpected frozen partition sizes')
    source_train=[r for r in rows['mixed'] if r.get('source')!='plantdoc']
    field_train=[r for r in rows['mixed'] if r.get('source')=='plantdoc']
    if len(source_train)!=6324 or len(field_train)!=632 or rows['mixed'][:6324]!=source_train:
        raise ValueError('Mixed TRAIN cache differs from expected split ordering')
    hashes={part:{r['sha256'] for r in values} for part,values in rows.items()}
    if any(hashes[x]&hashes[y] for x,y in [('mixed','source_tune'),('mixed','field_tune'),('source_tune','field_tune')]):
        raise ValueError('TRAIN/TUNE duplicates')
    field_classes=sorted({r['label_index'] for r in rows['field_tune']})
    protocol={'schema_version':1,'experiment':'frozen_v4_backbone_existing_head_adaptation',
        'checkpoint_sha256':digest(args.checkpoint),'parts':{k:digest(v[0]) for k,v in paths.items()},
        'source_train':6324,'field_train':632,'source_tune':2228,'field_tune':138,
        'source_accuracy_floor':.85,'source_macro_f1_floor':.85,
        'field_selection':'maximize_supported_class_macro_f1_then_source_macro_f1',
        'field_supported_classes':field_classes,'seed':2602,
        'sampling':'24_source_and_40_field_per_step_with_replacement',
        'learning_rate':.0003,'optimizer':'AdamW','label_smoothing':.02,
        'evaluation_steps':[0,25,50,100,150,200,300,400],
        'calibration_or_final_test_used':False}
    protocol_path=out/'protocol.json'
    if protocol_path.exists() and json.loads(protocol_path.read_text())!=protocol:
        raise ValueError('Frozen protocol differs')
    if not protocol_path.exists():atomic_json(protocol_path,protocol)
    saved=torch.load(args.checkpoint,map_location='cpu',weights_only=True)
    if saved.get('model_name')!=MODEL_NAME:raise ValueError('Not a pinned V4 checkpoint')
    model=CropModel().eval();model.load_state_dict(saved['state_dict'],strict=True)
    pairs={key:features(model,p[1],rows[key],out/f'{key}_features.npy') for key,p in paths.items()}
    train_x,train_y=pairs['mixed'];source_x,source_y=pairs['source_tune'];field_x,field_y=pairs['field_tune']
    baseline_source=assess(model,source_x,source_y)
    baseline_field=assess(model,field_x,field_y,field_classes)
    if abs(baseline_source['accuracy']-.9528725314183124)>.00001 or abs(baseline_field['accuracy']-.2971014492753623)>.00001:
        raise ValueError('Frozen-head logits do not reproduce full-network baseline')
    print(json.dumps({'event':'baseline','source':baseline_source,'field':baseline_field}),flush=True)
    for parameter in model.parameters():parameter.requires_grad_(False)
    for layer in [model.backbone.conv_head,model.backbone.norm_head,model.backbone.classifier]:
        for parameter in layer.parameters():parameter.requires_grad_(True)
    parameters=[p for p in model.parameters() if p.requires_grad]
    optimizer=torch.optim.AdamW(parameters,lr=protocol['learning_rate'],weight_decay=1e-4)
    loss_fn=torch.nn.CrossEntropyLoss(label_smoothing=.02)
    source_features=torch.from_numpy(np.array(train_x[:6324],copy=True))
    field_features=torch.from_numpy(np.array(train_x[6324:],copy=True))
    source_labels=torch.from_numpy(train_y[:6324]);field_labels=torch.from_numpy(train_y[6324:])
    history=[];best_key=(baseline_field['macro_f1_supported'],baseline_source['macro_f1_all_17']);best_step=0
    for step in range(1,401):
        s=torch.randint(len(source_features),(24,));f=torch.randint(len(field_features),(40,))
        def head(x):return model.backbone.forward_head(x.unsqueeze(-1).unsqueeze(-1))
        source_loss=loss_fn(head(source_features[s]),source_labels[s])
        field_loss=loss_fn(head(field_features[f]),field_labels[f])
        loss=.4*source_loss+.6*field_loss
        optimizer.zero_grad(set_to_none=True);loss.backward();optimizer.step()
        if step not in protocol['evaluation_steps']:continue
        sm=assess(model,source_x,source_y);fm=assess(model,field_x,field_y,field_classes)
        eligible=sm['accuracy']>=.85 and sm['macro_f1_all_17']>=.85
        key=(fm['macro_f1_supported'],sm['macro_f1_all_17'])
        improved=eligible and key>best_key
        item={'step':step,'loss':float(loss.item()),'source':sm,'field':fm,'eligible':eligible,'selected':improved}
        history.append(item);print(json.dumps(item),flush=True)
        if improved:
            best_key=key;best_step=step
            torch.save({'state_dict':model.state_dict(),'model_name':MODEL_NAME,'epoch':saved['epoch'],
                        'head_adaptation_step':step,'base_checkpoint_sha256':protocol['checkpoint_sha256']},out/'best.pt')
        atomic_json(out/'history.json',{'baseline':{'source':baseline_source,'field':baseline_field},
                                     'history':history,'best_step':best_step,'best_key':best_key})
    print(json.dumps({'event':'complete','best_step':best_step,'best_key':best_key}),flush=True)


if __name__=='__main__':main()
