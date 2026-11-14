"""Knowledge/artifact checks, not agronomic validation or model accuracy tests."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'android/app/src/main/assets'
spec = importlib.util.spec_from_file_location('build_advisory_bundle', ROOT / 'tools/build_advisory_bundle.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class AdvisoryArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / 'content/advisory_model.json'
        cls.model = json.loads(cls.source.read_text())
        cls.labels = json.loads((ROOT / 'contracts/labels.json').read_text())['labels']

    def test_complete_trilingual_profiles_match_classifier_taxonomy(self):
        builder.validate(self.model, self.labels)
        self.assertEqual(len(self.model['profiles']), 17)

    def test_cannot_package_unsupported_validation_or_training_claims(self):
        for flag in ('trained', 'field_validated', 'agronomist_reviewed'):
            model = deepcopy(self.model)
            model[flag] = True
            with self.assertRaises(ValueError):
                builder.validate(model, self.labels)

    def test_missing_language_fails_packaging(self):
        model = deepcopy(self.model)
        model['profiles']['tomato_mosaic_virus']['translations']['hi']['curability'] = ''
        with self.assertRaises(ValueError):
            builder.validate(model, self.labels)

    def test_wrong_late_blight_risk_fails_packaging(self):
        model = deepcopy(self.model)
        model['profiles']['potato_late_blight']['risk'] = 'routine'
        with self.assertRaises(ValueError):
            builder.validate(model, self.labels)

    def test_unresolved_reference_fails_packaging(self):
        model = deepcopy(self.model)
        model['profiles']['maize_common_rust']['source_ids'].append('nonexistent')
        with self.assertRaises(ValueError):
            builder.validate(model, self.labels)

    def test_packaged_artifact_and_receipt_match_canonical_profiles(self):
        self.assertEqual(self.source.read_bytes(), (ASSETS / 'content/advisory_model.json').read_bytes())
        receipt = json.loads((ASSETS / 'content/advisory_receipt.json').read_text())
        self.assertEqual(receipt['profile_sha256'], builder.digest(self.source))
        self.assertFalse(receipt['field_validated'])
        self.assertEqual(receipt['profile_count'], 17)
        self.assertEqual(len(receipt['implementation_sha256']), 2)
        for name, expected in receipt['implementation_sha256'].items():
            self.assertEqual(builder.digest(ROOT / name), expected)

    def test_all_new_narration_scripts_and_audio_are_bound_to_profiles(self):
        manifest = json.loads((ASSETS / 'content/advisory_audio_manifest.json').read_text())
        self.assertEqual(manifest['advisory_model_sha256'], builder.digest(self.source))
        self.assertFalse(manifest['runtime_network_required'])
        self.assertFalse(manifest['speech_weights_packaged'])
        clips = manifest['clips']
        self.assertEqual(len(clips), 75)
        expected = {f'audio/{lang}/advisory_{name}.ogg'
                    for lang in ('en', 'kn', 'hi')
                    for name in [*self.model['profiles'], 'urgent', 'same_day', 'soon', 'monitor',
                                 'question_coverage', 'question_wilting', 'question_fruit_stem', 'question_wet_weather']}
        self.assertEqual({clip['path'] for clip in clips}, expected)
        for clip in clips:
            path = ASSETS / clip['path']
            self.assertEqual(builder.digest(path), clip['sha256'])
            self.assertEqual(hashlib.sha256(clip['text'].encode()).hexdigest(), clip['text_sha256'])
            self.assertGreater(clip['duration_seconds'], 1)


if __name__ == '__main__':
    unittest.main()
