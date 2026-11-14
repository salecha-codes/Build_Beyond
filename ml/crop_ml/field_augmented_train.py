"""Bounded V4 field adaptation with natural-background training augmentation.

Only the pinned source/PlantDoc TRAIN and TUNE caches are read. This is an
experiment; use a fresh CAL/final test and export before any app deployment.
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
import torch.nn.functional as F
from sklearn.metrics import accuracy_score, f1_score
from torch.utils.data import DataLoader, Sampler

from .common import MODEL_NAME, read_jsonl
from .model import CropModel
from .training_improved import CachedImages, normalize_batch, evaluate


def digest(p:Path)->str:
    h=sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def save_json(path:Path,value):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');tmp.replace(path)

class ShortMixed(Sampler[list[int]]):
    def __init__(self,source=6324,field=632,steps=150):self.source,self.field,self.steps=source,field,steps
    def __len__(self):return self.steps
    def __iter__(self):
        for _ in range(self.steps):
            yield torch.randint(self.source,(16,)).tolist()+(torch.randint(self.field,(16,))+self.source).tolist()

def natural_background(pixels:torch.Tensor)->torch.Tensor:
    """Replace some source gray backdrops with blurred field-TRAIN imagery."""
    source=pixels[:16].permute(0,3,1,2).float()/255.
    field=pixels[16:].permute(0,3,1,2).float()/255.
    corners=torch.cat([source[:,:,:24,:24].flatten(2),source[:,:,:24,-24:].flatten(2),
                       source[:,:,-24:,:24].flatten(2),source[:,:,-24:,-24:].flatten(2)],2)
    base=corners.mean(2,keepdim=True).unsqueeze(-1)
    foreground=(source-base).abs().mean(1,keepdim=True).gt(.13).float()
    foreground=F.avg_pool2d(foreground,7,stride=1,padding=3).clamp(0,1)
    background=F.interpolate(F.interpolate(field,size=(20,20),mode='area'),size=(224,224),mode='bilinear',align_corners=False)
    blended=source*foreground+background*(1-foreground)
    choose=(torch.rand(16)<.55).reshape(16,1,1,1)
    source=torch.where(choose,blended,source)
    return (torch.cat([source,field],0).permute(0,2,3,1).clamp(0,1)*255).round().to(torch.uint8)

def scoped_metrics(logit_rows,labels,field_classes=None):
    truth=np.asarray(labels);pred=np.asarray(logit_rows).argmax(1)
    item={'accuracy':float(accuracy_score(truth,pred)),
          'macro_f1_all_17':float(f1_score(truth,pred,labels=list(range(17)),average='macro',zero_division=0))}
    if field_classes:item['macro_f1_supported_10']=float(f1_score(truth,pred,labels=field_classes,average='macro',zero_division=0))
    return item

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--checkpoint',type=Path,default=Path('/workspace/crop-artifacts/full_training/field_extension/best.pt'))
    a.add_argument('--cache',type=Path,default=Path('/workspace/crop-artifacts/full_training/field_adaptation/cache'))
    a.add_argument('--output',type=Path,default=Path('/workspace/crop-artifacts/field_experiments/background_augmented'))
    a.add_argument('--threads',type=int,default=3)
    args=a.parse_args();torch.set_num_threads(args.threads);torch.set_num_interop_threads(1)
    torch.manual_seed(2603);np.random.seed(2603);random.seed(2603)
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    names={'mixed':'mixed_train','source':'source_tune','field':'field_tune'}
    manifest={key:args.cache/f'{name}_rows.jsonl' for key,name in names.items()}
    pixels={key:args.cache/f'{name}_uint8.npy' for key,name in names.items()}
    rows={key:read_jsonl(path) for key,path in manifest.items()}
    if [len(rows[k]) for k in ['mixed','source','field']] != [6956,2228,138]:raise ValueError('Frozen data counts differ')
    if [r.get('source')=='plantdoc' for r in rows['mixed']]!=[False]*6324+[True]*632:raise ValueError('Unexpected TRAIN cache order')
    hashes={key:{r['sha256'] for r in value} for key,value in rows.items()}
    if hashes['mixed']&(hashes['source']|hashes['field']) or hashes['source']&hashes['field']:raise ValueError('TRAIN/TUNE overlap')
    field_classes=sorted({r['label_index'] for r in rows['field']})
    protocol={'schema_version':1,'experiment':'v4_backbone_natural_background_augmentation',
              'checkpoint_sha256':digest(args.checkpoint),'manifest_sha256':{k:digest(v) for k,v in manifest.items()},
              'source_train':6324,'field_train':632,'source_tune':2228,'field_tune':138,
              'source_min_accuracy':.85,'source_min_macro_f1':.85,
              'field_min_macro_gain_for_release':.05,'field_supported_classes':field_classes,
              'selection_order':['field_supported_class_macro_f1','source_macro_f1'],
              'epochs':4,'steps_per_epoch':150,'batch_source':16,'batch_field':16,
              'source_background_swap_probability':.55,'foreground_threshold_rgb_mean':.13,
              'background_source':'blurred_PlantDoc_TRAIN_only','background_grid':[20,20],
              'optimizer':'AdamW','learning_rate':.00007,'label_smoothing':.02,
              'seed':2603,'calibration_or_final_test_used':False}
    proto_path=out/'protocol.json'
    if proto_path.exists() and json.loads(proto_path.read_text())!=protocol:raise ValueError('Frozen protocol changed')
    if not proto_path.exists():save_json(proto_path,protocol)
    state=torch.load(args.checkpoint,map_location='cpu',weights_only=True)
    if state.get('model_name')!=MODEL_NAME:raise ValueError('Incorrect V4 checkpoint')
    model=CropModel().to(memory_format=torch.channels_last);model.load_state_dict(state['state_dict'],strict=True)
    train=DataLoader(CachedImages(pixels['mixed'],rows['mixed']),batch_sampler=ShortMixed(),num_workers=2,persistent_workers=True)
    source=DataLoader(CachedImages(pixels['source'],rows['source']),batch_size=48,num_workers=2,persistent_workers=True)
    field=DataLoader(CachedImages(pixels['field'],rows['field']),batch_size=48,num_workers=2,persistent_workers=True)
    baseline_source,base_source_scores=evaluate(model,source)
    baseline_field,base_field_scores=evaluate(model,field)
    if abs(baseline_source['accuracy']-.9528725314183124)>.00001 or abs(baseline_field['accuracy']-.2971014492753623)>.00001:
        raise ValueError('Selected reference checkpoint or preprocessing changed')
    baseline={'source':scoped_metrics(base_source_scores['logits'],base_source_scores['labels']),
              'field':scoped_metrics(base_field_scores['logits'],base_field_scores['labels'],field_classes)}
    print(json.dumps({'event':'baseline',**baseline}),flush=True)
    optimizer=torch.optim.AdamW(model.parameters(),lr=protocol['learning_rate'],weight_decay=1e-4)
    loss_fn=torch.nn.CrossEntropyLoss(label_smoothing=.02)
    best=(baseline['field']['macro_f1_supported_10'],baseline['source']['macro_f1_all_17'])
    history=[];start=time.monotonic()
    for epoch in range(1,5):
        model.train()
        # Keep source-domain BN behavior from the selected model; mixed batches
        # otherwise overwrite it with a 50/50 domain that is neither runtime.
        for layer in model.modules():
            if isinstance(layer,torch.nn.modules.batchnorm._BatchNorm):layer.eval()
        total=0.
        for sample,labels in train:
            sample=natural_background(sample)
            tensor=normalize_batch(sample,True)
            scores,_=model(tensor)
            loss=.5*loss_fn(scores[:16],labels[:16])+.5*loss_fn(scores[16:],labels[16:])
            optimizer.zero_grad(set_to_none=True);loss.backward();optimizer.step()
            total+=float(loss.item())
        source_metrics,source_scores=evaluate(model,source)
        field_metrics,field_scores=evaluate(model,field)
        sm=scoped_metrics(source_scores['logits'],source_scores['labels'])
        fm=scoped_metrics(field_scores['logits'],field_scores['labels'],field_classes)
        eligible=sm['accuracy']>=.85 and sm['macro_f1_all_17']>=.85
        key=(fm['macro_f1_supported_10'],sm['macro_f1_all_17'])
        selected=eligible and key>best
        rec={'epoch':epoch,'loss':total/len(train),'source':sm,'field':fm,
             'eligible':eligible,'selected':selected,'elapsed_seconds':time.monotonic()-start}
        history.append(rec)
        print(json.dumps({'event':'epoch_complete',**rec}),flush=True)
        if selected:
            best=key
            torch.save({'state_dict':model.state_dict(),'model_name':MODEL_NAME,'epoch':state['epoch']+epoch,
                        'base_checkpoint_sha256':protocol['checkpoint_sha256']},out/'best.pt')
        save_json(out/'history.json',{'baseline':baseline,'history':history,'best_key':best})
    print(json.dumps({'event':'complete','best_key':best,'release_gain':best[0]-baseline['field']['macro_f1_supported_10']}),flush=True)

if __name__=='__main__':main()
