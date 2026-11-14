"""Treatment coverage and provenance checks, not agricultural efficacy tests."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'android/app/src/main/assets'
spec = importlib.util.spec_from_file_location('build_care_protocols', ROOT / 'tools/build_care_protocols.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class TreatmentProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / 'content/care_protocols.json'
        cls.model = json.loads(cls.source.read_text())
        cls.labels = json.loads((ROOT / 'contracts/labels.json').read_text())['labels']

    def test_complete_protocols_and_real_stage_action_differences(self):
        builder.validate(self.model, self.labels)
        self.assertEqual(len(self.model['protocols']), 17)

    def test_missing_recovery_information_fails_packaging(self):
        model = deepcopy(self.model)
        model['protocols']['tomato_early_blight']['translations']['en']['recovery_signs'] = []
        with self.assertRaises(ValueError): builder.validate(model, self.labels)

    def test_identical_mild_and_severe_actions_fail_packaging(self):
        model = deepcopy(self.model)
        plans = model['protocols']['potato_late_blight']['translations']['en']['stage_plans']
        plans['SEVERE']['actions'] = plans['MILD']['actions']
        with self.assertRaises(ValueError): builder.validate(model, self.labels)

    def test_missing_locale_fails_packaging(self):
        model = deepcopy(self.model)
        model['protocols']['maize_common_rust']['translations']['kn']['audio_summary'] = ''
        with self.assertRaises(ValueError): builder.validate(model, self.labels)

    def test_unsupported_efficacy_claim_fails_packaging(self):
        model = deepcopy(self.model)
        model['field_validated'] = True
        with self.assertRaises(ValueError): builder.validate(model, self.labels)

    def test_unread_reference_cannot_authorize_chemical_option(self):
        model = deepcopy(self.model)
        source = {'id': 'unread-test', 'title': 'Unread reference', 'url': 'https://example.org/', 'verification_status': 'not_read'}
        model['sources'].append(source)
        for language in ('en', 'kn', 'hi'):
            option = model['protocols']['tomato_bacterial_spot']['translations'][language]['treatment_options'][0]
            option['category'] = 'chemical'
            option['source_ids'] = [source['id']]
        with self.assertRaises(ValueError): builder.validate(model, self.labels)

    def test_packaged_content_and_implementation_receipt_match(self):
        self.assertEqual(self.source.read_bytes(), (ASSETS / 'content/care_protocols.json').read_bytes())
        receipt = json.loads((ASSETS / 'content/care_protocols_receipt.json').read_text())
        self.assertEqual(receipt['protocol_sha256'], builder.sha(self.source))
        self.assertEqual(len(receipt['implementation_sha256']), 2)
        for name, expected in receipt['implementation_sha256'].items():
            self.assertEqual(builder.sha(ROOT / name), expected)

    def test_treatment_narration_complete_and_bound_to_actual_text(self):
        sys.path.insert(0, str(ROOT / 'content'))
        try:
            from generate_treatment_voice import scripts_for
            expected_scripts = scripts_for(self.model)
        finally:
            sys.path.pop(0)
        manifest = json.loads((ASSETS / 'content/treatment_audio_manifest.json').read_text())
        self.assertFalse(manifest['runtime_network_required'])
        self.assertFalse(manifest['speech_weights_packaged'])
        self.assertEqual(manifest['care_protocols_sha256'], builder.sha(self.source))
        expected = {f'audio/{lang}/treatment_{name}.ogg' for lang in ('en', 'kn', 'hi')
                    for name in [*self.model['protocols'], 'stage_mild', 'stage_moderate', 'stage_severe', 'stage_unknown']}
        clips = manifest['clips']
        self.assertEqual(len(clips), 63)
        self.assertEqual({clip['path'] for clip in clips}, expected)
        for clip in clips:
            self.assertEqual(clip['text'], expected_scripts[clip['path']])
            self.assertEqual(builder.sha(ASSETS / clip['path']), clip['sha256'])
            self.assertEqual(hashlib.sha256(clip['text'].encode()).hexdigest(), clip['text_sha256'])
            self.assertGreater(clip['duration_seconds'], 1)


if __name__ == '__main__': unittest.main()
