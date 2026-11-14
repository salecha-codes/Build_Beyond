#!/usr/bin/env python3
"""Package complete, provenance-checked care protocols. No clinical training."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LISTS = ('confirm_checks', 'look_alikes', 'avoid', 'recovery_signs', 'failure_signs', 'expert_questions')
CATEGORIES = {'cultural', 'biological', 'chemical', 'monitoring', 'expert'}
READ_SOURCE_STATUSES = {'retrieved_mirror_document', 'retrieved_primary_document', 'retrieved_primary'}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def lines(value, count=1) -> bool:
    return isinstance(value, list) and len(value) >= count and all(nonempty(x) for x in value)


def validate(model: dict, labels: list[dict]) -> None:
    if model.get('schema_version') != 1 or not nonempty(model.get('version')):
        raise ValueError('Unsupported care protocol version')
    if any(model.get(flag) is not False for flag in ('agronomist_reviewed', 'field_validated')):
        raise ValueError('Unsupported treatment-validation claim')
    if set(model['protocols']) != {label['id'] for label in labels}:
        raise ValueError('Care protocols must cover the exact 17 dataset categories')
    sources = {row['id']: row for row in model['sources']}
    if len(sources) != len(model['sources']):
        raise ValueError('Duplicate care source ID')
    for source in sources.values():
        if not source.get('url', '').startswith('https://') or not nonempty(source.get('verification_status')):
            raise ValueError('Missing care source URL/access status')
    for label in labels:
        cid = label['id']
        p = model['protocols'][cid]
        if p['crop_id'] != label['crop_id'] or not p['source_ids'] or not set(p['source_ids']) <= sources.keys():
            raise ValueError(f'Wrong crop or unresolved source: {cid}')
        option_ids = None
        for lang in ('en', 'kn', 'hi'):
            copy = p['translations'][lang]
            if not nonempty(copy.get('goal')) or not nonempty(copy.get('audio_summary')):
                raise ValueError(f'Missing treatment goal or narration: {cid}/{lang}')
            for key in LISTS:
                if not lines(copy.get(key)):
                    raise ValueError(f'Missing useful {key}: {cid}/{lang}')
            options = copy.get('treatment_options')
            if not isinstance(options, list) or len(options) < 2:
                raise ValueError(f'Expected distinct management options: {cid}/{lang}')
            ids = [option['id'] for option in options]
            if len(ids) != len(set(ids)) or (option_ids is not None and ids != option_ids):
                raise ValueError(f'Treatment IDs differ across languages: {cid}/{lang}')
            option_ids = ids
            for option in options:
                if any(not nonempty(option.get(key)) for key in ('id', 'title', 'when', 'limits')) or not lines(option.get('steps'), 2):
                    raise ValueError(f'Incomplete treatment option: {cid}/{lang}')
                category = option.get('category', 'cultural')
                if category not in CATEGORIES or not option.get('source_ids') or not set(option['source_ids']) <= sources.keys():
                    raise ValueError(f'Unsupported treatment source/category: {cid}/{lang}')
                if category == 'chemical' and not any(sources[sid]['verification_status'] in READ_SOURCE_STATUSES for sid in option['source_ids']):
                    raise ValueError(f'Chemical discussion requires a retrieved document: {cid}/{lang}')
            plans = copy['stage_plans']
            if set(plans) != {'MILD', 'MODERATE', 'SEVERE'}:
                raise ValueError(f'Missing severity pathways: {cid}/{lang}')
            for plan in plans.values():
                if not nonempty(plan.get('title')) or not lines(plan.get('actions'), 2):
                    raise ValueError(f'Empty severity action plan: {cid}/{lang}')
            if len({tuple(plans[stage]['actions']) for stage in plans}) != 3:
                raise ValueError(f'Severity must change actions: {cid}/{lang}')
            visits = copy['follow_up']
            if not isinstance(visits, list) or len(visits) < 3 or any(
                    not all(nonempty(visit.get(k)) for k in ('when', 'check', 'action')) for visit in visits):
                raise ValueError(f'Missing actionable follow-up schedule: {cid}/{lang}')
            text = json.dumps(copy, ensure_ascii=False)
            if lang == 'kn' and not any('\u0c80' <= c <= '\u0cff' for c in text):
                raise ValueError(f'Missing Kannada protocol: {cid}')
            if lang == 'hi' and not any('\u0900' <= c <= '\u097f' for c in text):
                raise ValueError(f'Missing Hindi protocol: {cid}')


def build() -> dict:
    source = ROOT / 'content/care_protocols.json'
    model = json.loads(source.read_text())
    labels = json.loads((ROOT / 'contracts/labels.json').read_text())['labels']
    validate(model, labels)
    implementations = [ROOT / 'frontend/src/lib/careProtocols.ts',
                       ROOT / 'android/app/src/main/java/com/debuggers/crophealth/domain/CarePlanSelection.kt']
    receipt = {'schema_version': 1, 'version': model['version'], 'protocol_sha256': sha(source),
               'protocol_count': 17, 'languages': ['en', 'kn', 'hi'],
               'agronomist_reviewed': False, 'field_validated': False,
               'trained': False, 'model_type': 'conditional_treatment_knowledge_and_stage_selection',
               'implementation_sha256': {str(p.relative_to(ROOT)): sha(p) for p in implementations if p.exists()},
               'scope': 'Engineering coverage/provenance, not treatment efficacy, crop registration or measured image severity.'}
    assets = ROOT / 'android/app/src/main/assets/content'
    assets.mkdir(parents=True, exist_ok=True)
    (assets / 'care_protocols.json').write_bytes(source.read_bytes())
    text = json.dumps(receipt, indent=2) + '\n'
    (assets / 'care_protocols_receipt.json').write_text(text)
    (ROOT / 'models/advisory/care_protocols_receipt.json').write_text(text)
    return receipt


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
