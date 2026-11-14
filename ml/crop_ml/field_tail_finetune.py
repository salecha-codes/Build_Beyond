"""Fine-tune a cloned V3 disease tail; freeze the original leaf-check pathway."""
from pathlib import Path
import argparse,copy,json,time,hashlib
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from torchvision.models import mobilenet_v3_large
from sklearn.metrics import accuracy_score,f1_score
from .common import read_jsonl
from .training_improved import normalize_batch

WEIGHTS=Path('/workspace/research/pretrained-v4/mobilenet_v3_large-5c1a4163.pth')
HEAD=Path('/workspace/crop-artifacts/v3_comparator/best_head.pt')
LEAF=Path('/workspace/crop-artifacts/leaf_gate/leaf_head.npz')
CACHE=Path('/workspace/crop-artifacts/full_training/field_extension/cache')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
 tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n');tmp.replace(p)
class PreservedLeafTail(nn.Module):
 def __init__(self):
  super().__init__();model=mobilenet_v3_large(weights=None);model.load_state_dict(torch.load(WEIGHTS,map_location='cpu',weights_only=True))
  self.early=model.features[:-3];self.leaf_tail=model.features[-3:];self.disease_tail=copy.deepcopy(self.leaf_tail)
  cp=torch.load(HEAD,map_location='cpu',weights_only=True);self.head=nn.Linear(960,17);self.head.load_state_dict(cp['state_dict'])
  self.register_buffer('mean',cp['feature_mean'].reshape(1,960));self.register_buffer('std',cp['feature_std'].reshape(1,960))
  leaf=dict(np.load(LEAF))
  for key in ['mean','std','coef']:self.register_buffer('leaf_'+key,torch.tensor(leaf[key],dtype=torch.float32).reshape(1,960))
  self.register_buffer('leaf_bias',torch.tensor(leaf['bias'],dtype=torch.float32).reshape(1,1))
  for block in [self.early,self.leaf_tail]:
   for p in block.parameters():p.requires_grad_(False)
 def disease(self,spatial):
  embedding=self.disease_tail(spatial).mean((2,3));return self.head(((embedding-self.mean)/self.std).clamp(-6,6)),embedding
 def forward(self,image):
  shared=self.early(image);logits,embedding=self.disease(shared);leaf_embedding=self.leaf_tail(shared).mean((2,3));leaf=((((leaf_embedding-self.leaf_mean)/self.leaf_std).clamp(-6,6))*self.leaf_coef).sum(1,keepdim=True)+self.leaf_bias
  return logits,embedding,leaf

def metrics(a,b,classes):return {'accuracy':float(accuracy_score(b,a.argmax(1))),'macro_f1':float(f1_score(b,a.argmax(1),labels=classes,average='macro',zero_division=0))}
def cache_early(model,pixels,destination):
 if destination.exists():return np.load(destination,mmap_mode='r')
 images=np.load(pixels,mmap_mode='r');data=np.lib.format.open_memmap(destination.with_suffix('.building.npy'),mode='w+',dtype=np.float32,shape=(len(images),160,7,7))
 model.eval()
 with torch.inference_mode():
  for start in range(0,len(images),32):
   x=torch.from_numpy(np.array(images[start:start+32],copy=True));data[start:start+len(x)]=model.early(normalize_batch(x,False)).numpy()
 del data;destination.with_suffix('.building.npy').replace(destination);return np.load(destination,mmap_mode='r')
