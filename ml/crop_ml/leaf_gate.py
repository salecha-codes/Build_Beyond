"""Train and export a small input leaf gate on frozen MobileNetV3 features.

Fit uses TRAIN/TUNE only. Finalize freezes identity before reading negative TEST
images and writes an isolated three-output model bundle; it never installs it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
import torch
from torch import nn

from .common import read_jsonl
from .export_v3_candidate import PretrainedV3Comparator
from .model import prepare_image

WEIGHTS=Path('/workspace/research/pretrained-v4/mobilenet_v3_large-5c1a4163.pth')
HEAD=Path('/workspace/crop-artifacts/v3_comparator/best_head.pt')
POSITIVE_CACHE=Path('/workspace/crop-artifacts/v4_distill/teacher_train_features.npy')
POSITIVE_ROWS=Path('/workspace/crop-artifacts/full_training/field_extension/cache/mixed_train_rows.jsonl')
SOURCE_TUNE=Path('/workspace/crop-artifacts/v3_comparator/source_tune_features.npy')
FIELD_TUNE=Path('/workspace/research/pretrained-v4/field_tune_v3_features.npz')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):h.update(block)
    return h.hexdigest()


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def sigmoid(values):
    return 1/(1+np.exp(-np.clip(values,-80,80)))


def wilson(correct,total):
    if not total:return None
    z=1.95996398454;p=correct/total;d=1+z*z/total
    center=(p+z*z/(2*total))/d
    half=z*np.sqrt(p*(1-p)/total+z*z/(4*total*total))/d
    return [float(center-half),float(center+half)]


def infer_features(model,rows,path):
    identity=hashlib.sha256(json.dumps([(r['sha256'],r['local_path']) for r in rows]).encode()).hexdigest()
    stamp=path.with_suffix('.json')
    if path.exists():
        assert json.loads(stamp.read_text())['identity']==identity
        result=np.load(path);assert result.shape==(len(rows),960)
        return result
    result=[]
    with torch.inference_mode():
        for start in range(0,len(rows),24):
            batch=[]
            for row in rows[start:start+24]:
                assert sha(row['local_path'])==row['sha256']
                with Image.open(row['local_path']) as image:batch.append(prepare_image(image))
            features=model.features(torch.from_numpy(np.stack(batch))).mean((2,3))
            result.append(features.numpy())
    result=np.concatenate(result).astype(np.float32)
    assert result.shape==(len(rows),960) and np.isfinite(result).all()
    np.save(path,result);write(stamp,{'identity':identity,'rows':len(rows),'sha256':sha(path)})
    return result


def normalized(values,mean,std):
    return np.clip((values-mean)/std,-6,6)


def score(values,checkpoint):
    x=normalized(values,checkpoint['mean'],checkpoint['std'])
    return sigmoid(x@checkpoint['coef']+checkpoint['bias'])


def rates(source,field,negative,threshold):
    def part(values,positive):
        accepted=values>=threshold
        correct=int(accepted.sum()) if positive else int((~accepted).sum())
        return {'samples':len(values),'correct':correct,'rate':correct/len(values),
                'wilson95':wilson(correct,len(values))}
    return {'source_leaf_recall':part(source,True),'field_leaf_recall':part(field,True),
            'nonleaf_rejection':part(negative,False)}


def fit(args):
    out=args.work;out.mkdir(parents=True,exist_ok=True)
    if (out/'fit_started.json').exists():raise FileExistsError('Use a new work directory for a new fit')
    train=read_jsonl(args.negatives/'train.jsonl');tune=read_jsonl(args.negatives/'tune.jsonl')
    assert len(train)>=100 and len(tune)>=25
    assert {r['sha256'] for r in train}.isdisjoint(r['sha256'] for r in tune)
    positive_rows=read_jsonl(POSITIVE_ROWS)
    receipt=json.loads(Path('/workspace/crop-artifacts/v4_distill/teacher_cache_receipt.json').read_text())
    assert sha(POSITIVE_CACHE)==receipt['feature_cache_sha256']
    assert sha(POSITIVE_ROWS)==receipt['train_manifest_sha256'] and sha(WEIGHTS)==receipt['teacher_weights_sha256']
    assert {r['sha256'] for r in positive_rows}.isdisjoint(r['sha256'] for r in train+tune)
    protocol={'schema_version':1,'task':'supported_crop_leaf_input_gate',
      'train_positive_rows':len(positive_rows),'negative_train_rows':len(train),'negative_tune_rows':len(tune),
      'weights_sha256':sha(WEIGHTS),'positive_cache_sha256':sha(POSITIVE_CACHE),
      'positive_manifest_sha256':sha(POSITIVE_ROWS),
      'negative_train_manifest_sha256':sha(args.negatives/'train.jsonl'),
      'negative_tune_manifest_sha256':sha(args.negatives/'tune.jsonl'),
      'negative_test_manifest_sha256':sha(args.negatives/'test.jsonl'),
      'C_grid':[.001,.01,.1,1.,10.], 'field_leaf_recall_floor':.95,'source_leaf_recall_floor':.98,
      'selection':'max nonleaf TUNE rejection subject to positive recall floors; tie field recall then source recall',
      'test_evaluated':False,'threshold_partition':'TUNE only','feature_scaler_partition':'TRAIN only',
      'preprocessing':'same RGB224 letterbox and ImageNet normalization as disease graph'}
    write(out/'fit_started.json',protocol)
    model=PretrainedV3Comparator(WEIGHTS,HEAD).eval()
    negative_train=infer_features(model,train,out/'negative_train.npy')
    negative_tune=infer_features(model,tune,out/'negative_tune.npy')
    positive=np.load(POSITIVE_CACHE)
    source=np.load(SOURCE_TUNE);field=np.load(FIELD_TUNE)['features']
    assert positive.shape==(6956,960) and source.shape==(2228,960) and field.shape==(138,960)
    # Equal domain influence in scaler statistics despite unequal sample counts.
    mean=(positive.mean(0)+negative_train.mean(0))/2
    variance=(np.mean((positive-mean)**2,0)+np.mean((negative_train-mean)**2,0))/2
    std=np.sqrt(variance).clip(.05)
    x=np.concatenate([normalized(positive,mean,std),normalized(negative_train,mean,std)])
    y=np.concatenate([np.ones(len(positive)),np.zeros(len(negative_train))])
    history=[];best=None;chosen=None
    for C in protocol['C_grid']:
        clf=LogisticRegression(C=C,class_weight='balanced',solver='lbfgs',max_iter=1500,random_state=2609)
        clf.fit(x,y)
        cp={'mean':mean,'std':std,'coef':clf.coef_[0],'bias':clf.intercept_[0]}
        sp,fp,np_=score(source,cp),score(field,cp),score(negative_tune,cp)
        field_allowed=int(np.floor((1-protocol['field_leaf_recall_floor'])*len(fp)))
        source_allowed=int(np.floor((1-protocol['source_leaf_recall_floor'])*len(sp)))
        threshold=float(max(1e-7,min(np.sort(fp)[field_allowed],np.sort(sp)[source_allowed])-1e-6))
        report=rates(sp,fp,np_,threshold)
        key=(report['nonleaf_rejection']['rate'],report['field_leaf_recall']['rate'],report['source_leaf_recall']['rate'])
        row={'C':C,'minimum_leaf_probability':threshold,'metrics':report,
             'pooled_tune_auc':float(roc_auc_score(np.r_[np.ones(len(fp)),np.zeros(len(np_))],np.r_[fp,np_]))}
        history.append(row)
        print(json.dumps({'event':'fit_candidate',**row}),flush=True)
        if best is None or key>best:best=key;chosen=(cp,row)
    cp,row=chosen
    np.savez(out/'leaf_head.npz',**cp,threshold=row['minimum_leaf_probability'])
    write(out/'fit_receipt.json',{'protocol':protocol,'selected':row,'history':history,
       'head_sha256':sha(out/'leaf_head.npz'),'fit_complete':True,'negative_test_evaluated':False})
    print(json.dumps({'event':'fit_complete','selected':row}),flush=True)


class LeafGuardedModel(nn.Module):
    def __init__(self,base,checkpoint):
        super().__init__();self.base=base
        for key in ['mean','std','coef']:
            self.register_buffer('leaf_'+key,torch.as_tensor(checkpoint[key],dtype=torch.float32).reshape(1,960))
        self.register_buffer('leaf_bias',torch.as_tensor(checkpoint['bias'],dtype=torch.float32).reshape(1,1))
    def forward(self,image):
        logits,embedding=self.base(image)
        values=((embedding-self.leaf_mean)/self.leaf_std).clamp(-6,6)
        leaf=(values*self.leaf_coef).sum(1,keepdim=True)+self.leaf_bias
        return logits,embedding,leaf


def finalize(args):
    import onnx
    import onnxruntime as ort
    out=args.work;fit_receipt=json.loads((out/'fit_receipt.json').read_text())
    if sha(out/'leaf_head.npz')!=fit_receipt['head_sha256']:raise ValueError('Frozen gate checkpoint changed')
    if sha(WEIGHTS)!=fit_receipt['protocol']['weights_sha256']:raise ValueError('Frozen backbone changed')
    crop_training=json.loads((args.base_bundle/'training_receipt.json').read_text())
    if sha(HEAD)!=crop_training['head_checkpoint_sha256']:raise ValueError('Frozen disease head changed')
    if sha(args.negatives/'test.jsonl')!=fit_receipt['protocol']['negative_test_manifest_sha256']:raise ValueError('Test manifest changed')
    with (out/'test_started.json').open('x') as stream:json.dump({'head_sha256':fit_receipt['head_sha256']},stream)
    cp=dict(np.load(out/'leaf_head.npz'));threshold=float(cp['threshold'])
    base=PretrainedV3Comparator(WEIGHTS,HEAD).eval()
    test=read_jsonl(args.negatives/'test.jsonl')
    test_features=infer_features(base,test,out/'negative_test.npy')
    scores=score(test_features,cp)
    report={'samples':len(test),'rejected':int((scores<threshold).sum()),
      'nonleaf_rejection':float((scores<threshold).mean()),'wilson95':wilson(int((scores<threshold).sum()),len(test)),
      'per_image':[{'sha256':r['sha256'],'class_id':r.get('class_id'),'class_name':r.get('class_name'),
                    'leaf_probability':float(v),'rejected':bool(v<threshold)} for r,v in zip(test,scores)]}
    write(out/'negative_test_report.json',report)
    candidate=args.bundle;candidate.mkdir(parents=True,exist_ok=True)
    # Copy metadata/labels only; source qualification for the new bytes is pending.
    for name in ['labels.json','training_receipt.json']:
        shutil.copy2(args.base_bundle/name,candidate/name)
    model=LeafGuardedModel(base,cp).eval()
    probe=np.random.default_rng(2609).normal(size=(1,3,224,224)).astype(np.float32)
    torch.onnx.export(model,torch.from_numpy(probe),str(candidate/'crop_model.onnx'),
       input_names=['image'],output_names=['logits','embeddings','leaf_logit'],opset_version=17,dynamo=False)
    onnx.checker.check_model(onnx.load(candidate/'crop_model.onnx'),full_check=True)
    options=ort.SessionOptions();options.intra_op_num_threads=args.threads
    session=ort.InferenceSession(str(candidate/'crop_model.onnx'),options,providers=['CPUExecutionProvider'])
    parity=[]
    for values in [np.zeros_like(probe),probe]:
        with torch.inference_mode():reference=model(torch.from_numpy(values))
        actual=session.run(None,{'image':values})
        assert [list(v.shape) for v in actual]==[[1,17],[1,960],[1,1]]
        for got,want in zip(actual,reference):np.testing.assert_allclose(got,want.numpy(),rtol=3e-4,atol=3e-4)
        parity.append(max(float(np.abs(a-b.numpy()).max()) for a,b in zip(actual,reference)))
    model_hash=sha(candidate/'crop_model.onnx');version=f'mnv3-large-leaf-guard-{model_hash[:12]}'
    validation={'schema_version':1,'model_sha256':model_hash,'model_version':version,
      'output_name':'leaf_logit','minimum_leaf_probability':threshold,
      'protocol':fit_receipt['protocol'],'selected_tune_metrics':fit_receipt['selected'],
      'negative_test':report,'head_sha256':fit_receipt['head_sha256'],
      'scope':'prototype input validation; held-out examples are not proof for every nonleaf image',
      'disease_classifier_changed':False,'leaf_gate_test_evaluated_once':True}
    write(candidate/'leaf_validation.json',validation)
    old=json.loads((args.base_bundle/'model_metadata.json').read_text())
    meta={k:v for k,v in old.items() if not k.startswith('source_')}
    meta.update(model_sha256=model_hash,model_version=version,model_size_bytes=(candidate/'crop_model.onnx').stat().st_size,
      diagnosis_validated=False,leaf_gate={'enabled':True,'output_name':'leaf_logit','minimum_leaf_probability':threshold,
       'receipt_file':'leaf_validation.json','receipt_sha256':sha(candidate/'leaf_validation.json')})
    meta['outputs']['leaf_logit']={'name':'leaf_logit','shape':[1,1]}
    write(candidate/'model_metadata.json',meta)
    policy={'schema_version':1,'model_version':version,'model_sha256':model_hash,'validated':False,
      'temperature':1.,'min_confidence':.75,'min_margin':.15,'thresholds_calibrated':False,
      'source_evaluated':False,'source_acceptance_enabled':False,'allow_condition_specific_advice':False,
      'reason':'MODEL_NOT_VALIDATED','validation_status':'new_graph_qualification_pending'}
    write(candidate/'decision_policy.json',policy)
    write(candidate/'export_receipt.json',{'architecture':'MobileNetV3-Large','model_sha256':model_hash,
      'onnx_checker_passed':True,'parity_max_abs_errors':parity,'output_shapes':[[1,17],[1,960],[1,1]],
      'leaf_validation_sha256':sha(candidate/'leaf_validation.json'),'phone_benchmark_executed':False})
    (candidate/'MODEL_CARD.md').write_text('# Leaf-guarded V3 candidate\n\nNew binary leaf input head precedes the unchanged crop classifier. See leaf_validation.json for frozen TRAIN/TUNE protocol and held-out negative results. Crop classifier qualification for this new graph is pending.\n')
    write(out/'finalize_receipt.json',{'bundle':str(candidate),'model_sha256':model_hash,'model_version':version,
      'negative_test_rejection':report['nonleaf_rejection'],'leaf_threshold':threshold})
    print(json.dumps({'event':'finalized', 'model_sha256':model_hash,'bundle':str(candidate),
         'negative_test_rejection':report['nonleaf_rejection'],'tune':fit_receipt['selected']}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['fit','finalize'])
    p.add_argument('--negatives',type=Path,default=Path('/workspace/crop-data/nonleaf'))
    p.add_argument('--work',type=Path,default=Path('/workspace/crop-artifacts/leaf_gate'))
    p.add_argument('--bundle',type=Path,default=Path('/workspace/crop-artifacts/leaf_guard_bundle'))
    p.add_argument('--base-bundle',type=Path,default=Path('/workspace/crop-artifacts/v3_candidate_bundle'))
    p.add_argument('--threads',type=int,default=3);args=p.parse_args()
    torch.set_num_threads(args.threads);torch.set_num_interop_threads(1)
    fit(args) if args.phase=='fit' else finalize(args)


if __name__=='__main__':main()
