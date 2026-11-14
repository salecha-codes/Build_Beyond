"""Train a MobileNetV4 student with a frozen ImageNet V3 *training-only* teacher.

The exported model is still CropModel/MobileNetV4-Conv-Small. This stage reads
mixed TRAIN and frozen TUNE only; it does not import CAL/test manifests or run
inference on those images. Teacher targets are cached from TRAIN before this run.
"""
from __future__ import annotations
import argparse, hashlib, json, math, random, shutil, time
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader, Dataset
from .common import MODEL_NAME, read_jsonl, sha256, write_json
from .model import CropModel
from .training_improved import MixedBatches, CachedImages, evaluate, normalize_batch

class TrainWithTeacher(Dataset):
    def __init__(self, pixels:Path, rows:list[dict], features:Path):
        self.base=CachedImages(pixels,rows)
        self.features_path=str(features)
        self.teacher=None
    def __len__(self):return len(self.base)
    def __getitem__(self,index):
        if self.teacher is None:self.teacher=np.load(self.features_path,mmap_mode='r')
        pixels,label=self.base[index]
        return pixels,label,torch.from_numpy(np.array(self.teacher[index],copy=True))

def run(args):
    if args.epochs<1 or args.epochs>4 or args.threads<1:raise ValueError('Only predeclared 1–4 epoch experiment is allowed')
    torch.set_num_threads(args.threads);torch.set_num_interop_threads(1)
    torch.manual_seed(args.seed);np.random.seed(args.seed);random.seed(args.seed)
    root=args.cache_root
    train_rows=read_jsonl(root/'mixed_train_rows.jsonl')
    source_rows=read_jsonl(root/'source_tune_rows.jsonl')
    field_rows=read_jsonl(root/'field_tune_rows.jsonl')
    n_source=sum(r.get('domain')!='plantdoc_internet_field_like' for r in train_rows)
    assert (len(train_rows),n_source,len(field_rows))==(6956,6324,138)
    assert all(r.get('domain')!='plantdoc_internet_field_like' for r in train_rows[:n_source])
    assert all(r.get('domain')=='plantdoc_internet_field_like' for r in train_rows[n_source:])
    for key in ('sha256','group_id'):
        assert {r[key] for r in train_rows}.isdisjoint(r[key] for r in source_rows+field_rows)
        assert {r[key] for r in source_rows}.isdisjoint(r[key] for r in field_rows)
    teacher_receipt=json.loads(args.teacher_receipt.read_text())
    if teacher_receipt['train_manifest_sha256']!=sha256(root/'mixed_train_rows.jsonl') or teacher_receipt['feature_cache_sha256']!=sha256(args.teacher_features):
        raise ValueError('Frozen teacher features do not match exact TRAIN rows')
    if teacher_receipt['rows']!=len(train_rows) or teacher_receipt['features']!=960:
        raise ValueError('Teacher embedding contract mismatch')
    base_receipt=json.loads((args.base_checkpoint.parent/'training_receipt.json').read_text())
    if base_receipt['running'] or base_receipt['best_checkpoint_sha256']!=sha256(args.base_checkpoint):
        raise ValueError('Base V4 checkpoint is not locked')
    selected_state=torch.load(args.base_checkpoint,map_location='cpu',weights_only=True)
    if selected_state['model_name']!=MODEL_NAME:raise ValueError('Teacher experiment must retain exact V4 backbone')
    model=CropModel().to(memory_format=torch.channels_last)
    model.load_state_dict(selected_state['state_dict'],strict=True)
    field_classes=sorted({r['label_index'] for r in field_rows})
    opts={'batch_size':32,'num_workers':1,'persistent_workers':True}
    source_loader=DataLoader(CachedImages(root/'source_tune_uint8.npy',source_rows),shuffle=False,**opts)
    field_loader=DataLoader(CachedImages(root/'field_tune_uint8.npy',field_rows),shuffle=False,**opts)
    source_base,_=evaluate(model,source_loader)
    field_base,field_outputs=evaluate(model,field_loader)
    field_base['supported_macro_f1']=float(f1_score(field_outputs['labels'],np.asarray(field_outputs['logits']).argmax(1),labels=field_classes,average='macro',zero_division=0))
    reference=json.loads((args.base_checkpoint.parent/'candidate_epoch_8_field_tune.json').read_text())
    if abs(field_base['supported_macro_f1']-reference['macro_f1'])>1e-3:
        raise ValueError('V4 baseline differs from previously frozen TUNE evidence')
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'training_receipt.json').exists():raise FileExistsError('Refusing an unnoticed distillation rerun')
    relational=args.distillation=='relational'
    protocol={'schema_version':1,'architecture':MODEL_NAME,'teacher':'torchvision MobileNetV3 Large ImageNet-1K V2, offline TRAIN-only teacher; runtime remains V4',
        'base_checkpoint_sha256':sha256(args.base_checkpoint),'teacher_cache_receipt_sha256':sha256(args.teacher_receipt),
        'teacher_train_cache_sha256':sha256(args.teacher_features),'mixed_train_manifest_sha256':sha256(root/'mixed_train_rows.jsonl'),
        'source_tune_manifest_sha256':sha256(root/'source_tune_rows.jsonl'),'field_tune_manifest_sha256':sha256(root/'field_tune_rows.jsonl'),
        'calibration_evaluated':False,'source_test_evaluated':False,'external_field_test_evaluated':False,
        'source_train':n_source,'field_train':len(train_rows)-n_source,'field_tune':len(field_rows),'source_tune':len(source_rows),
        'field_macro_class_indices':field_classes,
        'selection_field_supported_macro_f1_min':field_base['supported_macro_f1']+(.05 if relational else .03),
        'selection_field_accuracy_min':field_base['accuracy']+(.01 if relational else 0.),
        'source_tune_accuracy_min':.90 if relational else .85,
        'source_tune_macro_f1_min':.90 if relational else .85,
        'selection_order':['max_field_supported_macro_f1','max_field_accuracy','max_source_macro_f1'],
        'teacher_loss':('in_batch_cosine_relation_KL_temperature_0.1_with_25pct_same_class_neighbors'
                        if relational else '1 - cosine(student_embedding, teacher_embedding)'),
        'distillation':args.distillation,'teacher_weight':args.teacher_weight,
        'classification_loss':'17-class label-smoothed cross entropy','max_epochs':args.epochs,'learning_rate':args.learning_rate,
        'batch_size':32,'field_per_batch':10,'batchnorm_running_statistics':'frozen','seed':args.seed}
    write_json(args.output/'selection_protocol.json',protocol)
    batches=MixedBatches(n_source,len(train_rows)-n_source,32,.3)
    loader=DataLoader(TrainWithTeacher(root/'mixed_train_uint8.npy',train_rows,args.teacher_features),batch_sampler=batches,
        num_workers=1,persistent_workers=True)
    optimizer=torch.optim.AdamW(model.parameters(),lr=args.learning_rate,weight_decay=1e-4,betas=(.9,.99))
    total_steps=args.epochs*len(loader);step=0
    best=None;history=[];started=time.monotonic()
    receipt={'model_name':MODEL_NAME,'training_mode':'supervised_from_scratch_with_offline_teacher_distillation','field_training_used':True,
        'field_train_manifest_sha256':base_receipt['field_train_manifest_sha256'],
        'resume_checkpoint_sha256':sha256(args.base_checkpoint),'teacher_train_cache_sha256':sha256(args.teacher_features),
        'protocol':protocol,'train_validation_only':True,'held_out_test_executed':False,'calibration_evaluated':False,
        'diagnosis_validated':False,'running':True,'history':history,'epochs':0,'selected_mixed_candidate':False}
    write_json(args.output/'training_receipt.json',receipt)
    print(json.dumps({'event':'baseline','source_accuracy':source_base['accuracy'],'source_f1':source_base['macro_f1'],
        'field_accuracy':field_base['accuracy'],'field_f1':field_base['supported_macro_f1']}),flush=True)
    for epoch in range(1,args.epochs+1):
        tick=time.monotonic();model.train()
        for layer in model.modules():
            if isinstance(layer,torch.nn.modules.batchnorm._BatchNorm):layer.eval()
        loss_sum=0.;seen=0
        for pixels,targets,teacher in loader:
            step+=1
            lr=args.learning_rate*(.2+.8*.5*(1+math.cos(math.pi*(step-1)/total_steps)))
            for group in optimizer.param_groups:group['lr']=lr
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast('cpu',dtype=torch.bfloat16):
                logits,student=model(normalize_batch(pixels,True))
            supervised=F.cross_entropy(logits.float(),targets,label_smoothing=.03)
            if relational:
                student_unit=F.normalize(student.float(),dim=1)
                teacher_unit=F.normalize(teacher.float(),dim=1)
                student_relation=student_unit@student_unit.T
                teacher_relation=teacher_unit@teacher_unit.T
                diagonal=torch.eye(len(targets),dtype=torch.bool)
                student_relation=student_relation.masked_fill(diagonal,-1e4)
                teacher_relation=teacher_relation.masked_fill(diagonal,-1e4)
                visual_neighbors=F.softmax(teacher_relation/.1,dim=1)
                same_class=(targets[:,None]==targets[None,:])&~diagonal
                positive=same_class.float()
                positive_count=positive.sum(1,keepdim=True)
                positive=positive/positive_count.clamp_min(1.)
                target_neighbors=(.75*visual_neighbors+.25*positive
                                  if (positive_count>0).all() else
                                  torch.where(positive_count>0,.75*visual_neighbors+.25*positive,visual_neighbors))
                alignment=F.kl_div(F.log_softmax(student_relation/.1,dim=1),target_neighbors,reduction='batchmean')
            else:
                alignment=(1-F.cosine_similarity(student.float(),teacher.float(),dim=1)).mean()
            loss=supervised+args.teacher_weight*alignment
            if not torch.isfinite(loss):raise RuntimeError('Distillation loss is nonfinite')
            loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5.);optimizer.step()
            seen+=len(targets);loss_sum+=float(loss.detach())*len(targets)
        source,_=evaluate(model,source_loader)
        field,out=evaluate(model,field_loader)
        field_f1=float(f1_score(out['labels'],np.asarray(out['logits']).argmax(1),labels=field_classes,average='macro',zero_division=0))
        eligible=(source['accuracy']>=protocol['source_tune_accuracy_min'] and
            source['macro_f1']>=protocol['source_tune_macro_f1_min'] and
            field_f1>=protocol['selection_field_supported_macro_f1_min'] and
            field['accuracy']>=protocol['selection_field_accuracy_min'])
        key=(field_f1,field['accuracy'],source['macro_f1']);selected=eligible and (best is None or key>best)
        record={'epoch':epoch,'source_accuracy':source['accuracy'],'source_macro_f1':source['macro_f1'],
            'field_accuracy':field['accuracy'],'field_supported_macro_f1':field_f1,'loss':loss_sum/seen,'eligible':eligible,
            'selected':selected,'epoch_seconds':time.monotonic()-tick}
        history.append(record)
        if selected:
            best=key
            torch.save({'state_dict':model.state_dict(),'model_name':MODEL_NAME,
                'epoch':int(selected_state.get('epoch',0))+epoch,'field_training_used':True},args.output/'best.pt')
            write_json(args.output/'validation_metrics.json',source)
        receipt.update(history=history,epochs=epoch,running=epoch<args.epochs,selected_mixed_candidate=best is not None)
        write_json(args.output/'training_receipt.json',receipt)
        print(json.dumps({'event':'epoch','data':record}),flush=True)
    receipt.update(running=False,best_checkpoint_sha256=sha256(args.output/'best.pt') if best is not None else None,
        selected_mixed_candidate=best is not None,elapsed_seconds=time.monotonic()-started)
    write_json(args.output/'training_receipt.json',receipt)
    print(json.dumps({'event':'complete','selected':best is not None,'best_field_f1':best[0] if best else field_base['supported_macro_f1']}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-root',type=Path,default=Path('/workspace/crop-artifacts/full_training/field_extension/cache'))
    parser.add_argument('--base-checkpoint',type=Path,default=Path('/workspace/crop-artifacts/full_training/field_extension/best.pt'))
    parser.add_argument('--teacher-features',type=Path,default=Path('/workspace/crop-artifacts/v4_distill/teacher_train_features.npy'))
    parser.add_argument('--teacher-receipt',type=Path,default=Path('/workspace/crop-artifacts/v4_distill/teacher_cache_receipt.json'))
    parser.add_argument('--output',type=Path,default=Path('/workspace/crop-artifacts/v4_distill/student'))
    parser.add_argument('--epochs',type=int,default=4)
    parser.add_argument('--threads',type=int,default=3)
    parser.add_argument('--learning-rate',type=float,default=5e-5)
    parser.add_argument('--teacher-weight',type=float,default=1.)
    parser.add_argument('--distillation',choices=['direct','relational'],default='direct')
    parser.add_argument('--seed',type=int,default=2701)
    run(parser.parse_args())
