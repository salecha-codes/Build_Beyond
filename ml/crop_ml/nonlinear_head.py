"""TRAIN-only residual MLP comparison on frozen V3 features; no CAL/test use."""
from pathlib import Path
import argparse,json,time,hashlib
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from sklearn.metrics import accuracy_score,f1_score
from .common import read_jsonl

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
class ResidualHead(nn.Module):
 def __init__(self,base,hidden,dropout):
  super().__init__();self.base=nn.Linear(960,17);self.base.load_state_dict(base)
  for p in self.base.parameters():p.requires_grad_(False)
  self.residual=nn.Sequential(nn.Linear(960,hidden),nn.GELU(),nn.Dropout(dropout),nn.Linear(hidden,17))
  nn.init.zeros_(self.residual[-1].weight);nn.init.zeros_(self.residual[-1].bias)
 def forward(self,x):return self.base(x)+self.residual(x)
def metrics(x,y,classes):
 pred=x.argmax(1);return {'accuracy':float(accuracy_score(y,pred)),'macro_f1':float(f1_score(y,pred,labels=classes,average='macro',zero_division=0))}
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('/workspace/crop-artifacts/nonlinear_head'));p.add_argument('--threads',type=int,default=2);a=p.parse_args()
 torch.set_num_threads(a.threads);torch.set_num_interop_threads(1);torch.manual_seed(2611)
 a.output.mkdir(parents=True,exist_ok=True)
 if (a.output/'history.json').exists():raise FileExistsError('Use fresh experiment output')
 cache=Path('/workspace/crop-artifacts/full_training/field_extension/cache');basepath=Path('/workspace/crop-artifacts/v3_comparator/best_head.pt');trainfile=Path('/workspace/crop-artifacts/v4_distill/teacher_train_features.npy')
 paths={k:cache/f'{k}_rows.jsonl' for k in ['mixed_train','source_tune','field_tune']};rows={k:read_jsonl(v) for k,v in paths.items()}
 teacher=json.loads(Path('/workspace/crop-artifacts/v4_distill/teacher_cache_receipt.json').read_text());assert teacher['feature_cache_sha256']==digest(trainfile) and teacher['train_manifest_sha256']==digest(paths['mixed_train'])
 configs=[{'hidden':128,'dropout':.4,'decay':.02,'field_weight':1.0,'lr':.002},{'hidden':256,'dropout':.5,'decay':.02,'field_weight':1.0,'lr':.001},{'hidden':128,'dropout':.3,'decay':.01,'field_weight':2.0,'lr':.001}]
 protocol={'schema_version':1,'method':'frozen_V3_features_frozen_linear_plus_residual_MLP','seed':2611,'configs':configs,'steps':[75,150,300],'source_accuracy_floor':.9,'source_macro_f1_floor':.9,'field_accuracy_floor':.5472,'field_supported_macro_f1_floor':.55393,'train_manifest_sha256':digest(paths['mixed_train']),'source_tune_manifest_sha256':digest(paths['source_tune']),'field_tune_manifest_sha256':digest(paths['field_tune']),'base_head_sha256':digest(basepath),'train_features_sha256':digest(trainfile),'calibration_or_test_used':False,'leaf_head_or_backbone_changed':False,'selection_order':['field_macro_f1','field_accuracy','source_macro_f1']}
 save(a.output/'protocol.json',protocol)
 saved=torch.load(basepath,map_location='cpu',weights_only=True);mean=saved['feature_mean'].numpy();std=saved['feature_std'].numpy()
 def normalized(x):return torch.from_numpy(np.ascontiguousarray(np.clip((np.asarray(x)-mean)/std,-6,6),dtype=np.float32))
 x=normalized(np.load(trainfile));s=normalized(np.load('/workspace/crop-artifacts/v3_comparator/source_tune_features.npy'));fieldcache=np.load('/workspace/research/pretrained-v4/field_tune_v3_features.npz');f=normalized(fieldcache['features'])
 y=torch.tensor([r['label_index'] for r in rows['mixed_train']]);sy=np.array([r['label_index'] for r in rows['source_tune']]);fy=np.array([r['label_index'] for r in rows['field_tune']]);assert np.array_equal(fy,fieldcache['targets']);classes=sorted(set(fy))
 assert x.shape==(6956,960) and s.shape==(2228,960) and f.shape==(138,960)
 baseline=ResidualHead(saved['state_dict'],128,.4).eval()
 with torch.no_grad():sm=metrics(baseline(s).numpy(),sy,list(range(17)));fm=metrics(baseline(f).numpy(),fy,classes)
 assert abs(sm['accuracy']-.9245960502692998)<1e-9 and abs(fm['accuracy']-.5072463768115942)<1e-9
 print(json.dumps({'event':'baseline','source':sm,'field':fm}),flush=True)
 history=[];best=None;started=time.monotonic()
 for index,c in enumerate(configs):
  torch.manual_seed(2611+index);head=ResidualHead(saved['state_dict'],c['hidden'],c['dropout']);optimizer=torch.optim.AdamW((p for p in head.parameters() if p.requires_grad),lr=c['lr'],weight_decay=c['decay'])
  for step in range(1,301):
   head.train();logits=head(x);loss=(F.cross_entropy(logits[:6324],y[:6324])+c['field_weight']*F.cross_entropy(logits[6324:],y[6324:]))/(1+c['field_weight']);optimizer.zero_grad();loss.backward();optimizer.step()
   if step not in protocol['steps']:continue
   head.eval()
   with torch.no_grad():sm=metrics(head(s).numpy(),sy,list(range(17)));fm=metrics(head(f).numpy(),fy,classes)
   eligible=sm['accuracy']>=.90 and sm['macro_f1']>=.90 and fm['accuracy']>=.5472 and fm['macro_f1']>=.55393
   key=(fm['macro_f1'],fm['accuracy'],sm['macro_f1']);item={'config':index,'step':step,'source':sm,'field':fm,'eligible':eligible,'elapsed_seconds':time.monotonic()-started};history.append(item);print(json.dumps(item),flush=True)
   if eligible and (best is None or key>best):
    best=key;torch.save({'state_dict':head.state_dict(),'config':c,'step':step,'feature_mean':saved['feature_mean'],'feature_std':saved['feature_std'],'base_head_sha256':digest(basepath),'teacher_sha256':saved['teacher_sha256']},a.output/'best_head.pt')
   save(a.output/'history.json',{'history':history,'best_key':best})
 save(a.output/'complete.json',{'best_key':best,'elapsed_seconds':time.monotonic()-started,'calibration_or_test_used':False});print(json.dumps({'event':'complete','best_key':best}),flush=True)
if __name__=='__main__':main()
