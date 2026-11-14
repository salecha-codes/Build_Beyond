#!/usr/bin/env python3
"""Build fixed advisory narration locally; never ship speech checkpoints.

Generate each language into the same staging root, then --install-from that
root. New advisory assets and their independent manifest are the only installed
files; the previous 90 observation clips remain untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unicodedata

from generate_english_voice import VOICE_MODELS, normalize_and_encode, sha256
from generate_hindi_voice import MODEL_SHA256 as HI_HASH, SOURCE as HI_SOURCE

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ('en', 'kn', 'hi')
KANNADA_CHECKPOINTS = {
    'fastpitch/best_model.pth': '086ccd302bb73900a66b98ccd3df3b24175bf135eb80ecd966b043bb3f342841',
    'fastpitch/config.json': '05e43b0047ba4dace72a3ee1bcb834eb3d985aaea99bbaad36f6decfc8da76bd',
    'fastpitch/speakers.pth': 'f665e358b34b232fb27f7c8cd3968fcd47784a7be065ae127f611c33ee809bea',
    'hifigan/best_model.pth': 'b08cecc8c44078d39be4864ea173629ed56c67ebd4ac8d286988e8dade379448',
    'hifigan/config.json': '988fa675394e5fad9b6690a15544271e9673aaac9bf63a43e42370b0cd0cf0b9',
}
QUESTIONS = {
    'en': {
        'coverage': 'How much of the leaf is visibly affected? Choose no visible damage, a few spots covering less than ten percent, some spots covering ten to thirty percent, many spots covering more than thirty percent, or not sure.',
        'wilting': 'Are plants wilting or dying? Choose yes, no, or not sure.',
        'fruit_stem': 'Are fruits, tubers or stems also affected? Choose yes, no, or not sure.',
        'wet_weather': 'Has the crop had wet or humid conditions? Choose yes, no, or not sure.',
    },
    'kn': {
        'coverage': 'ಎಲೆಯ ಎಷ್ಟು ಭಾಗಕ್ಕೆ ಹಾನಿಯಾಗಿದೆ? ಕಾಣುವ ಹಾನಿ ಇಲ್ಲ, ಶೇಕಡಾ ಹತ್ತಕ್ಕಿಂತ ಕಡಿಮೆ ಭಾಗದಲ್ಲಿ ಕೆಲವು ಕಲೆಗಳು, ಶೇಕಡಾ ಹತ್ತರಿಂದ ಮೂವತ್ತರವರೆಗೆ ಕಲೆಗಳು, ಶೇಕಡಾ ಮೂವತ್ತಕ್ಕಿಂತ ಹೆಚ್ಚು ಭಾಗದಲ್ಲಿ ಅನೇಕ ಕಲೆಗಳು, ಅಥವಾ ಖಚಿತವಿಲ್ಲ ಎಂದು ಆಯ್ಕೆಮಾಡಿ.',
        'wilting': 'ಗಿಡಗಳು ಬಾಡುತ್ತಿವೆಯೇ ಅಥವಾ ಸಾಯುತ್ತಿವೆಯೇ? ಹೌದು, ಇಲ್ಲ, ಅಥವಾ ಖಚಿತವಿಲ್ಲ ಎಂದು ಆಯ್ಕೆಮಾಡಿ.',
        'fruit_stem': 'ಹಣ್ಣು, ಗೆಡ್ಡೆ ಅಥವಾ ಕಾಂಡಕ್ಕೂ ಹಾನಿಯಾಗಿದೆಯೇ? ಹೌದು, ಇಲ್ಲ, ಅಥವಾ ಖಚಿತವಿಲ್ಲ ಎಂದು ಆಯ್ಕೆಮಾಡಿ.',
        'wet_weather': 'ಬೆಳೆಯ ಸುತ್ತ ತೇವ ಅಥವಾ ಆರ್ದ್ರತೆ ಇದೆಯೇ? ಹೌದು, ಇಲ್ಲ, ಅಥವಾ ಖಚಿತವಿಲ್ಲ ಎಂದು ಆಯ್ಕೆಮಾಡಿ.',
    },
    'hi': {
        'coverage': 'पत्ते का कितना हिस्सा प्रभावित है? कोई नुकसान नहीं दिखता, दस प्रतिशत से कम हिस्से पर कुछ धब्बे, दस से तीस प्रतिशत हिस्से पर धब्बे, तीस प्रतिशत से अधिक हिस्से पर बहुत धब्बे, या पता नहीं चुनें।',
        'wilting': 'क्या पौधे मुरझा रहे हैं या मर रहे हैं? हाँ, नहीं, या पता नहीं चुनें।',
        'fruit_stem': 'क्या फल, कंद या तने भी प्रभावित हैं? हाँ, नहीं, या पता नहीं चुनें।',
        'wet_weather': 'क्या फसल के आसपास नमी या आर्द्रता रही है? हाँ, नहीं, या पता नहीं चुनें।',
    },
}
PREFIX = {
    'en': 'If this condition is confirmed, follow this care advice.',
    'kn': 'ಈ ರೋಗವು ದೃಢಪಟ್ಟರೆ ಮಾತ್ರ ಈ ಸಲಹೆಯನ್ನು ಅನುಸರಿಸಿ.',
    'hi': 'इस रोग की पुष्टि होने पर ही यह सलाह अपनाएं।',
}
HEALTHY_PREFIX = {
    'en': 'A healthy-looking leaf does not prove the whole crop is healthy.',
    'kn': 'ಒಂದು ಎಲೆ ಆರೋಗ್ಯಕರವಾಗಿ ಕಂಡರೂ ಇಡೀ ಬೆಳೆ ಆರೋಗ್ಯಕರವಾಗಿದೆ ಎಂದು ಹೇಳಲಾಗುವುದಿಲ್ಲ.',
    'hi': 'एक पत्ता स्वस्थ दिखने से पूरी फसल के स्वस्थ होने की पुष्टि नहीं होती।',
}
URGENCY = {
    'en': {
        'urgent': 'Urgent attention is needed. Wilting or fast spread across many plants needs a local agriculture expert now. Do not wait for another app scan. A model score alone must not decide treatment.',
        'same_day': 'Arrange advice from a local agriculture expert today. Severe reported damage or suspected late blight can need prompt action. Keep a record of symptoms and avoid working among wet plants.',
        'soon': 'Arrange a check within the next forty eight hours. Watch whether spots spread or plants wilt. If symptoms worsen, seek advice sooner. This is a suggested priority, not a confirmed diagnosis.',
        'monitor': 'Monitor the crop and check it again within forty eight hours. Take another photo in similar light. If damage spreads or plants wilt, seek advice sooner. Mild reported damage is not a guarantee that the crop is safe.',
    },
    'kn': {
        'urgent': 'ತುರ್ತು ಗಮನ ಬೇಕಾಗಿದೆ. ಗಿಡಗಳು ಬಾಡುತ್ತಿದ್ದರೆ ಅಥವಾ ರೋಗವು ಅನೇಕ ಗಿಡಗಳಿಗೆ ವೇಗವಾಗಿ ಹರಡುತ್ತಿದ್ದರೆ ಈಗಲೇ ಸ್ಥಳೀಯ ಕೃಷಿ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ. ಮತ್ತೊಂದು ಆಪ್ ಪರೀಕ್ಷೆಗಾಗಿ ಕಾಯಬೇಡಿ. ಮಾದರಿಯ ಅಂಕೆಯಿಂದ ಮಾತ್ರ ಚಿಕಿತ್ಸೆ ನಿರ್ಧರಿಸಬೇಡಿ.',
        'same_day': 'ಇಂದೇ ಸ್ಥಳೀಯ ಕೃಷಿ ತಜ್ಞರ ಸಲಹೆ ಪಡೆಯಿರಿ. ಹೆಚ್ಚು ಹಾನಿ ಅಥವಾ ತಡವಾದ ಅಂಗಮಾರಿ ಶಂಕೆ ಇದ್ದರೆ ತ್ವರಿತ ಕ್ರಮ ಬೇಕಾಗಬಹುದು. ಲಕ್ಷಣಗಳನ್ನು ದಾಖಲಿಸಿ. ಒದ್ದೆಯಾದ ಗಿಡಗಳ ನಡುವೆ ಕೆಲಸ ಮಾಡುವುದನ್ನು ತಪ್ಪಿಸಿ.',
        'soon': 'ಮುಂದಿನ ನಲವತ್ತೆಂಟು ಗಂಟೆಗಳೊಳಗೆ ಪರಿಶೀಲನೆ ಮಾಡಿಸಿ. ಕಲೆಗಳು ಹರಡುತ್ತಿವೆಯೇ ಅಥವಾ ಗಿಡಗಳು ಬಾಡುತ್ತಿವೆಯೇ ಗಮನಿಸಿ. ಲಕ್ಷಣಗಳು ಹೆಚ್ಚಾದರೆ ಬೇಗ ಸಲಹೆ ಪಡೆಯಿರಿ. ಇದು ಆದ್ಯತೆಯ ಸಲಹೆ ಮಾತ್ರ, ದೃಢಪಟ್ಟ ರೋಗನಿರ್ಣಯವಲ್ಲ.',
        'monitor': 'ಬೆಳೆಯನ್ನು ಗಮನಿಸಿ ಮುಂದಿನ ನಲವತ್ತೆಂಟು ಗಂಟೆಗಳೊಳಗೆ ಮತ್ತೆ ಪರಿಶೀಲಿಸಿ. ಅದೇ ರೀತಿಯ ಬೆಳಕಿನಲ್ಲಿ ಮತ್ತೊಂದು ಚಿತ್ರ ತೆಗೆಯಿರಿ. ಹಾನಿ ಹರಡಿದರೆ ಅಥವಾ ಗಿಡಗಳು ಬಾಡಿದರೆ ಬೇಗ ಸಲಹೆ ಪಡೆಯಿರಿ. ಕಡಿಮೆ ಹಾನಿ ಎಂದರೆ ಬೆಳೆ ಸುರಕ್ಷಿತವಾಗಿದೆ ಎಂಬ ಖಾತರಿಯಲ್ಲ.',
    },
    'hi': {
        'urgent': 'तुरंत ध्यान देने की जरूरत है। पौधे मुरझा रहे हों या कई पौधों में लक्षण तेजी से फैल रहे हों तो अभी स्थानीय कृषि विशेषज्ञ से संपर्क करें। ऐप में अगली जांच का इंतजार न करें। केवल मॉडल के अंक से उपचार तय न करें।',
        'same_day': 'आज ही स्थानीय कृषि विशेषज्ञ की सलाह लें। अधिक नुकसान या पछेती झुलसा की आशंका में जल्द कार्रवाई जरूरी हो सकती है। लक्षणों का रिकॉर्ड रखें और गीले पौधों के बीच काम करने से बचें।',
        'soon': 'अगले अड़तालीस घंटों में जांच की व्यवस्था करें। देखें कि धब्बे फैल रहे हैं या पौधे मुरझा रहे हैं। लक्षण बढ़ें तो पहले सलाह लें। यह प्राथमिकता का सुझाव है, पक्का रोग निदान नहीं।',
        'monitor': 'फसल पर नजर रखें और अगले अड़तालीस घंटों में फिर जांचें। समान रोशनी में दोबारा तस्वीर लें। नुकसान फैले या पौधे मुरझाएं तो पहले सलाह लें। हल्का दिखने वाला नुकसान फसल के सुरक्षित होने की गारंटी नहीं है।',
    },
}


def scripts_for(model: dict) -> dict[str, str]:
    result = {}
    for lang in LANGUAGES:
        for condition, profile in sorted(model['profiles'].items()):
            copy = profile['translations'][lang]
            prefix = HEALTHY_PREFIX[lang] if profile['kind'] == 'healthy' else PREFIX[lang]
            text = ' '.join([prefix, copy['curability'], *copy['do_now'][:2]])
            result[f'audio/{lang}/advisory_{condition}.ogg'] = unicodedata.normalize('NFC', text)
        for level, text in URGENCY[lang].items():
            result[f'audio/{lang}/advisory_{level}.ogg'] = unicodedata.normalize('NFC', text)
        for key, text in QUESTIONS[lang].items():
            result[f'audio/{lang}/advisory_question_{key}.ogg'] = unicodedata.normalize('NFC', text)
    return result


def generate_piper(args, scripts: dict[str, str], model: dict) -> None:
    import numpy as np
    import sherpa_onnx
    import soundfile as sf

    voice = VOICE_MODELS['ljspeech-high'] if args.language == 'en' else {
        'file': 'hi_IN-pratham-medium.onnx', 'model_sha256': HI_HASH,
        'name': 'Piper hi_IN-pratham-medium', 'source': HI_SOURCE,
        'license': 'Dataset CC BY-NC-SA 4.0 per packaged model card; separate converted checkpoint terms not declared.',
    }
    checkpoint = args.model_dir / voice['file']
    if sha256(checkpoint) != voice['model_sha256']:
        raise ValueError('Pinned voice checkpoint SHA-256 differs')
    config = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
        vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(checkpoint),
            tokens=str(args.model_dir / 'tokens.txt'), data_dir=str(args.model_dir / 'espeak-ng-data')),
        num_threads=args.threads, provider='cpu'), max_num_sentences=1)
    if not config.validate():
        raise ValueError('Invalid offline neural speech configuration')
    engine = sherpa_onnx.OfflineTts(config)
    receipt_path = args.output / f'provenance-{args.language}.json'
    previous = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
    previous_rows = {row['path']: row for row in previous.get('clips', [])}
    rows = []
    for key, text in scripts.items():
        if not key.startswith(f'audio/{args.language}/'):
            continue
        target = args.output / key
        target.parent.mkdir(parents=True, exist_ok=True)
        cached = previous_rows.get(key)
        if cached and cached.get('text') == text and target.is_file() and sha256(target) == cached['sha256']:
            rows.append(cached)
            continue
        audio = engine.generate(text, sid=0, speed=.94)
        samples = np.asarray(audio.samples, dtype=np.float32)
        if samples.size < audio.sample_rate / 2 or not np.isfinite(samples).all() or np.max(np.abs(samples)) < .01:
            raise ValueError(f'Invalid neural synthesis: {key}')
        with tempfile.TemporaryDirectory(prefix='crop-advisory-voice-') as temp:
            wav = Path(temp) / 'speech.wav'
            sf.write(wav, samples, audio.sample_rate, subtype='PCM_16')
            normalize_and_encode(wav, target, '64k')
        decoded, rate = sf.read(target, dtype='float32')
        if rate != 24000 or decoded.ndim != 1 or not np.isfinite(decoded).all() or not .01 < np.max(np.abs(decoded)) <= 1:
            raise ValueError(f'Invalid encoded narration: {key}')
        rows.append({'path': key, 'text': text, 'sha256': sha256(target),
                     'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                     'duration_seconds': len(decoded) / rate, 'bytes': target.stat().st_size,
                     'sample_rate': rate, 'channels': 1})
        print(json.dumps({'generated': key, 'duration_seconds': rows[-1]['duration_seconds']}), flush=True)
    receipt = {'schema_version': 1, 'model_version': model['model_version'],
               'voice': voice['name'], 'source': voice['source'], 'license': voice['license'],
               'model_sha256': voice['model_sha256'], 'engine': f'sherpa-onnx {sherpa_onnx.__version__}; Piper/VITS',
               'review': 'full_decode_checked; pronunciation_and_agronomy_not_expert_reviewed', 'clips': rows}
    (args.output / f'provenance-{args.language}.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')


def install(args, model: dict, scripts: dict[str, str]) -> None:
    stage = args.install_from
    rows, voices = [], {}
    for lang in LANGUAGES:
        receipt = json.loads((stage / f'provenance-{lang}.json').read_text())
        if receipt.get('model_version', receipt.get('script_version')) != model['model_version']:
            raise ValueError(f'Advisory model version differs for {lang}')
        voices[lang] = {key: value for key, value in receipt.items() if key != 'clips'}
        for row in receipt['clips']:
            key = row['path']
            if not key.startswith(f'audio/{lang}/advisory_') or key not in scripts:
                raise ValueError(f'Unexpected advisory audio key: {key}')
            text = scripts[key]
            actual_text = row.get('text')
            if actual_text != text or sha256(stage/key) != row['sha256']:
                raise ValueError(f'Audio script/content mismatch: {key}')
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(stage/key), '-f', 'null', '-'], check=True)
            rows.append({**row, 'language': lang, 'text_sha256': hashlib.sha256(text.encode()).hexdigest()})
    if set(row['path'] for row in rows) != set(scripts) or len(rows) != 75:
        raise ValueError('Expected every one of 75 advisory narration clips exactly once')
    assets = ROOT/'android/app/src/main/assets'
    for row in rows:
        target = assets/row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stage/row['path'], target)
    manifest = {'schema_version': 1, 'model_version': model['model_version'],
                'advisory_model_sha256': sha256(args.profiles), 'runtime_network_required': False,
                'speech_weights_packaged': False, 'voices': voices,
                'review': 'technical_decode_only; native_listening_and_agronomy_review_pending',
                'total_clips': len(rows), 'total_bytes': sum(row['bytes'] for row in rows), 'clips': rows}
    (assets/'content/advisory_audio_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'installed': len(rows), 'bytes': manifest['total_bytes']}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles', type=Path, default=ROOT/'content/advisory_model.json')
    parser.add_argument('--language', choices=LANGUAGES)
    parser.add_argument('--model-dir', type=Path)
    parser.add_argument('--checkpoint-root', type=Path)
    parser.add_argument('--python-packages', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--install-from', type=Path)
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--fixed-only', action='store_true', help='Generate only urgency/question clips before profile review')
    args = parser.parse_args()
    model = ({'model_version': 'offline-advisory-v1', 'profiles': {}} if args.fixed_only
             else json.loads(args.profiles.read_text()))
    labels = json.loads((ROOT/'contracts/labels.json').read_text())['labels']
    if not args.fixed_only and set(model['profiles']) != {row['id'] for row in labels}:
        raise ValueError('Expected all 17 classifier categories before generating narration')
    scripts = scripts_for(model)
    if args.install_from:
        if args.fixed_only:
            parser.error('Partial fixed clips cannot be installed; generate all reviewed profiles first')
        install(args, model, scripts)
        return
    if not args.output or not args.language or not 1 <= args.threads <= 4:
        parser.error('--language, --output and 1–4 --threads are required')
    args.output = args.output.resolve()
    for forbidden in (ROOT/'android/app/src/main/assets', ROOT/'frontend/public', ROOT/'frontend/dist'):
        if args.output == forbidden or forbidden in args.output.parents:
            parser.error('Generate into staging, then install validated outputs')
    args.output.mkdir(parents=True, exist_ok=True)
    if args.language != 'kn':
        if not args.model_dir:
            parser.error('--model-dir required for Piper voices')
        generate_piper(args, scripts, model)
    else:
        if not args.checkpoint_root:
            parser.error('--checkpoint-root required for Kannada')
        checkpoint = args.checkpoint_root/'kn'
        if not checkpoint.exists():
            checkpoint = args.checkpoint_root
        for filename, digest in KANNADA_CHECKPOINTS.items():
            if sha256(checkpoint/filename) != digest:
                raise ValueError(f'Pinned Kannada checkpoint differs: {filename}')
        receipt_path = args.output/'provenance-kn.json'
        previous = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
        old_rows = {row['path']: row for row in previous.get('clips', [])}
        retained = {key: row for key, row in old_rows.items() if key in scripts
                    and row.get('text') == scripts[key] and (args.output/key).is_file()
                    and sha256(args.output/key) == row['sha256']}
        remaining = {key: text for key, text in scripts.items() if key.startswith('audio/kn/') and key not in retained}
        if not remaining:
            return
        script_path = args.output/'advisory_scripts.json'
        script_path.write_text(json.dumps({'script_version': model['model_version'], 'scripts': remaining}, ensure_ascii=False, indent=2)+'\n')
        command = [sys.executable, str(ROOT/'content/generate_indic_voice.py'), '--checkpoint-root', str(args.checkpoint_root),
                   '--scripts', str(script_path), '--output', str(args.output/'kn-stage'), '--threads', str(args.threads)]
        if args.python_packages:
            command += ['--python-packages', str(args.python_packages)]
        subprocess.run(command, check=True)
        stage = args.output/'kn-stage'
        shutil.copytree(stage/'audio/kn', args.output/'audio/kn', dirs_exist_ok=True)
        receipt = json.loads((stage/'provenance.json').read_text())
        receipt['clips'] = [*retained.values(), *receipt['clips']]
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()
