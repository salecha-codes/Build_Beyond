"""Predeclared RBF disease head experiment on frozen V3 TRAIN/TUNE features only."""
from pathlib import Path
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import json,time,hashlib,argparse
import numpy as np
from sklearn.svm import SVC
from sklearn.metrics import accuracy_score,f1_score
from sklearn.metrics.pairwise import euclidean_distances
from threadpoolctl import threadpool_limits
import joblib

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--followup',action='store_true');args=a.parse_args()
 root=Path('/workspace/crop-artifacts');out=root/('kernel_head_followup' if args.followup else 'kernel_head');out.mkdir(exist_ok=True)
 cache=root/'full_training/field_extension/cache'
 paths={k:cache/(n+'_rows.jsonl') for k,n in [('train','mixed_train'),('source','source_tune'),('field','field_tune')]}
 rows={k:[json.loads(v) for v in p.read_text().splitlines()] for k,p in paths.items()}
 train=np.load(root/'v4_distill/teacher_train_features.npy');source=np.load(root/'v3_comparator/source_tune_features.npy');field=np.load('/workspace/research/pretrained-v4/field_tune_v3_features.npz')['features']
 teacher=json.loads((root/'v4_distill/teacher_cache_receipt.json').read_text())
 assert sha(paths['train'])==teacher['train_manifest_sha256']
 assert sha(root/'v4_distill/teacher_train_features.npy')==teacher['feature_cache_sha256']
 assert [len(rows[k]) for k in ['train','source','field']]==[6956,2228,138]
 assert {r['sha256'] for r in rows['train']}.isdisjoint(r['sha256'] for r in rows['field'])
 proto={'schema_version':1,'model':'frozenV3_RBF_SVC17','grid':{'C':[1.,10.],'gamma':[.0005,.002,.01]},'sample_weight_source':1.,'sample_weight_field':10.,'source_floor_accuracy':.90,'source_floor_f1':.90,'field_min_accuracy':.5472,'field_min_supported_f1':.55393,'selection':['field_supported_f1','field_accuracy','source_f1'],'manifests':{k:sha(p) for k,p in paths.items()},'train_features_sha256':sha(root/'v4_distill/teacher_train_features.npy'),'calibration_or_test_used':False,'threads':1}
 configs=[(100.,.0005),(10.,.0001),(10.,.0002)] if args.followup else [(c,g) for g in proto['grid']['gamma'] for c in proto['grid']['C']]
 proto['configs']=[{'C':c,'gamma':g} for c,g in configs];proto['prediction_method']='argmax_continuous_ovr_scores' if args.followup else 'libsvm_vote_predict'
 if (out/'protocol.json').exists():raise FileExistsError('Use fresh experiment directory; protocol already exists')
 (out/'protocol.json').write_text(json.dumps(proto,indent=2)+'\n')
 mean=train.mean(0);std=train.std(0).clip(.05)
 norm=lambda x:np.ascontiguousarray(np.clip((x-mean)/std,-6,6),dtype=np.float64)
 x,sv,fv=map(norm,[train,source,field]);ys={k:np.array([r['label_index'] for r in rows[k]]) for k in rows};classes=sorted(set(ys['field']))
 weights=np.ones(len(x));weights[6324:]=10.
 metric=lambda a,y,cls:{'accuracy':float(accuracy_score(y,a)),'macro_f1':float(f1_score(y,a,labels=cls,average='macro',zero_division=0))}
 started=time.monotonic();history=[];best=None
 with threadpool_limits(limits=1):
  print(json.dumps({'event':'distance_start'}),flush=True)
  dtrain=euclidean_distances(x,x,squared=True);dsource=euclidean_distances(sv,x,squared=True);dfield=euclidean_distances(fv,x,squared=True)
  print(json.dumps({'event':'distances_ready','seconds':time.monotonic()-started}),flush=True)
  for c,gamma in configs:
   kt=np.exp(-gamma*dtrain);ks=np.exp(-gamma*dsource);kf=np.exp(-gamma*dfield)
   tick=time.monotonic();model=SVC(C=c,kernel='precomputed',class_weight=None,cache_size=700,decision_function_shape='ovr',max_iter=100000)
   model.fit(kt,ys['train'],sample_weight=weights)
   sp=model.decision_function(ks).argmax(1) if args.followup else model.predict(ks);fp=model.decision_function(kf).argmax(1) if args.followup else model.predict(kf)
   sm=metric(sp,ys['source'],range(17));fm=metric(fp,ys['field'],classes)
   eligible=sm['accuracy']>=.90 and sm['macro_f1']>=.90 and fm['accuracy']>=.5472 and fm['macro_f1']>=.55393
   item={'C':c,'gamma':gamma,'source':sm,'field':fm,'eligible':eligible,'support_vectors':len(model.support_),'seconds':time.monotonic()-tick}
   history.append(item);print(json.dumps(item),flush=True)
   key=(fm['macro_f1'],fm['accuracy'],sm['macro_f1'])
   if eligible and (best is None or key>best):
    best=key;joblib.dump({'svc':model,'support_features':x[model.support_],'mean':mean,'std':std,'gamma':gamma,'source':sm,'field':fm,'protocol_sha256':sha(out/'protocol.json')},out/'best.joblib')
   (out/'history.json').write_text(json.dumps({'history':history,'best':best,'running':True},indent=2)+'\n')
 (out/'history.json').write_text(json.dumps({'history':history,'best':best,'running':False,'seconds':time.monotonic()-started},indent=2)+'\n')
if __name__=='__main__':main()