def evaluate(model,x,y,classes):
 model.eval();out=[]
 with torch.inference_mode():
  for start in range(0,len(x),64):out.append(model.disease(torch.from_numpy(np.array(x[start:start+64],copy=True)))[0].numpy())
 return metrics(np.concatenate(out),y,classes)
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('/workspace/crop-artifacts/field_tail'));p.add_argument('--threads',type=int,default=3);a=p.parse_args()
 torch.set_num_threads(a.threads);torch.set_num_interop_threads(1);torch.manual_seed(2612);rng=np.random.default_rng(2612)
 a.output.mkdir(parents=True,exist_ok=True)
 if (a.output/'history.json').exists():raise FileExistsError('Fresh run directory required')
 paths={'train':CACHE/'mixed_train_rows.jsonl','source':CACHE/'source_tune_rows.jsonl','field':CACHE/'field_tune_rows.jsonl'};rows={k:read_jsonl(v) for k,v in paths.items()};labels={k:np.array([r['label_index'] for r in v]) for k,v in rows.items()};classes=sorted(set(labels['field']))
 protocol={'schema_version':1,'method':'shared_frozen_early_original_frozen_leaf_tail_cloned_trainable_disease_last3','seed':2612,'epochs':3,'steps_per_epoch':150,'batch_source':16,'batch_field':16,'disease_tail_learning_rate':3e-5,'head_learning_rate':1e-4,'batchnorm_running_stats':'frozen','source_accuracy_floor':.90,'source_macro_f1_floor':.90,'field_accuracy_floor':.5472,'field_macro_f1_floor':.55393,'weights_sha256':sha(WEIGHTS),'base_head_sha256':sha(HEAD),'leaf_head_sha256':sha(LEAF),'manifest_sha256':{k:sha(v) for k,v in paths.items()},'calibration_or_test_used':False,'leaf_path_trainable':False}
 write(a.output/'protocol.json',protocol);model=PreservedLeafTail().eval();initial_leaf={k:v.clone() for k,v in model.state_dict().items() if k.startswith(('early.','leaf_tail.','leaf_'))}
 print(json.dumps({'event':'cache_start'}),flush=True)
 cached={k:cache_early(model,CACHE/({'train':'mixed_train','source':'source_tune','field':'field_tune'}[k]+'_uint8.npy'),a.output/(k+'_early.npy')) for k in paths}
 print(json.dumps({'event':'cache_complete','samples':{k:len(v) for k,v in cached.items()}}),flush=True)
 sm=evaluate(model,cached['source'],labels['source'],list(range(17)));fm=evaluate(model,cached['field'],labels['field'],classes)
 print(json.dumps({'event':'baseline','source':sm,'field':fm}),flush=True)
 assert abs(sm['accuracy']-.9245960502692998)<1e-9 and abs(fm['accuracy']-.5072463768115942)<1e-9
 optimizer=torch.optim.AdamW([{'params':model.disease_tail.parameters(),'lr':3e-5},{'params':model.head.parameters(),'lr':1e-4}],weight_decay=1e-4)
 history=[];best=None;started=time.monotonic()
 for epoch in range(1,4):
  model.disease_tail.train();model.head.train()
  for module in model.disease_tail.modules():
   if isinstance(module,nn.BatchNorm2d):module.eval()
  losses=[]
  for step in range(150):
   indices=np.concatenate([rng.integers(0,6324,16),rng.integers(6324,6956,16)]);x=torch.from_numpy(np.array(cached['train'][indices],copy=True));target=torch.from_numpy(labels['train'][indices]);scores,_=model.disease(x);loss=F.cross_entropy(scores,target);optimizer.zero_grad();loss.backward();nn.utils.clip_grad_norm_(list(model.disease_tail.parameters())+list(model.head.parameters()),5.);optimizer.step();losses.append(float(loss))
  sm=evaluate(model,cached['source'],labels['source'],list(range(17)));fm=evaluate(model,cached['field'],labels['field'],classes)
  eligible=sm['accuracy']>=.90 and sm['macro_f1']>=.90 and fm['accuracy']>=.5472 and fm['macro_f1']>=.55393;key=(fm['macro_f1'],fm['accuracy'],sm['macro_f1'])
  for k,v in initial_leaf.items():assert torch.equal(v,model.state_dict()[k]),'Frozen leaf pathway changed'
  rec={'epoch':epoch,'source':sm,'field':fm,'eligible':eligible,'loss':float(np.mean(losses)),'elapsed_seconds':time.monotonic()-started};history.append(rec);print(json.dumps(rec),flush=True)
  if eligible and (best is None or key>best):
   best=key;torch.save({'state_dict':model.state_dict(),'epoch':epoch,'protocol':protocol,'source':sm,'field':fm},a.output/'best.pt')
  write(a.output/'history.json',{'history':history,'best_key':best,'leaf_path_tensors_identical':True})
 write(a.output/'complete.json',{'best_key':best,'elapsed_seconds':time.monotonic()-started,'leaf_path_tensors_identical':True});print(json.dumps({'event':'complete','best_key':best}),flush=True)
if __name__=='__main__':main()
