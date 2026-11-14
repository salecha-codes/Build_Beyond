"""Export an isolated healthy-only head candidate with unchanged V3 leaf guard."""
import argparse
import copy
import json
from pathlib import Path
import shutil

import numpy as np
import onnx
import onnxruntime as ort
from PIL import Image
import torch

from .common import read_jsonl
from .export_v3_candidate import PretrainedV3Comparator
from .field_tail_finetune import WEIGHTS, HEAD, LEAF, sha, write
from .leaf_gate import LeafGuardedModel
from .model import prepare_image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=Path('/workspace/crop-artifacts/field_healthy_head_e2e'))
    parser.add_argument('--output', type=Path, default=Path('/workspace/crop-artifacts/healthy_candidate_bundle'))
    args = parser.parse_args()
    assert not args.output.exists()
    complete = json.loads((args.work / 'complete.json').read_text())
    assert complete['best_key'] is not None
    saved = torch.load(args.work / 'best_head.pt', map_location='cpu', weights_only=True)
    torch.set_num_threads(2)
    base = PretrainedV3Comparator(WEIGHTS, args.work / 'best_head.pt').eval()
    original = PretrainedV3Comparator(WEIGHTS, HEAD).eval()
    for key, value in original.features.state_dict().items():
        assert torch.equal(value, base.features.state_dict()[key])
    for key in ('feature_mean', 'feature_std'):
        assert torch.equal(getattr(original, key), getattr(base, key))
    leaf = dict(np.load(LEAF))
    model = LeafGuardedModel(base, leaf).eval()
    original_model = LeafGuardedModel(original, leaf).eval()
    args.output.mkdir(parents=True)
    probe = np.random.default_rng(2615).normal(size=(1, 3, 224, 224)).astype(np.float32)
    file = args.output / 'crop_model.onnx'
    torch.onnx.export(model, torch.from_numpy(probe), str(file), input_names=['image'],
                      output_names=['logits', 'embeddings', 'leaf_logit'], opset_version=17, dynamo=False)
    onnx.checker.check_model(onnx.load(file), full_check=True)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(str(file), options, providers=['CPUExecutionProvider'])
    root = Path(__file__).resolve().parents[2] / 'models/assets/model'
    old_session = ort.InferenceSession(str(root / 'crop_model.onnx'), options, providers=['CPUExecutionProvider'])
    # Runtime checks use TRAIN examples only; no reserved test manifest is opened.
    train_leaf = read_jsonl(Path('/workspace/research/field_data_next/kandahar_healthy/train.jsonl'))[0]
    train_object = read_jsonl(Path('/workspace/crop-data/nonleaf/train.jsonl'))[0]
    inputs = [('zero', np.zeros_like(probe)), ('random', probe)]
    for name, row in [('train_healthy_leaf', train_leaf), ('train_object', train_object)]:
        with Image.open(row['local_path']) as image:
            inputs.append((name, prepare_image(image)[None]))
    parity = []
    for name, image in inputs:
        with torch.inference_mode():
            expected = model(torch.from_numpy(image))
            old_expected = original_model(torch.from_numpy(image))
        actual = session.run(None, {'image': image})
        old_actual = old_session.run(None, {'image': image})
        for got, wanted in zip(actual, expected):
            np.testing.assert_allclose(got, wanted.numpy(), rtol=3e-4, atol=3e-4)
        assert torch.equal(expected[1], old_expected[1])
        assert torch.equal(expected[2], old_expected[2])
        for index in (1, 2):
            np.testing.assert_allclose(actual[index], old_actual[index], rtol=3e-4, atol=3e-4)
        parity.append({'input': name, 'leaf_output_max_error_vs_current': float(np.abs(actual[2] - old_actual[2]).max()),
                       'embedding_max_error_vs_current': float(np.abs(actual[1] - old_actual[1]).max())})
    model_hash = sha(file)
    version = 'mnv3-large-healthy-transfer-' + model_hash[:12]
    validation = json.loads((root / 'leaf_validation.json').read_text())
    validation.update(model_sha256=model_hash, model_version=version, disease_classifier_changed=True,
                      leaf_branch_unchanged_from_model_sha256=sha(root / 'crop_model.onnx'),
                      leaf_validation_evidence='Inherited unchanged backbone and leaf head; TRAIN-only runtime parity verified',
                      leaf_gate_test_evaluated_once=False)
    write(args.output / 'leaf_validation.json', validation)
    old = json.loads((root / 'model_metadata.json').read_text())
    metadata = {key: value for key, value in old.items() if not key.startswith('source_')}
    metadata.update(model_sha256=model_hash, model_version=version, model_size_bytes=file.stat().st_size,
                    diagnosis_validated=False, test_scope='Frozen candidate; exact-artifact calibration and tests pending')
    metadata['leaf_gate']['receipt_sha256'] = sha(args.output / 'leaf_validation.json')
    write(args.output / 'model_metadata.json', metadata)
    write(args.output / 'decision_policy.json', {'schema_version': 1, 'model_sha256': model_hash, 'model_version': version,
        'validated': False, 'temperature': 1., 'min_confidence': .75, 'min_margin': .15,
        'thresholds_calibrated': False, 'source_evaluated': False, 'source_acceptance_enabled': False,
        'allow_condition_specific_advice': False, 'reason': 'MODEL_NOT_VALIDATED', 'validation_status': 'new_graph_qualification_pending'})
    shutil.copy2(root / 'labels.json', args.output / 'labels.json')
    receipt = {'schema_version': 1, 'model_sha256': model_hash, 'model_version': version,
               'head_checkpoint_sha256': sha(args.work / 'best_head.pt'),
               'best_checkpoint_sha256': sha(args.work / 'best_head.pt'),
               'pretrained_weights_sha256': sha(WEIGHTS), 'leaf_head_sha256': sha(LEAF),
               'training_mode': 'frozen_V3_healthy_only_field_head_transfer',
               'training_protocol_sha256': sha(args.work / 'protocol.json'),
               'source_tune_accuracy': saved['source']['accuracy'], 'source_tune_macro_f1': saved['source']['macro_f1'],
               'field_tune_accuracy': saved['field']['accuracy'], 'field_tune_supported_macro_f1': saved['field']['macro_f1'],
               'new_healthy_train_files': 448, 'new_healthy_valid_correct': saved['healthy_valid_correct'],
               'new_healthy_valid_files': 18, 'source_training_files': 6324, 'field_training_files': 1080,
               'field_training_used': True, 'diagnosis_validated': False,
               'field_train_manifest_sha256': sha(Path('/workspace/crop-data/plantdoc-5467f601/partitions/train.jsonl')),
               'extra_train_manifest_sha256': sha(Path('/workspace/research/field_data_next/kandahar_healthy/train.jsonl')),
               'extra_train_manifest_path': '/workspace/research/field_data_next/kandahar_healthy/train.jsonl',
               'extra_train_receipt_sha256': sha(Path('/workspace/research/field_data_next/kandahar_healthy/receipt.json')),
               'extra_train_source_receipt_sha256': sha(Path('/workspace/research/field_data_next/kandahar_healthy/receipt.json')),
               'original_plantdoc_training_files': 632, 'extra_healthy_training_files': 448,
               'calibration_evaluated': False, 'held_out_test_executed': False,
               'backbone_and_leaf_head_unchanged': True, 'runtime_parity': parity}
    write(args.output / 'training_receipt.json', receipt)
    write(args.output / 'export_receipt.json', {**receipt, 'onnx_checker_passed': True,
          'output_shapes': [[1, 17], [1, 960], [1, 1]], 'phone_benchmark_executed': False})
    (args.output / 'MODEL_CARD.md').write_text('# Healthy-only field-transfer candidate\n\n'
        'Original frozen MobileNetV3-Large and binary leaf/object guard; only the linear 17-class head changed. '
        'Uses 448 audited new Healthy maize TRAIN photos. Broad Blight/Spot photos are excluded. '
        'New Healthy VALID improved from1/18 to5/18, all passing the leaf guard. '
        'This narrow tuning gain does not establish field disease accuracy. Exact-artifact qualification is pending.\n')
    print(json.dumps({'event': 'exported', 'model_sha256': model_hash, 'bundle': str(args.output), 'runtime_parity': parity}), flush=True)


if __name__ == '__main__':
    main()
