"""Export selected RBF17 head with frozen V3 backbone and unchanged leaf guard."""
from pathlib import Path
import json,shutil,hashlib,time,argparse
import joblib,numpy as np,torch,onnx,onnxruntime as ort
from torch import nn
from .export_v3_candidate import PretrainedV3Comparator
from .leaf_gate import LeafGuardedModel,WEIGHTS,HEAD,sha,write
from .model import prepare_image

class KernelComparator(nn.Module):
 def __init__(self,cp):
  super().__init__();self.features=PretrainedV3Comparator(WEIGHTS,HEAD).features
  svc=cp['svc'];sv=cp['support_features'];n=len(sv);classes=len(svc.classes_)
  coef=np.zeros((n,classes*(classes-1)//2));vi=np.zeros((coef.shape[1],classes));vj=vi.copy();starts=np.r_[0,np.cumsum(svc.n_support_)]
  k=0
  for i in range(classes):
   for j in range(i+1,classes):
    coef[starts[i]:starts[i+1],k]=svc.dual_coef_[j-1,starts[i]:starts[i+1]]
    coef[starts[j]:starts[j+1],k]=svc.dual_coef_[i,starts[j]:starts[j+1]]
    vi[k,i]=1;vj[k,j]=1;k+=1
  for name,value in [('mean',cp['mean'].reshape(1,-1)),('std',cp['std'].reshape(1,-1)),('sv',sv.T),('sv_norm',(sv*sv).sum(1).reshape(1,-1)),('coef',coef),('intercept',svc.intercept_),('vote_i',vi),('vote_j',vj)]:self.register_buffer(name,torch.as_tensor(value,dtype=torch.float32))
  self.gamma=float(cp['gamma']);self.softvote_tau=cp.get('softvote_tau')
 def head(self,embedding):
  x=((embedding-self.mean)/self.std).clamp(-6,6)
  distance=(x*x).sum(1,keepdim=True)+self.sv_norm-2*(x@self.sv)
  pair=torch.exp(-self.gamma*distance.clamp_min(0))@self.coef+self.intercept
  choice=(pair>=0).float() if self.softvote_tau is None else torch.sigmoid(pair/self.softvote_tau);votes=choice@self.vote_i+(1-choice)@self.vote_j
  conf=pair@(self.vote_i-self.vote_j)
  return votes+conf/(3*(conf.abs()+1))
 def forward(self,image):
  embedding=self.features(image).mean((2,3));return self.head(embedding),embedding

def main():
 torch.set_num_threads(1);torch.set_num_interop_threads(1)
 a=argparse.ArgumentParser();a.add_argument('--checkpoint',type=Path,default=Path('/workspace/crop-artifacts/kernel_head_followup/best.joblib'));a.add_argument('--output',type=Path,default=Path('/workspace/crop-artifacts/kernel_candidate_bundle'));args=a.parse_args()
 work=args.checkpoint.parent;out=args.output;out.mkdir(exist_ok=True)
 cp=joblib.load(args.checkpoint);base=KernelComparator(cp).eval()
 # Exact manual pairwise/OVR implementation check on actual reserved TUNE features.
 field=np.load('/workspace/research/pretrained-v4/field_tune_v3_features.npz')['features'];train=np.load('/workspace/crop-artifacts/v4_distill/teacher_train_features.npy')
 normalize=lambda x:np.ascontiguousarray(np.clip((x-cp['mean'])/cp['std'],-6,6),dtype=np.float64)
 x=normalize(field);tr=normalize(train);distance=np.maximum((x*x).sum(1,keepdims=True)+(tr*tr).sum(1)[None]-2*x@tr.T,0)
 reference=cp['svc'].decision_function(np.exp(-cp['gamma']*distance))
 with torch.inference_mode():manual=base.head(torch.from_numpy(field)).numpy()
 if cp.get('softvote_tau') is None:assert np.array_equal(manual.argmax(1),reference.argmax(1)), 'Float32 RBF changed selected TUNE classifications'
 error=float(np.abs(reference-manual).max());print('Head parity',error,flush=True)
 gate=dict(np.load('/workspace/crop-artifacts/leaf_gate/leaf_head.npz'));model=LeafGuardedModel(base,gate).eval()
 probe=np.random.default_rng(2703).normal(size=(1,3,224,224)).astype(np.float32)
 modelpath=out/'crop_model.onnx'
 torch.onnx.export(model,torch.from_numpy(probe),str(modelpath),input_names=['image'],output_names=['logits','embeddings','leaf_logit'],opset_version=17,dynamo=False)
 onnx.checker.check_model(onnx.load(modelpath),full_check=True)
 opts=ort.SessionOptions();opts.intra_op_num_threads=1;opts.inter_op_num_threads=1
 session=ort.InferenceSession(str(modelpath),opts,providers=['CPUExecutionProvider']);errors={}
 for name,value in [('random',probe),('zero',np.zeros_like(probe))]:
  with torch.inference_mode():want=model(torch.from_numpy(value))
  got=session.run(None,{'image':value});errors[name]=[float(np.max(np.abs(v-w.numpy()))) for v,w in zip(got,want)]
  for v,w in zip(got,want):np.testing.assert_allclose(v,w.numpy(),rtol=5e-4,atol=5e-4)
 from PIL import Image
 with Image.open('/workspace/Build_Beyond/dist/Sample-Leaf-QA.jpg') as im:prepared=prepare_image(im)[None]
 with torch.inference_mode():want=model(torch.from_numpy(prepared))
 got=session.run(None,{'image':prepared})
 assert got[0].argmax()==want[0].numpy().argmax()
 for v,w in zip(got,want):np.testing.assert_allclose(v,w.numpy(),rtol=5e-4,atol=5e-4)
 errors['real_leaf']=[float(np.max(np.abs(v-w.numpy()))) for v,w in zip(got,want)]
 old=Path('/workspace/Build_Beyond/models/assets/model');metadata=json.loads((old/'model_metadata.json').read_text());version=('mnv3-large-soft-rbf-leaf-' if cp.get('softvote_tau') else 'mnv3-large-rbf-leaf-')+sha(modelpath)[:12]
 for k in list(metadata):
  if k.startswith('source_'):metadata.pop(k)
 metadata.update(model_version=version,model_sha256=sha(modelpath),model_size_bytes=modelpath.stat().st_size,training_status='trained_prototype',test_scope='TRAIN/TUNE selected RBF candidate; new exact-artifact calibration/final comparison pending')
 leaf=json.loads((old/'leaf_validation.json').read_text());leaf.update(model_version=version,model_sha256=sha(modelpath));leaf['backbone_and_leaf_head_unchanged_from']=json.loads((old/'model_metadata.json').read_text())['model_sha256'];write(out/'leaf_validation.json',leaf)
 metadata['leaf_gate']['receipt_sha256']=sha(out/'leaf_validation.json')
 write(out/'model_metadata.json',metadata)
 policy={'schema_version':1,'model_version':version,'model_sha256':metadata['model_sha256'],'validated':False,'temperature':1.,'min_confidence':.75,'min_margin':.15,'thresholds_calibrated':False,'source_evaluated':False,'source_acceptance_enabled':False,'allow_condition_specific_advice':False,'reason':'MODEL_NOT_VALIDATED'};write(out/'decision_policy.json',policy)
 shutil.copy2(old/'labels.json',out/'labels.json')
 training=json.loads(Path('/workspace/crop-artifacts/v3_candidate_bundle/training_receipt.json').read_text());training.update(training_mode='frozen_V3_pretrained_RBF_SVC17_manual_OVR_head',head_checkpoint_sha256=sha(work/'best.joblib'),best_checkpoint_sha256=sha(work/'best.joblib'),field_tune_accuracy=cp['field']['accuracy'],field_tune_supported_macro_f1=cp['field']['macro_f1'],source_tune_accuracy=cp['source']['accuracy'],source_tune_macro_f1=cp['source']['macro_f1'],calibration_evaluated=False,held_out_test_executed=False,head_selection_protocol_sha256=sha(work/'protocol.json'),support_vectors=len(cp['support_features']),rbf_gamma=cp['gamma']);write(out/'training_receipt.json',training)
 times=[]
 for _ in range(12):
  tick=time.perf_counter();session.run(None,{'image':prepared});times.append((time.perf_counter()-tick)*1000)
 receipt={'model_sha256':sha(modelpath),'architecture':'MobileNetV3-Large','manual_ovr_field_tune_max_abs_error':error,'onnx_checker_passed':True,'parity_max_abs_errors':errors,'output_shapes':[list(v.shape) for v in got],'model_bytes':modelpath.stat().st_size,'support_vectors':len(cp['support_features']),'desktop_cpu_latency_ms_p50':float(np.median(times)),'desktop_cpu_latency_ms_p95':float(np.percentile(times,95)),'phone_benchmark_executed':False,'field_tune':cp['field'],'source_tune':cp['source'],'leaf_head_checkpoint_sha256':sha('/workspace/crop-artifacts/leaf_gate/leaf_head.npz'),'candidate_only':True};write(out/'export_receipt.json',receipt)
 (out/'MODEL_CARD.md').write_text('# Frozen MobileNetV3 RBF disease-head candidate\n\nTRAIN/TUNE only; exact-artifact CAL/source/field evaluation pending. Original V3 backbone and leaf rejection head are unchanged. Manual RBF/SVC pairwise-to-OVR continuous scores run in standard ONNX tensor operators.\n')
 print(json.dumps(receipt,indent=2),flush=True)
if __name__=='__main__':main()
