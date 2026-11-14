#!/usr/bin/env python3
"""Validate and package the offline advisory knowledge model; no training occurs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('overview', 'curability', 'do_now', 'management', 'prevention', 'escalation')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(model: dict, labels: list[dict]) -> None:
    if model.get('schema_version') != 1 or model.get('model_type') != 'expert_decision_model':
        raise ValueError('Unsupported advisory model format')
    for flag in ('trained', 'agronomist_reviewed', 'field_validated'):
        if model.get(flag) is not False:
            raise ValueError(f'Unsupported advisory validation claim: {flag}')
    if set(model.get('languages', [])) != {'en', 'kn', 'hi'}:
        raise ValueError('Expected all three supported languages')
    profiles = model['profiles']
    if set(profiles) != {label['id'] for label in labels}:
        raise ValueError('Advisory categories differ from disease-model labels')
    source_ids = {source['id'] for source in model['sources']}
    if len(source_ids) != len(model['sources']):
        raise ValueError('Duplicate source IDs')
    for source in model['sources']:
        if not source.get('verification_status') or not source.get('url', '').startswith('https://'):
            raise ValueError('Missing source URL or explicit verification status')
    for label in labels:
        key = label['id']
        item = profiles[key]
        if item['crop_id'] != label['crop_id']:
            raise ValueError(f'Wrong crop for {key}')
        if not item['source_ids'] or not set(item['source_ids']) <= source_ids:
            raise ValueError(f'Unresolved care sources for {key}')
        if key.endswith('_healthy') != (item['kind'] == 'healthy'):
            raise ValueError(f'Healthy category mismatch: {key}')
        if key.endswith('_late_blight') and (item['kind'] != 'oomycete' or item['risk'] != 'rapid_blight'):
            raise ValueError(f'Late-blight risk classification mismatch: {key}')
        if key.endswith('_virus') and (item['kind'] != 'viral' or item['risk'] != 'virus'):
            raise ValueError(f'Virus classification mismatch: {key}')
        for language in ('en', 'kn', 'hi'):
            copy = item['translations'][language]
            for field in FIELDS:
                value = copy[field]
                if field in ('overview', 'curability'):
                    good = isinstance(value, str) and bool(value.strip())
                else:
                    good = isinstance(value, list) and bool(value) and all(isinstance(v, str) and v.strip() for v in value)
                if not good:
                    raise ValueError(f'Missing {key}/{language}/{field}')
            joined = ' '.join(str(copy[field]) for field in FIELDS)
            if language == 'kn' and not any('\u0c80' <= c <= '\u0cff' for c in joined):
                raise ValueError(f'Missing Kannada text for {key}')
            if language == 'hi' and not any('\u0900' <= c <= '\u097f' for c in joined):
                raise ValueError(f'Missing Hindi text for {key}')


def build() -> dict:
    source = ROOT / 'content/advisory_model.json'
    model = json.loads(source.read_text())
    labels = json.loads((ROOT / 'contracts/labels.json').read_text())['labels']
    validate(model, labels)
    implementations = [ROOT / 'frontend/src/lib/advisory.ts',
                       ROOT / 'android/app/src/main/java/com/debuggers/crophealth/domain/AdvisoryDecisionModel.kt']
    receipt = {
        'schema_version': 1,
        'model_version': model['model_version'],
        'model_type': model['model_type'],
        'profile_sha256': digest(source),
        'profile_count': len(model['profiles']),
        'languages': model['languages'],
        'trained': False,
        'field_validated': False,
        'agronomist_reviewed': False,
        'implementation_sha256': {str(p.relative_to(ROOT)): digest(p) for p in implementations if p.exists()},
        'behavior_cases_sha256': digest(ROOT / 'contracts/fixtures/advisory_cases.json'),
        'scope': 'Disease-specific draft knowledge plus deterministic farmer-reported triage. Behavior tests do not establish agricultural correctness or treatment efficacy.',
    }
    packaged = ROOT / 'android/app/src/main/assets/content'
    packaged.mkdir(parents=True, exist_ok=True)
    (packaged / 'advisory_model.json').write_bytes(source.read_bytes())
    text = json.dumps(receipt, indent=2) + '\n'
    (packaged / 'advisory_receipt.json').write_text(text)
    (ROOT / 'models/advisory/model_receipt.json').write_text(text)
    return receipt


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
