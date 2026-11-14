#!/usr/bin/env python3
"""Asset/contract checks; these are not agricultural or native-language validation."""
import hashlib, json, pathlib, subprocess, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
ASSETS=ROOT/'android/app/src/main/assets'
CATALOG=json.loads((ASSETS/'content/catalog.json').read_text())
MANIFEST=json.loads((ASSETS/'content/audio_manifest.json').read_text())

class OfflineContentTests(unittest.TestCase):
    def test_labels_match_model_contract(self):
        labels=json.loads((ROOT/'contracts/labels.json').read_text())['labels']
        self.assertEqual(len(labels),17)
        self.assertEqual({x['id'] for x in labels},set(CATALOG['conditions']))
    def test_each_condition_has_complete_bilingual_observation_guidance(self):
        for cid,item in CATALOG['conditions'].items():
            self.assertFalse(item['chemical_treatment_enabled'])
            self.assertEqual(item['review_status'],'general_observation_only_not_expert_reviewed')
            for lang in ['en','kn']:
                copy=item['translations'][lang]
                for field in ['name','summary','symptoms','actions','prevention','caution','audio_asset']:
                    self.assertTrue(copy[field],(cid,lang,field))
                if lang=='kn':
                    self.assertTrue(any('\u0c80'<=c<='\u0cff' for c in copy['summary']))
                    self.assertEqual(copy['translation_status'],'draft_not_native_reviewed')
    def test_prompt_audio_covers_required_paths(self):
        required={'uncertain','retake','offline','crop_mismatch','model_unavailable','concern_coverage','concern_expert','check_expert'}
        self.assertTrue(required <= set(CATALOG['prompts']))
        for item in CATALOG['prompts'].values():
            for lang in ['en','kn']:
                self.assertTrue(item[lang]['message'])
                self.assertTrue((ASSETS/item[lang]['audio_asset']).is_file())
    def test_all_audio_hashes_and_durations_are_valid(self):
        paths=[x['path'] for x in MANIFEST['clips']]
        self.assertEqual(len(paths),60)
        self.assertEqual(len(paths),len(set(paths)))
        for clip in MANIFEST['clips']:
            target=ASSETS/clip['path']
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),clip['sha256'])
            self.assertGreater(clip['duration_seconds'],1.0)
            self.assertLess(clip['duration_seconds'],45.0)
            self.assertGreater(clip['bytes'],1000)
    def test_all_ogg_assets_decode_offline(self):
        for clip in MANIFEST['clips']:
            result=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(ASSETS/clip['path']),'-f','null','-'],capture_output=True)
            self.assertEqual(result.returncode,0,(clip['path'],result.stderr.decode()))
    def test_sources_do_not_claim_unread_treatment_verification(self):
        self.assertTrue(all(x['status'].endswith('not_read') for x in CATALOG['primary_advisory_access']))
        for item in CATALOG['conditions'].values():
            self.assertTrue(all(s['verification_status']=='taxonomy_only' for s in item['sources']))

if __name__=='__main__':unittest.main(verbosity=2)
