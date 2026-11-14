"""Export the frozen ImageNet MobileNetV3 linear-head comparator as one ONNX graph.

This writes an isolated candidate, never replacing the shipped V4 app bundle.
Its output contract is the same 17 global logits plus 960 pooled features.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import time

import numpy as np
import onnx
import onnxruntime as ort
import torch
from torch import nn
from torchvision.models import mobilenet_v3_large

from .common import LABELS_PATH
from .model import prepare_image


def digest(path:Path)->str:
    h=sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):h.update(block)
    return h.hexdigest()


class PretrainedV3Comparator(nn.Module):
    def __init__(self,weights:Path,head_checkpoint:Path):
        super().__init__()
        teacher=mobilenet_v3_large(weights=None)
        teacher.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True),strict=True)
        self.features=teacher.features
        saved=torch.load(head_checkpoint,map_location='cpu',weights_only=True)
        self.linear=nn.Linear(960,17)
        self.linear.load_state_dict(saved['state_dict'],strict=True)
        self.register_buffer('feature_mean',torch.as_tensor(saved['feature_mean'],dtype=torch.float32).reshape(1,960))
        self.register_buffer('feature_std',torch.as_tensor(saved['feature_std'],dtype=torch.float32).reshape(1,960))

    def forward(self,image):
        embedding=self.features(image).mean((2,3))
        normalized=((embedding-self.feature_mean)/self.feature_std).clamp(-6.,6.)
        return self.linear(normalized),embedding


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--weights',type=Path,default=Path('/workspace/research/pretrained-v4/mobilenet_v3_large-5c1a4163.pth'))
    p.add_argument('--head',type=Path,default=Path('/workspace/crop-artifacts/v3_comparator/best_head.pt'))
    p.add_argument('--output',type=Path,default=Path('/workspace/crop-artifacts/v3_candidate_bundle'))
    p.add_argument('--one-tune-image',type=Path)
    args=p.parse_args();torch.set_num_threads(1)
    args.output.mkdir(parents=True,exist_ok=True)
    protocol=json.loads((args.head.parent/'protocol.json').read_text())
    if protocol['teacher_weights_sha256']!=digest(args.weights):raise ValueError('Wrong frozen pretrained weights')
    head=torch.load(args.head,map_location='cpu',weights_only=True)
    if head['teacher_sha256']!=protocol['teacher_weights_sha256']:raise ValueError('Head fit to another teacher')
    model=PretrainedV3Comparator(args.weights,args.head).eval()
    model_file=args.output/'crop_model.onnx'
    probe=np.random.default_rng(2605).normal(size=(1,3,224,224)).astype(np.float32)
    zero=np.zeros_like(probe)
    with torch.inference_mode():reference=model(torch.from_numpy(probe))
    torch.onnx.export(model,torch.from_numpy(probe),str(model_file),input_names=['image'],
                      output_names=['logits','embeddings'],opset_version=17,dynamo=False)
    onnx.checker.check_model(onnx.load(model_file),full_check=True)
    options=ort.SessionOptions();options.intra_op_num_threads=1
    session=ort.InferenceSession(str(model_file),options,providers=['CPUExecutionProvider'])
    actual=session.run(['logits','embeddings'],{'image':probe})
    for got,want in zip(actual,reference):np.testing.assert_allclose(got,want.numpy(),rtol=2e-4,atol=2e-4)
    with torch.inference_mode():zero_reference=model(torch.from_numpy(zero))
    zero_actual=session.run(['logits','embeddings'],{'image':zero})
    for got,want in zip(zero_actual,zero_reference):np.testing.assert_allclose(got,want.numpy(),rtol=2e-4,atol=2e-4)
    real_image_error=None
    if args.one_tune_image:
        from PIL import Image
        with Image.open(args.one_tune_image) as image:prepared=prepare_image(image)[None]
        with torch.inference_mode():expected=model(torch.from_numpy(prepared))
        got=session.run(['logits','embeddings'],{'image':prepared})
        for value,want in zip(got,expected):np.testing.assert_allclose(value,want.numpy(),rtol=2e-4,atol=2e-4)
        real_image_error=max(float(np.abs(value-want.numpy()).max()) for value,want in zip(got,expected))
    model_hash=digest(model_file)
    model_version=f'mnv3-large-imagenet-v2-field-head-{model_hash[:12]}'
    template=json.loads((Path(__file__).resolve().parents[2]/'models/assets/model/model_metadata.json').read_text())
    metadata={key:value for key,value in template.items() if key not in {
        'timm_model','source_evaluated','source_thresholds_calibrated','source_acceptance_qualified',
        'source_acceptance_enabled','source_evaluation_file','source_evaluation_sha256'}}
    metadata.update(model_version=model_version,architecture='MobileNetV3-Large',
        torchvision_model='mobilenet_v3_large',pretrained_weights='IMAGENET1K_V2',
        pretrained_weights_sha256=digest(args.weights),
        model_sha256=model_hash,model_size_bytes=model_file.stat().st_size,
        training_status='trained_prototype',diagnosis_validated=False,
        test_scope='Candidate only: source/field tuning was used for classifier selection; CAL and all final tests pending.')
    policy={'schema_version':1,'model_version':model_version,'model_sha256':model_hash,
        'validated':False,'validation_status':'awaiting_source_evaluation',
        'temperature':1.0,'min_confidence':.75,'min_margin':.15,
        'thresholds_calibrated':False,'source_evaluated':False,
        'source_acceptance_enabled':False,'reason':'MODEL_NOT_VALIDATED',
        'allow_condition_specific_advice':False,
        'note':'Exact-artifact CAL and final-test qualification required before source prototype predictions.'}
    training_receipt={'schema_version':1,'model_name':'torchvision.mobilenet_v3_large.IMAGENET1K_V2',
        'training_mode':'frozen_official_imagenet_backbone_supervised_linear17_head',
        'pretrained_weights_sha256':digest(args.weights),
        'head_checkpoint_sha256':digest(args.head),
        'best_checkpoint_sha256':digest(args.head),
        'head_train_steps':head['step'],'field_loss_weight':head['field_weight'],
        'training_files':6956,'source_training_files':6324,'field_training_files':632,
        'field_training_used':True,
        'field_train_manifest_sha256':digest(Path('/workspace/crop-data/plantdoc-5467f601/partitions/train.jsonl')),
        'source_tune_files':2228,'field_tune_files':138,
        'source_tune_accuracy':.9245960502692998,'source_tune_macro_f1':.9189191308593536,
        'field_tune_accuracy':.5072463768115942,'field_tune_supported_macro_f1':.5239292100447007,
        'head_selection_protocol_sha256':digest(args.head.parent/'protocol.json'),
        'train_validation_only':True,'calibration_evaluated':False,
        'held_out_test_executed':False,'diagnosis_validated':False,'running':False,
        'limitations':'External field images and full source test remain uninspected for this candidate.'}
    for filename,data in [('model_metadata.json',metadata),('decision_policy.json',policy),('training_receipt.json',training_receipt)]:
        (args.output/filename).write_text(json.dumps(data,indent=2)+'\n')
    shutil.copy2(LABELS_PATH,args.output/'labels.json')
    measure=[]
    for _ in range(10):
        start=time.perf_counter();session.run(['logits','embeddings'],{'image':probe});measure.append((time.perf_counter()-start)*1000)
    export_receipt={'architecture':'MobileNetV3-Large','model_sha256':model_hash,
        'checkpoint':str(args.head),'onnx_checker_passed':True,
        'zero_input_max_abs_error':max(float(np.abs(value-want.numpy()).max()) for value,want in zip(zero_actual,zero_reference)),
        'nonzero_input_max_abs_error':max(float(np.abs(value-want.numpy()).max()) for value,want in zip(actual,reference)),
        'output_shapes':[list(x.shape) for x in actual],
        'desktop_cpu_latency_ms':{'iterations':10,'p50':float(np.median(measure)),'p95':float(np.percentile(measure,95))},
        'phone_benchmark_executed':False,'diagnosis_validated':False}
    (args.output/'export_receipt.json').write_text(json.dumps(export_receipt,indent=2)+'\n')
    (args.output/'MODEL_CARD.md').write_text(
        '# Pretrained MobileNetV3-Large candidate\n\n'
        'Frozen official torchvision ImageNet-1K V2 backbone and a TRAIN-only linear 17-class head. '
        'The complete ONNX graph embeds the TRAIN-fitted feature standardization and returns 17 global logits plus 960 features.\n\n'
        'Selected on TUNE: source 92.46% accuracy / 0.9189 macro F1 (2,228 images); '
        'PlantDoc field-like 50.72% accuracy / 0.5239 supported-10 macro F1 (138 images). '
        'These are tuning results, not final-test or real-farm accuracy. CAL and final tests are pending. '
        'Field diagnosis and treatment advice are not validated.\n')
    info={'architecture':'MobileNetV3-Large-ImageNet-V2-frozen-backbone-plus-trained-linear-head',
          'candidate_only':True,'model_sha256':digest(model_file),'bytes':model_file.stat().st_size,
          'teacher_weights_sha256':digest(args.weights),'head_checkpoint_sha256':digest(args.head),
          'train_manifest_sha256':protocol['manifest_sha256']['train'],
          'source_tune_manifest_sha256':protocol['manifest_sha256']['source_tune'],
          'field_tune_manifest_sha256':protocol['manifest_sha256']['field_tune'],
          'head_selection':{'field_weight':head['field_weight'],'step':head['step']},
          'input_shape':[1,3,224,224],'output_shapes':[list(x.shape) for x in actual],
          'random_probe_max_abs_error':max(float(np.abs(value-want.numpy()).max()) for value,want in zip(actual,reference)),
          'zero_probe_max_abs_error':export_receipt['zero_input_max_abs_error'],
          'one_tune_image_max_abs_error':real_image_error,
          'labels_sha256':digest(LABELS_PATH),
          'calibration_or_final_test_executed':False,'field_diagnosis_validated':False}
    (args.output/'candidate_receipt.json').write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps(info,indent=2))

if __name__=='__main__':main()
