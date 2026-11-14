"""Frozen official ImageNet MobileNetV3 feature comparator, TRAIN/TUNE only.

This does not modify the V4 app. It asks whether a pretrained backbone is a
promising direction before any architecture switch or release evaluation.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import time

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import accuracy_score, f1_score
from torchvision.models import mobilenet_v3_large

from .common import read_jsonl
from .training_improved import normalize_batch


def digest(path: Path) -> str:
    h=sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):h.update(block)
    return h.hexdigest()

def save_json(path:Path,value):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');tmp.replace(path)

def tune_features(model,images:Path,rows:list[dict],out:Path)->np.ndarray:
    if out.exists():
        arr=np.load(out,mmap_mode='r')
        if arr.shape!=(len(rows),960):raise ValueError('TUNE features shape changed')
        return arr
    pixels=np.load(images,mmap_mode='r')
    if pixels.shape!=(len(rows),224,224,3):raise ValueError('TUNE image cache mismatch')
    values=np.lib.format.open_memmap(out.with_suffix('.building.npy'),mode='w+',dtype=np.float32,shape=(len(rows),960))
    model.eval()
    with torch.inference_mode():
        for start in range(0,len(rows),32):
            batch=torch.from_numpy(np.array(pixels[start:start+32],copy=True))
            values[start:start+len(batch)]=model.features(normalize_batch(batch,False)).mean((2,3)).numpy()
    del values
    out.with_suffix('.building.npy').replace(out)
    return np.load(out,mmap_mode='r')

def metrics(logits,targets,field_classes=None):
    predicted=np.asarray(logits).argmax(1)
    value={'accuracy':float(accuracy_score(targets,predicted)),
           'macro_f1_all_17':float(f1_score(targets,predicted,labels=list(range(17)),average='macro',zero_division=0))}
    if field_classes is not None:
        value['macro_f1_supported_10']=float(f1_score(targets,predicted,labels=field_classes,average='macro',zero_division=0))
    return value

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--weights',type=Path,default=Path('/workspace/research/pretrained-v4/mobilenet_v3_large-5c1a4163.pth'))
    a.add_argument('--cache',type=Path,default=Path('/workspace/crop-artifacts/full_training/field_extension/cache'))
    a.add_argument('--teacher-train',type=Path,default=Path('/workspace/crop-artifacts/v4_distill/teacher_train_features.npy'))
    a.add_argument('--teacher-receipt',type=Path,default=Path('/workspace/crop-artifacts/v4_distill/teacher_cache_receipt.json'))
    a.add_argument('--output',type=Path,default=Path('/workspace/crop-artifacts/v3_comparator'))
    args=a.parse_args();torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(2605)
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    files={'train':args.cache/'mixed_train_rows.jsonl',
           'source_tune':args.cache/'source_tune_rows.jsonl',
           'field_tune':args.cache/'field_tune_rows.jsonl'}
    rows={key:read_jsonl(path) for key,path in files.items()}
    if [len(rows[k]) for k in ['train','source_tune','field_tune']]!=[6956,2228,138]:raise ValueError('Frozen split counts changed')
    hashes={key:{row['sha256'] for row in value} for key,value in rows.items()}
    if any(hashes[x]&hashes[y] for x,y in [('train','source_tune'),('train','field_tune'),('source_tune','field_tune')]):
        raise ValueError('TRAIN/TUNE leakage')
    teacher=json.loads(args.teacher_receipt.read_text())
    if teacher['teacher_weights_sha256']!=digest(args.weights) or teacher['feature_cache_sha256']!=digest(args.teacher_train):
        raise ValueError('Teacher weights or TRAIN features changed')
    if teacher['train_manifest_sha256']!=digest(files['train']):raise ValueError('Teacher TRAIN order differs')
    field_classes=sorted({row['label_index'] for row in rows['field_tune']})
    protocol={'schema_version':1,'experiment':'official_pretrained_mobilenet_v3_large_frozen_linear_head',
              'teacher_weights_sha256':teacher['teacher_weights_sha256'],
              'teacher_train_cache_sha256':teacher['feature_cache_sha256'],
              'manifest_sha256':{key:digest(value) for key,value in files.items()},
              'source_train':6324,'field_train':632,'source_tune':2228,'field_tune':138,
              'field_supported_classes':field_classes,'global_logits':17,
              'preprocessing':'RGB224_letterbox_then_ImageNet_normalization_same_as_V4',
              'train_feature_standardization':'TRAIN_only_mean_std_clip_-6_6',
              'field_loss_weight_grid':[1,3,6,12],
              'optimizer':'Adam_full_batch','learning_rate':.05,'weight_decay':.001,
              'training_steps':[40,100],
              'source_tune_accuracy_floor':.90,'source_tune_macro_f1_floor':.90,
              'field_accuracy_min':.2971014492753623,
              'field_supported_macro_f1_min':.26945184773274017,
              'selection_order':['max_field_supported_macro_f1','max_field_accuracy','max_source_macro_f1'],
              'seed':2605,'source_calibration_or_any_test_used':False,
              'deployment_allowed':False}
    proto=out/'protocol.json'
    if proto.exists() and json.loads(proto.read_text())!=protocol:raise ValueError('Protocol changed')
    if not proto.exists():save_json(proto,protocol)
    model=mobilenet_v3_large(weights=None).eval()
    model.load_state_dict(torch.load(args.weights,map_location='cpu',weights_only=True),strict=True)
    train_x=np.load(args.teacher_train,mmap_mode='r')
    if train_x.shape!=(6956,960):raise ValueError('Teacher TRAIN features shape')
    source_x=tune_features(model,args.cache/'source_tune_uint8.npy',rows['source_tune'],out/'source_tune_features.npy')
    # The other agent already evaluated field TUNE frozen features. Reuse only
    # after verifying the ordered labels against this canonical TUNE manifest.
    field_cache=np.load('/workspace/research/pretrained-v4/field_tune_v3_features.npz')
    field_x=field_cache['features'];field_targets=field_cache['targets']
    if field_x.shape!=(138,960) or not np.array_equal(field_targets,[r['label_index'] for r in rows['field_tune']]):
        raise ValueError('Teacher field TUNE feature cache order changed')
    train_targets=np.asarray([r['label_index'] for r in rows['train']],dtype=np.int64)
    source_targets=np.asarray([r['label_index'] for r in rows['source_tune']],dtype=np.int64)
    mean=np.asarray(train_x).mean(0);std=np.asarray(train_x).std(0).clip(.05)
    def normalize(data):return torch.from_numpy(np.ascontiguousarray(np.clip((np.asarray(data)-mean)/std,-6,6),dtype=np.float32))
    features=normalize(train_x);source=normalize(source_x);field=normalize(field_x)
    truth=torch.from_numpy(train_targets)
    source_mask=torch.arange(len(truth))<6324
    field_mask=~source_mask
    source_count=source_mask.sum().item();field_count=field_mask.sum().item()
    source_target=torch.from_numpy(source_targets)
    field_target=torch.from_numpy(field_targets)
    history=[];best=None;started=time.monotonic()
    for field_weight in protocol['field_loss_weight_grid']:
        head=torch.nn.Linear(960,17)
        torch.nn.init.zeros_(head.weight);torch.nn.init.zeros_(head.bias)
        optimizer=torch.optim.Adam(head.parameters(),lr=protocol['learning_rate'],weight_decay=protocol['weight_decay'])
        for step in range(1,101):
            scores=head(features)
            source_loss=F.cross_entropy(scores[source_mask],truth[source_mask])
            field_loss=F.cross_entropy(scores[field_mask],truth[field_mask])
            loss=(source_loss+field_weight*field_loss)/(1+field_weight)
            optimizer.zero_grad(set_to_none=True);loss.backward();optimizer.step()
            if step not in protocol['training_steps']:continue
            with torch.no_grad():
                sm=metrics(head(source).numpy(),source_targets)
                fm=metrics(head(field).numpy(),field_targets,field_classes)
            eligible=sm['accuracy']>=.90 and sm['macro_f1_all_17']>=.90 and \
                     fm['accuracy']>.2971014492753623 and fm['macro_f1_supported_10']>.26945184773274017
            key=(fm['macro_f1_supported_10'],fm['accuracy'],sm['macro_f1_all_17'])
            item={'field_weight':field_weight,'step':step,'source':sm,'field':fm,'eligible':eligible,
                  'elapsed_seconds':time.monotonic()-started}
            history.append(item);print(json.dumps(item),flush=True)
            if eligible and (best is None or key>best):
                best=key
                torch.save({'state_dict':head.state_dict(),
                            'feature_mean':torch.from_numpy(mean.copy()),
                            'feature_std':torch.from_numpy(std.copy()),
                            'teacher_sha256':teacher['teacher_weights_sha256'],'field_weight':field_weight,'step':step},out/'best_head.pt')
            save_json(out/'history.json',{'history':history,'best_key':best})
    print(json.dumps({'event':'complete','best_key':best,'evaluations':len(history)}),flush=True)

if __name__=='__main__':main()
