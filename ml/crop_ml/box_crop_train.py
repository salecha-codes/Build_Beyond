"""Bounded V4 field adaptation using only pinned PlantDoc TRAIN leaf boxes.

The known classifier and box photographs are TRAIN data; model selection uses
only source/PlantDoc TUNE. CAL and both final tests are never opened here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import time

import numpy as np
from PIL import Image
import torch
from torch.utils.data import ConcatDataset, DataLoader, Dataset, Sampler
from sklearn.metrics import f1_score

from .common import DEFAULT_DATA, MODEL_NAME, labels, read_jsonl, sha256
from .model import CropModel
from .training_improved import CachedImages, atomic_json, cache_images, evaluate, normalize_batch


class BoxBatches(Sampler[list[int]]):
    """Visit capped source once; draw half the field slots from each photo view."""
    def __init__(self, source_count: int, whole_count: int, box_count: int, batch_size=32):
        self.source_count, self.whole_count, self.box_count = source_count, whole_count, box_count
        self.source_per_batch = 19
        self.whole_per_batch = 6
        self.box_per_batch = batch_size-self.source_per_batch-self.whole_per_batch
    def __len__(self):
        return math.ceil(self.source_count/self.source_per_batch)
    def __iter__(self):
        order=torch.randperm(self.source_count).tolist()
        for start in range(0,self.source_count,self.source_per_batch):
            source=order[start:start+self.source_per_batch]
            if len(source)<self.source_per_batch:
                source+=torch.randint(self.source_count,(self.source_per_batch-len(source),)).tolist()
            whole=(torch.randint(self.whole_count,(self.whole_per_batch,))+self.source_count).tolist()
            boxed=(torch.randint(self.box_count,(self.box_per_batch,))+self.source_count+self.whole_count).tolist()
            batch=source+whole+boxed;random.shuffle(batch);yield batch


def cache_box_views(rows: list[dict], directory: Path, workers: int) -> Path:
    """Exact RGB224 Pillow letterbox of each original VOC box plus 10% context."""
    from concurrent.futures import ThreadPoolExecutor
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/'box_views_uint8.npy'
    receipt=directory/'box_views_uint8.json'
    key=hashlib.sha256(''.join(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n' for x in rows).encode()).hexdigest()
    if path.exists() and receipt.exists():
        old=json.loads(receipt.read_text());array=np.load(path,mmap_mode='r')
        if old.get('rows_sha256')==key and array.shape==(len(rows),224,224,3) and array.dtype==np.uint8:return path
        raise ValueError('Existing box cache belongs to other rows')
    array=np.lib.format.open_memmap(path,mode='w+',dtype=np.uint8,shape=(len(rows),224,224,3))
    def work(pair):
        index,row=pair
        with Image.open(row['local_path']) as photo:
            if photo.getexif().get(274,1) not in (0,1):
                raise ValueError(f'Unresolved EXIF orientation in pinned VOC photo: {row["id"]}')
            photo=photo.convert('RGB')
            if photo.size!=(row['width'],row['height']):
                raise ValueError(f'VOC photo dimensions differ from source pixels: {row["id"]}')
            box=row['box'];dx=(box['xmax']-box['xmin'])*.1;dy=(box['ymax']-box['ymin'])*.1
            crop=photo.crop((max(0,math.floor(box['xmin']-dx)),max(0,math.floor(box['ymin']-dy)),
                             min(photo.width,math.ceil(box['xmax']+dx)),min(photo.height,math.ceil(box['ymax']+dy))))
            scale=min(224/crop.width,224/crop.height)
            size=(max(1,int(crop.width*scale+.5)),max(1,int(crop.height*scale+.5)))
            crop=crop.resize(size,Image.Resampling.BILINEAR)
            canvas=Image.new('RGB',(224,224),(124,116,104))
            canvas.paste(crop,((224-size[0])//2,(224-size[1])//2))
            array[index]=np.asarray(canvas,dtype=np.uint8)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in pool.map(work,enumerate(rows)):pass
    array.flush();atomic_json(receipt,{'rows_sha256':key,'samples':len(rows),'context_fraction':.1,
                                      'shape':[len(rows),224,224,3],'dtype':'uint8'})
    return path


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--selection-lock',type=Path,required=True)
    p.add_argument('--box-manifest',type=Path,required=True)
    p.add_argument('--box-receipt',type=Path,required=True)
    p.add_argument('--field-train',type=Path,required=True)
    p.add_argument('--field-tune',type=Path,required=True)
    p.add_argument('--source-tune',type=Path,required=True)
    p.add_argument('--source-data-root',type=Path,default=DEFAULT_DATA)
    p.add_argument('--existing-cache',type=Path)
    p.add_argument('--epochs',type=int,default=3)
    p.add_argument('--threads',type=int,default=2)
    p.add_argument('--workers',type=int,default=2)
    p.add_argument('--seed',type=int,default=2026)
    p.add_argument('--learning-rate',type=float,default=.0001)
    args=p.parse_args(argv)
    if args.epochs not in range(1,4) or args.threads not in range(1,5) or args.workers<0:
        raise ValueError('Experiment is limited to 3 epochs and 2-4 CPU threads')
    if args.output.exists():raise FileExistsError('Use a new output path; candidate lock must not be rewritten')
    torch.set_num_threads(args.threads);torch.set_num_interop_threads(1)
    torch.manual_seed(args.seed);np.random.seed(args.seed);random.seed(args.seed)
    selected=json.loads(args.selection_lock.read_text())
    if selected['selected_checkpoint_sha256']!=sha256(args.checkpoint):raise ValueError('Wrong frozen warm start')
    base=selected['selected_metrics']
    source_train=[x for x in read_jsonl(args.source_data_root/'splits.jsonl') if x['split']=='train']
    field_train=read_jsonl(args.field_train);field_tune=read_jsonl(args.field_tune);source_tune=read_jsonl(args.source_tune)
    receipt=json.loads(args.box_receipt.read_text());boxes=read_jsonl(args.box_manifest)
    if receipt['manifest_sha256']!=sha256(args.box_manifest) or receipt['source_train_manifest_sha256']!=sha256(args.field_train):
        raise ValueError('VOC boxes and field TRAIN partition disagree')
    source_labels=labels();field_by_sha={x['sha256']:x for x in field_train}
    if len(field_by_sha)!=len(field_train) or not boxes:raise ValueError('Field TRAIN must contain unique photos and actual boxes')
    if any(x['image_sha256'] not in field_by_sha or x['original_partition']!='train' or
           x['label_id']!=field_by_sha[x['image_sha256']]['label_id'] or
           x['group_id']!=field_by_sha[x['image_sha256']]['group_id'] or
           x['label_index']!=field_by_sha[x['image_sha256']]['label_index'] for x in boxes):
        raise ValueError('A box row is not an exact member of field TRAIN')
    if {x['image_sha256'] for x in boxes}&{x['sha256'] for x in field_tune}:
        raise ValueError('Field TUNE photo appears as box TRAIN')
    if {x['group_id'] for x in boxes}&{x['group_id'] for x in field_tune}:
        raise ValueError('Field TUNE group appears as box TRAIN')
    # A few original files carry EXIF rotations or VOC sizes that describe a
    # differently oriented/resized copy. Exclude these TRAIN views before the
    # selection protocol is written; guessing transformed boxes would add noise.
    usable_boxes, skipped_boxes = [], []
    for row in boxes:
        with Image.open(row['local_path']) as photo:
            if photo.getexif().get(274,1) in (0,1) and photo.size == (row['width'],row['height']):
                usable_boxes.append(row)
            else:
                skipped_boxes.append(row['id'])
    boxes = usable_boxes
    rng=random.Random(args.seed)
    capped=[]
    for cls in range(17):
        population=[x for x in source_train if x['label_index']==cls]
        capped+=rng.sample(population,min(400,len(population)))
    flattened=[{**{k:v for k,v in x.items() if k!='boxes'},'box':b,'box_index':i}
               for x in boxes for i,b in enumerate(x['boxes'])]
    field_classes=sorted({x['label_index'] for x in field_tune})
    baseline={'source_accuracy':base['source_tune_accuracy'],'source_macro_f1':base['source_tune_macro_f1'],
              'field_accuracy':base['field_tune_accuracy'],'field_supported_macro_f1':base['field_tune_macro_f1']}
    protocol={'schema_version':1,'description':'V4 3-epoch PlantDoc TRAIN VOC crop-context experiment',
        'warm_start_sha256':sha256(args.checkpoint),'selection_lock_sha256':sha256(args.selection_lock),
        'box_manifest_sha256':sha256(args.box_manifest),'box_receipt_sha256':sha256(args.box_receipt),
        'field_train_sha256':sha256(args.field_train),'field_tune_sha256':sha256(args.field_tune),
        'source_tune_sha256':sha256(args.source_tune),'source_split_sha256':sha256(args.source_data_root/'splits.jsonl'),
        'source_train_cap_per_class':400,'source_train_count':len(capped),
        'field_whole_count':len(field_train),'field_photo_count_with_boxes':len(boxes),'box_crop_count':len(flattened),
        'excluded_box_photo_count_for_EXIF_or_size':len(skipped_boxes),
        'excluded_box_photo_ids_sha256':hashlib.sha256('\n'.join(skipped_boxes).encode()).hexdigest(),
        'max_epochs':args.epochs,'train_batch':{'source_whole':19,'field_whole':6,'field_box_crop':7},
        'box_context_fraction':.1,'field_original_and_crop_balance':'6:7 slots per batch',
        'source_floor_accuracy':.90,'source_floor_macro_f1':.90,
        'field_min_accuracy':baseline['field_accuracy']+.01,
        'field_min_supported_macro_f1':baseline['field_supported_macro_f1']+.05,
        'baseline_tune':baseline,'field_supported_classes':field_classes,
        'selection_order':['field_supported_macro_f1','field_accuracy','source_macro_f1'],
        'calibration_or_final_test_used':False,
        'field_label_limit':'Source dataset candidate labels, not agronomist reviewed'}
    args.output.mkdir(parents=True)
    atomic_json(args.output/'selection_protocol.json',protocol)
    cache=args.output/'cache'
    whole=cache_images(capped+field_train,args.existing_cache or cache,'mixed_train',args.threads)
    source_val=cache_images(source_tune,args.existing_cache or cache,'source_tune',args.threads)
    field_val=cache_images(field_tune,args.existing_cache or cache,'field_tune',args.threads)
    box_cache=cache_box_views(flattened,cache,args.workers or args.threads)
    whole_data=CachedImages(whole,capped+field_train)
    box_data=CachedImages(box_cache,flattened)
    batches=BoxBatches(len(capped),len(field_train),len(flattened))
    train_loader=DataLoader(ConcatDataset([whole_data,box_data]),batch_sampler=batches,
                            num_workers=args.workers,persistent_workers=args.workers>0)
    eval_args={'batch_size':32,'num_workers':args.workers,'persistent_workers':args.workers>0}
    source_loader=DataLoader(CachedImages(source_val,source_tune),shuffle=False,**eval_args)
    field_loader=DataLoader(CachedImages(field_val,field_tune),shuffle=False,**eval_args)
    model=CropModel().to(memory_format=torch.channels_last)
    state=torch.load(args.checkpoint,map_location='cpu',weights_only=True)
    if state.get('model_name')!=MODEL_NAME:raise ValueError('Warm start architecture differs')
    model.load_state_dict(state['state_dict'],strict=True)
    # The acceptance protocol is persisted before touching any TUNE pixels.
    source_start,_=evaluate(model,source_loader)
    field_start,field_predictions=evaluate(model,field_loader)
    baseline_field_f1=float(f1_score(field_predictions['labels'],np.asarray(field_predictions['logits']).argmax(1),
                                     labels=field_classes,average='macro',zero_division=0))
    if abs(source_start['accuracy']-baseline['source_accuracy'])>.000001 or abs(baseline_field_f1-baseline['field_supported_macro_f1'])>.000001:
        raise ValueError('Frozen checkpoint/TUNE baseline is not reproducible')
    optimizer=torch.optim.AdamW(model.parameters(),lr=args.learning_rate,weight_decay=1e-4,betas=(.9,.99))
    loss_fn=torch.nn.CrossEntropyLoss(label_smoothing=.03)
    history=[];best=None;started=time.monotonic()
    training={'model_name':MODEL_NAME,'training_mode':'supervised_from_scratch_box_crop_continuation',
        'field_training_used':True,'field_train_manifest_sha256':protocol['field_train_sha256'],
        'box_manifest_sha256':protocol['box_manifest_sha256'],'base_checkpoint_sha256':protocol['warm_start_sha256'],
        'source_tune_files':len(source_tune),'field_tune_files':len(field_tune),
        'source_train_files':len(capped),'field_original_train_files':len(field_train),
        'box_crops_from_field_train':len(flattened),'calibration_evaluated':False,'final_test_evaluated':False,
        'history':history,'running':True,'selection_protocol_sha256':sha256(args.output/'selection_protocol.json')}
    atomic_json(args.output/'training_receipt.json',training)
    for epoch in range(1,args.epochs+1):
        model.train()
        for layer in model.modules():
            if isinstance(layer,torch.nn.modules.batchnorm._BatchNorm):layer.eval()
        loss_sum=0.;seen=0;tick=time.monotonic()
        for pixels,target in train_loader:
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast('cpu',dtype=torch.bfloat16):logits,_=model(normalize_batch(pixels,True));loss=loss_fn(logits.float(),target)
            if not torch.isfinite(loss):raise ValueError('Nonfinite crop training loss')
            loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5.);optimizer.step()
            loss_sum+=float(loss.detach())*len(target);seen+=len(target)
        source,_=evaluate(model,source_loader)
        field,preds=evaluate(model,field_loader)
        f1=float(f1_score(preds['labels'],np.asarray(preds['logits']).argmax(1),labels=field_classes,average='macro',zero_division=0))
        eligible=source['accuracy']>=.90 and source['macro_f1']>=.90 and field['accuracy']>=protocol['field_min_accuracy'] and f1>=protocol['field_min_supported_macro_f1']
        key=(f1,field['accuracy'],source['macro_f1'])
        improved=eligible and (best is None or key>best)
        record={'epoch':epoch,'source_tune_accuracy':source['accuracy'],'source_tune_macro_f1':source['macro_f1'],
                'field_tune_accuracy':field['accuracy'],'field_tune_supported_macro_f1':f1,
                'train_loss':loss_sum/seen,'train_samples_seen':seen,'eligible':eligible,'selected':improved,
                'epoch_seconds':time.monotonic()-tick}
        history.append(record)
        if improved:
            best=key;tmp=args.output/'best.tmp'
            torch.save({'state_dict':model.state_dict(),'model_name':MODEL_NAME,'epoch':int(state.get('epoch',37))+epoch,
                        'seed':args.seed,'box_crop_training':True},tmp)
            tmp.replace(args.output/'best.pt')
            atomic_json(args.output/'selected_source_tune.json',source)
            atomic_json(args.output/'selected_field_tune.json',{**field,'supported_macro_f1':f1})
        training.update(history=history,epochs=epoch,running=epoch<args.epochs,selected_candidate=best is not None,
                        selected_epoch=next((r['epoch'] for r in reversed(history) if r['selected']),None))
        atomic_json(args.output/'training_receipt.json',training)
        print(json.dumps({'event':'box_crop_epoch',**record}),flush=True)
    training.update(running=False,elapsed_seconds=time.monotonic()-started,
                    best_checkpoint_sha256=sha256(args.output/'best.pt') if best is not None else None)
    atomic_json(args.output/'training_receipt.json',training)
    print(json.dumps({'event':'box_crop_complete','selected_candidate':best is not None,
                      'checkpoint':str(args.output/'best.pt') if best is not None else None,
                      'best_key':best}),flush=True)


if __name__=='__main__':main()
