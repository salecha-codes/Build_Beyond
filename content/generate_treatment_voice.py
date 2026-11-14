#!/usr/bin/env python3
"""Generate and install fixed offline treatment/recovery summaries.

Uses the project's pinned build-time speech providers. Checkpoints never ship.
Generate languages into a staging directory, then validate with --install-from.
Existing observation/advisory audio and manifests are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

from generate_advisory_voice import KANNADA_CHECKPOINTS
from generate_english_voice import VOICE_MODELS, normalize_and_encode, sha256
from generate_hindi_voice import MODEL_SHA256 as HI_HASH, SOURCE as HI_SOURCE

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ('en', 'kn', 'hi')
PRIORITY_PREFIX = {
    'en': 'Follow the urgency shown on screen. Even mild damage can need advice today or immediate help.',
    'kn': 'ಪರದೆಯಲ್ಲಿ ತೋರಿಸಿದ ತುರ್ತು ಸೂಚನೆ ಅನುಸರಿಸಿ. ಕಡಿಮೆ ಹಾನಿಯಿದ್ದರೂ ಇಂದೇ ಸಲಹೆ ಅಥವಾ ತಕ್ಷಣ ಸಹಾಯ ಬೇಕಾಗಬಹುದು.',
    'hi': 'स्क्रीन पर बताई तात्कालिकता मानें। हल्के नुकसान में भी आज सलाह या तुरंत मदद की जरूरत हो सकती है।',
}
STAGES = {
    'en': {
        'mild': 'You reported mild damage. Use the mild-stage actions on this care plan, inspect nearby plants, and record a dated photo of the same leaf. Old spots may remain even when management is helping. Look for fewer new spots and healthy new growth. Follow the listed recheck steps. If damage spreads, plants wilt, or stems and fruits become affected, seek advice sooner. Suspected late blight still needs same-day advice even when damage looks mild.',
        'moderate': 'You reported moderate damage. Start the moderate-stage actions, compare several plants, and keep a dated record of new symptoms. Management aims to protect healthy tissue; old dead patches will not turn green again. Use only a product registered for this crop and problem, and follow its label rather than choosing a dose from this app. Follow the recovery checks and contact a crop adviser if symptoms continue to spread.',
        'severe': 'You reported severe signs. Follow the severe-stage actions and arrange prompt crop advice. Wilting, dying plants, or rapid spread across many plants need an expert now. Do not wait for old damaged leaves to recover. Protect remaining healthy plants and record fresh symptoms for confirmation. Do not increase spray strength or mix products to force recovery. The care plan explains what to monitor while help is arranged.',
        'unknown': 'There is not enough information to grade reported damage. Use the confirmation checks and answer the observation questions before selecting a stage plan. An uncertain answer is not the same as no damage. The treatment summary describes options if the disease is confirmed; it does not confirm the diagnosis. If plants are wilting, dying, or symptoms are spreading quickly, get local crop advice now. Suspected late blight needs advice today.',
    },
    'kn': {
        'mild': 'ನೀವು ಕಡಿಮೆ ಹಾನಿ ಇದೆ ಎಂದು ತಿಳಿಸಿದ್ದೀರಿ. ಈ ಆರೈಕೆ ಯೋಜನೆಯ ಕಡಿಮೆ ಹಾನಿಯ ಕ್ರಮ ಅನುಸರಿಸಿ. ಹತ್ತಿರದ ಗಿಡಗಳನ್ನು ಪರಿಶೀಲಿಸಿ, ಅದೇ ಎಲೆಯ ದಿನಾಂಕದ ಚಿತ್ರ ಉಳಿಸಿ. ನಿರ್ವಹಣೆ ಸಹಾಯ ಮಾಡಿದರೂ ಹಳೆಯ ಕಲೆಗಳು ಉಳಿಯಬಹುದು. ಹೊಸ ಕಲೆಗಳು ಕಡಿಮೆಯಾಗುತ್ತಿವೆಯೇ ಮತ್ತು ಹೊಸ ಬೆಳವಣಿಗೆ ಚೆನ್ನಾಗಿದೆಯೇ ನೋಡಿ. ಯೋಜನೆಯ ಮರುಪರಿಶೀಲನೆ ಕ್ರಮ ಅನುಸರಿಸಿ. ಹಾನಿ ಹರಡಿದರೆ, ಗಿಡ ಬಾಡಿದರೆ ಅಥವಾ ಕಾಂಡ ಮತ್ತು ಹಣ್ಣಿಗೆ ಹಾನಿಯಾದರೆ ಬೇಗ ಸಲಹೆ ಪಡೆಯಿರಿ. ತಡವಾದ ಅಂಗಮಾರಿ ಶಂಕೆ ಇದ್ದರೆ ಕಡಿಮೆ ಹಾನಿಯಿದ್ದರೂ ಇಂದೇ ಸಲಹೆ ಬೇಕು.',
        'moderate': 'ನೀವು ಮಧ್ಯಮ ಹಾನಿ ಇದೆ ಎಂದು ತಿಳಿಸಿದ್ದೀರಿ. ಮಧ್ಯಮ ಹಾನಿಯ ಕ್ರಮ ಪ್ರಾರಂಭಿಸಿ, ಹಲವು ಗಿಡಗಳನ್ನು ಹೋಲಿಸಿ ಮತ್ತು ಹೊಸ ಲಕ್ಷಣಗಳ ದಿನಾಂಕದ ದಾಖಲೆ ಇಡಿ. ನಿರ್ವಹಣೆ ಆರೋಗ್ಯಕರ ಭಾಗ ರಕ್ಷಿಸುತ್ತದೆ; ಹಳೆಯ ಸತ್ತ ಕಲೆಗಳು ಮತ್ತೆ ಹಸಿರಾಗುವುದಿಲ್ಲ. ಈ ಬೆಳೆ ಮತ್ತು ಸಮಸ್ಯೆಗೆ ನೋಂದಾಯಿತ ಉತ್ಪನ್ನ ಮಾತ್ರ ಬಳಸಿ. ಆಪ್‌ನಿಂದ ಪ್ರಮಾಣ ಆಯ್ಕೆ ಮಾಡುವ ಬದಲು ಲೇಬಲ್ ಅನುಸರಿಸಿ. ಚೇತರಿಕೆಯ ಪರಿಶೀಲನೆ ಮಾಡಿ. ಲಕ್ಷಣಗಳು ಹರಡುತ್ತಿದ್ದರೆ ಕೃಷಿ ಸಲಹೆಗಾರರನ್ನು ಸಂಪರ್ಕಿಸಿ.',
        'severe': 'ನೀವು ತೀವ್ರ ಲಕ್ಷಣಗಳಿವೆ ಎಂದು ತಿಳಿಸಿದ್ದೀರಿ. ತೀವ್ರ ಹಾನಿಯ ಕ್ರಮ ಅನುಸರಿಸಿ ಮತ್ತು ತಕ್ಷಣ ಬೆಳೆ ಸಲಹೆ ಪಡೆಯಲು ವ್ಯವಸ್ಥೆ ಮಾಡಿ. ಗಿಡಗಳು ಬಾಡುವುದು, ಸಾಯುವುದು ಅಥವಾ ಅನೇಕ ಗಿಡಗಳಿಗೆ ವೇಗವಾಗಿ ಹರಡುವುದು ಇದ್ದರೆ ಈಗಲೇ ತಜ್ಞರ ಸಹಾಯ ಬೇಕು. ಹಳೆಯ ಹಾನಿಯಾದ ಎಲೆ ಚೇತರಿಸಿಕೊಳ್ಳಲು ಕಾಯಬೇಡಿ. ಉಳಿದ ಆರೋಗ್ಯಕರ ಗಿಡಗಳನ್ನು ರಕ್ಷಿಸಿ, ಹೊಸ ಲಕ್ಷಣ ದಾಖಲಿಸಿ. ಚೇತರಿಕೆಗಾಗಿ ಸಿಂಪಡಣೆಯ ಸಾಂದ್ರತೆ ಹೆಚ್ಚಿಸಬೇಡಿ ಅಥವಾ ಉತ್ಪನ್ನಗಳನ್ನು ಬೆರೆಸಬೇಡಿ. ಸಹಾಯ ಬರುವವರೆಗೆ ಗಮನಿಸಬೇಕಾದವು ಯೋಜನೆಯಲ್ಲಿವೆ.',
        'unknown': 'ಹಾನಿಯ ಮಟ್ಟ ತಿಳಿಯಲು ಮಾಹಿತಿ ಸಾಕಾಗಿಲ್ಲ. ರೋಗ ದೃಢೀಕರಣದ ಪರಿಶೀಲನೆ ಮಾಡಿ ಮತ್ತು ಹಂತದ ಯೋಜನೆ ಆರಿಸುವ ಮೊದಲು ಗಮನಿಸುವಿಕೆಯ ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಿ. ಖಚಿತವಿಲ್ಲ ಎಂದರೆ ಹಾನಿ ಇಲ್ಲ ಎಂದಲ್ಲ. ರೋಗ ದೃಢಪಟ್ಟರೆ ಇರುವ ಆಯ್ಕೆಯನ್ನು ಚಿಕಿತ್ಸೆಯ ಸಾರಾಂಶ ವಿವರಿಸುತ್ತದೆ; ಅದು ರೋಗವನ್ನು ದೃಢಪಡಿಸುವುದಿಲ್ಲ. ಗಿಡಗಳು ಬಾಡುತ್ತಿದ್ದರೆ, ಸಾಯುತ್ತಿದ್ದರೆ ಅಥವಾ ಲಕ್ಷಣ ವೇಗವಾಗಿ ಹರಡುತ್ತಿದ್ದರೆ ಈಗಲೇ ಸ್ಥಳೀಯ ಕೃಷಿ ಸಲಹೆ ಪಡೆಯಿರಿ. ತಡವಾದ ಅಂಗಮಾರಿ ಶಂಕೆಗೆ ಇಂದೇ ಸಲಹೆ ಬೇಕು.',
    },
    'hi': {
        'mild': 'आपने हल्का नुकसान बताया है। इस देखभाल योजना में हल्के नुकसान वाले कदम अपनाएँ, आसपास के पौधों की जाँच करें और उसी पत्ते की तारीख वाली तस्वीर रखें। प्रबंधन से फायदा होने पर भी पुराने धब्बे रह सकते हैं। देखें कि नए धब्बे कम हो रहे हैं और नई बढ़वार स्वस्थ है या नहीं। बताए गए समय पर फिर जाँचें। नुकसान फैले, पौधे मुरझाएँ या तने और फल प्रभावित हों तो पहले सलाह लें। पछेती झुलसा की आशंका में हल्के नुकसान पर भी आज ही सलाह चाहिए।',
        'moderate': 'आपने मध्यम नुकसान बताया है। मध्यम अवस्था वाले कदम शुरू करें, कई पौधों की तुलना करें और नए लक्षणों का तारीख वाला रिकॉर्ड रखें। प्रबंधन स्वस्थ हिस्सों को बचाता है; पुराने मृत धब्बे फिर हरे नहीं होंगे। केवल इस फसल और समस्या के लिए पंजीकृत उत्पाद लें और ऐप से मात्रा चुनने के बजाय लेबल मानें। सुधार के संकेत जाँचें और लक्षण फैलते रहें तो कृषि सलाहकार से संपर्क करें।',
        'severe': 'आपने गंभीर लक्षण बताए हैं। गंभीर अवस्था वाले कदम अपनाएँ और जल्द फसल की सलाह लें। पौधे मुरझा रहे हों, मर रहे हों या कई पौधों में लक्षण तेजी से फैल रहे हों तो अभी विशेषज्ञ चाहिए। पुरानी खराब पत्तियों के ठीक होने का इंतजार न करें। बचे स्वस्थ पौधों को बचाएँ और नए लक्षण दर्ज करें। सुधार जल्दी लाने के लिए छिड़काव तेज न करें और उत्पाद न मिलाएँ। मदद मिलने तक क्या देखना है, योजना में बताया गया है।',
        'unknown': 'नुकसान का स्तर तय करने के लिए जानकारी पर्याप्त नहीं है। पुष्टि वाली जाँच करें और अवस्था चुनने से पहले निरीक्षण के प्रश्नों के उत्तर दें। पता नहीं का मतलब नुकसान नहीं है, ऐसा नहीं होता। उपचार का सार रोग की पुष्टि होने पर विकल्प समझाता है; वह निदान की पुष्टि नहीं करता। पौधे मुरझा रहे हों, मर रहे हों या लक्षण तेजी से फैल रहे हों तो अभी स्थानीय कृषि सलाह लें। पछेती झुलसा की आशंका में आज सलाह चाहिए।',
    },
}


def spoken_text(text: str, language: str) -> str:
    """Preserve numbers that Indic-TTS otherwise silently drops from Kannada."""
    text = unicodedata.normalize('NFC', text)
    if language == 'kn':
        text = re.sub(r'24\s*[–-]\s*48', 'ಇಪ್ಪತ್ತನಾಲ್ಕರಿಂದ ನಲವತ್ತೆಂಟು', text)
        words = {'24': 'ಇಪ್ಪತ್ತನಾಲ್ಕು', '48': 'ನಲವತ್ತೆಂಟು'}
        def number(match):
            if match.group() not in words:
                raise ValueError('Unmapped Kannada speech number: ' + match.group())
            return words[match.group()]
        text = re.sub(r'\d+', number, text)
        text = text.replace('/', ' ಅಥವಾ ')
    return text


def scripts_for(protocols: dict, fixed_only: bool = False) -> dict[str, str]:
    scripts = {}
    for lang in LANGUAGES:
        for level, text in STAGES[lang].items():
            scripts[f'audio/{lang}/treatment_stage_{level}.ogg'] = spoken_text(PRIORITY_PREFIX[lang] + ' ' + text, lang)
        if fixed_only:
            continue
        for condition, item in sorted(protocols['protocols'].items()):
            text = item['translations'][lang]['audio_summary']
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f'Missing treatment summary: {condition}/{lang}')
            scripts[f'audio/{lang}/treatment_{condition}.ogg'] = spoken_text(text, lang)
    return scripts


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
    cached_rows = {row['path']: row for row in previous.get('clips', [])}
    rows = []
    for key, text in scripts.items():
        if not key.startswith(f'audio/{args.language}/'):
            continue
        target = args.output / key
        target.parent.mkdir(parents=True, exist_ok=True)
        cached = cached_rows.get(key)
        if cached and cached.get('text') == text and target.is_file() and sha256(target) == cached['sha256']:
            rows.append(cached)
            continue
        audio = engine.generate(text, sid=0, speed=.94)
        samples = np.asarray(audio.samples, dtype=np.float32)
        if samples.size < audio.sample_rate / 2 or not np.isfinite(samples).all():
            raise ValueError(f'Invalid neural synthesis: {key}')
        raw_peak = float(np.max(np.abs(samples)))
        if raw_peak < .01:
            raise ValueError(f'Silent neural synthesis: {key}')
        # Avoid clipping float synthesis when writing intermediate PCM16.
        if raw_peak > .98:
            samples = samples * (.98 / raw_peak)
        with tempfile.TemporaryDirectory(prefix='crop-treatment-voice-') as temp:
            wav = Path(temp) / 'speech.wav'
            sf.write(wav, samples, audio.sample_rate, subtype='PCM_16')
            normalize_and_encode(wav, target, '64k')
            # Lossy-codec reconstruction can exceed the normalization true peak.
            # Add headroom after encoding and check the decoded samples again.
            for attempt in range(3):
                decoded, rate = sf.read(target, dtype='float32')
                if rate != 24000 or decoded.ndim != 1 or not np.isfinite(decoded).all():
                    raise ValueError(f'Invalid encoded narration: {key}')
                peak = float(np.max(np.abs(decoded)))
                if .01 < peak <= .98:
                    break
                if peak <= .01:
                    raise ValueError(f'Silent encoded narration: {key}')
                adjusted = Path(temp) / f'headroom-{attempt}.ogg'
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(target),
                    '-af', f'volume={.9 / peak:.10f}', '-ar', '24000', '-ac', '1',
                    '-c:a', 'libvorbis', '-b:a', '64k', str(adjusted)], check=True)
                shutil.copy2(adjusted, target)
            decoded, rate = sf.read(target, dtype='float32')
            peak = float(np.max(np.abs(decoded)))
            if not .01 < peak <= .98:
                raise ValueError(f'Encoded narration has insufficient headroom: {key}')
        rows.append({'path': key, 'text': text, 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                     'sha256': sha256(target), 'duration_seconds': len(decoded) / rate,
                     'bytes': target.stat().st_size, 'sample_rate': rate, 'channels': 1,
                     'raw_synthesis_peak': raw_peak, 'decoded_peak': peak})
        print(json.dumps({'generated': key, 'duration_seconds': rows[-1]['duration_seconds'],
                          'decoded_peak': peak}), flush=True)
    receipt = {'schema_version': 1, 'model_version': model['model_version'], 'voice': voice['name'],
               'source': voice['source'], 'license': voice['license'], 'model_sha256': voice['model_sha256'],
               'engine': f'sherpa-onnx {sherpa_onnx.__version__}; Piper/VITS',
               'normalization': 'PCM16 headroom; two-pass -18 LUFS/-1.5 dBTP; decoded Vorbis peak guard',
               'review': 'technical_decode_checked; pronunciation_and_agronomy_not_expert_reviewed', 'clips': rows}
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')


def generate_kannada(args, scripts: dict[str, str], version: str) -> None:
    checkpoint = args.checkpoint_root / 'kn'
    if not checkpoint.exists():
        checkpoint = args.checkpoint_root
    for filename, expected in KANNADA_CHECKPOINTS.items():
        if sha256(checkpoint / filename) != expected:
            raise ValueError(f'Pinned Kannada checkpoint differs: {filename}')
    characters = json.loads((checkpoint / 'fastpitch/config.json').read_text())['characters']
    vocabulary = set(characters['characters'] + characters['punctuations'])
    for key, text in scripts.items():
        if key.startswith('audio/kn/') and set(text) - vocabulary:
            raise ValueError(f'Unsupported Kannada speech characters in {key}: {sorted(set(text) - vocabulary)!r}')
    receipt_path = args.output / 'provenance-kn.json'
    previous = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
    old_rows = {row['path']: row for row in previous.get('clips', [])}
    retained = {key: row for key, row in old_rows.items() if key in scripts and row.get('text') == scripts[key]
                and (args.output / key).is_file() and sha256(args.output / key) == row['sha256']}
    remaining = {key: text for key, text in scripts.items() if key.startswith('audio/kn/') and key not in retained}
    if not remaining:
        return
    script_path = args.output / 'treatment_scripts.json'
    script_path.write_text(json.dumps({'script_version': version, 'scripts': remaining}, ensure_ascii=False, indent=2) + '\n')
    command = [sys.executable, str(ROOT / 'content/generate_indic_voice.py'), '--checkpoint-root', str(args.checkpoint_root),
               '--scripts', str(script_path), '--output', str(args.output / 'kn-stage'), '--threads', str(args.threads)]
    if args.python_packages:
        command += ['--python-packages', str(args.python_packages)]
    subprocess.run(command, check=True)
    stage = args.output / 'kn-stage'
    shutil.copytree(stage / 'audio/kn', args.output / 'audio/kn', dirs_exist_ok=True)
    receipt = json.loads((stage / 'provenance.json').read_text())
    receipt['clips'] = [*retained.values(), *receipt['clips']]
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')


def install(args, model: dict, scripts: dict[str, str]) -> None:
    import numpy as np
    import soundfile as sf

    rows, voices = [], {}
    for lang in LANGUAGES:
        receipt = json.loads((args.install_from / f'provenance-{lang}.json').read_text())
        if receipt.get('model_version', receipt.get('script_version')) != model['version']:
            raise ValueError(f'Treatment narration version differs for {lang}')
        voices[lang] = {key: value for key, value in receipt.items() if key != 'clips'}
        for row in receipt['clips']:
            key = row['path']
            if not key.startswith(f'audio/{lang}/treatment_') or key not in scripts or row.get('text') != scripts[key]:
                raise ValueError(f'Unexpected treatment narration/script: {key}')
            if sha256(args.install_from / key) != row['sha256']:
                raise ValueError(f'Treatment audio checksum differs: {key}')
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(args.install_from / key), '-f', 'null', '-'], check=True)
            decoded, rate = sf.read(args.install_from / key, dtype='float32')
            if rate != 24000 or decoded.ndim != 1 or not len(decoded) or not np.isfinite(decoded).all():
                raise ValueError(f'Invalid treatment audio format/samples: {key}')
            peak = float(np.max(np.abs(decoded)))
            if not .01 < peak <= 1:
                raise ValueError(f'Treatment audio is silent or exceeds full-scale peak: {key}')
            condition = Path(key).stem.removeprefix('treatment_')
            original = model['protocols'].get(condition, {}).get('translations', {}).get(lang, {}).get('audio_summary', scripts[key])
            rows.append({**row, 'language': lang, 'decoded_peak': peak,
                         'source_text_sha256': hashlib.sha256(original.encode()).hexdigest(),
                         'text_sha256': hashlib.sha256(scripts[key].encode()).hexdigest()})
    if len(rows) != 63 or {row['path'] for row in rows} != set(scripts):
        raise ValueError('Expected every one of 63 treatment narration clips exactly once')
    assets = ROOT / 'android/app/src/main/assets'
    for row in rows:
        target = assets / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.install_from / row['path'], target)
    manifest = {'schema_version': 1, 'version': model['version'], 'care_protocols_sha256': sha256(args.protocols),
                'generator_sha256': sha256(Path(__file__)),
                'runtime_network_required': False, 'speech_weights_packaged': False,
                'voices': voices, 'text_normalization': 'NFC; Kannada Arabic 24/48 time numerals and ranges spoken as Kannada words; slash spoken as ಅಥವಾ',
                'review': 'technical_decode_only; native_listening_and_agronomy_review_pending',
                'total_clips': len(rows), 'total_bytes': sum(row['bytes'] for row in rows), 'clips': rows}
    (assets / 'content/treatment_audio_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'installed': len(rows), 'bytes': manifest['total_bytes']}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocols', type=Path, default=ROOT / 'content/care_protocols.json')
    parser.add_argument('--language', choices=LANGUAGES)
    parser.add_argument('--model-dir', type=Path)
    parser.add_argument('--checkpoint-root', type=Path)
    parser.add_argument('--python-packages', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--install-from', type=Path)
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--fixed-only', action='store_true')
    args = parser.parse_args()
    model = {'version': 'care-protocols-v2', 'protocols': {}} if args.fixed_only else json.loads(args.protocols.read_text())
    if not args.fixed_only:
        labels = json.loads((ROOT / 'contracts/labels.json').read_text())['labels']
        if set(model['protocols']) != {label['id'] for label in labels}:
            raise ValueError('Expected all 17 care categories before narration generation')
    scripts = scripts_for(model, args.fixed_only)
    if args.install_from:
        if args.fixed_only:
            parser.error('Partial treatment narration cannot be installed')
        install(args, model, scripts)
        return
    if not args.output or not args.language or not 1 <= args.threads <= 4:
        parser.error('--language, --output and 1–4 --threads are required')
    args.output = args.output.resolve()
    for forbidden in (ROOT / 'android/app/src/main/assets', ROOT / 'frontend/public', ROOT / 'frontend/dist'):
        if args.output == forbidden or forbidden in args.output.parents:
            parser.error('Generate into staging; only validated complete outputs may be installed')
    args.output.mkdir(parents=True, exist_ok=True)
    if args.language == 'kn':
        if not args.checkpoint_root:
            parser.error('--checkpoint-root required for Kannada')
        generate_kannada(args, scripts, model['version'])
    else:
        if not args.model_dir:
            parser.error('--model-dir required for Piper')
        generate_piper(args, scripts, {'model_version': model['version']})


if __name__ == '__main__':
    main()
