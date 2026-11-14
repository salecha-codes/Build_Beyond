#!/usr/bin/env python3
"""Generate fixed offline English speech with a pinned, build-time Piper/VITS model.

Model weights and the Python speech runtime are NOT app dependencies. Output is
staged separately; the integration script decides which reviewed clips to ship.

Dependencies: sherpa-onnx==1.12.40 soundfile==0.13.1 numpy==2.4.2 and ffmpeg.
Example:
  python content/generate_english_voice.py --model-dir /external/vits-piper-en_US-ljspeech-high \
    --output-dir /external/neural-en
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
VOICE_MODELS = {
    'ljspeech-high': {
        'name': 'Piper en_US-ljspeech-high',
        'file': 'en_US-ljspeech-high.onnx',
        'model_sha256': 'fea8faae21240174e972568a004f1d7afb01a93dbc7b3a58c36ecdc1bae82e33',
        'archive_sha256': '00c6408d2409050312193b0d40ae07fde28af7d3d45a56efcc55440db516b935',
        'source': 'https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-en_US-ljspeech-high.tar.bz2',
        'license': 'LJ Speech dataset: public domain, as stated in the packaged MODEL_CARD. No separate SPDX license for the converted model is stated in that card; weights are build-time only and are not packaged in the app.',
        'dataset_source': 'https://keithito.com/LJ-Speech-Dataset/',
    },
    'lessac-medium': {
        'name': 'Piper en_US-lessac-medium',
        'file': 'en_US-lessac-medium.onnx',
        'model_sha256': '4ba07d8549906668ee855fd9abf9faf66c5db74742712ff026a159f7277fca9f',
        'archive_sha256': '9e3febfacf0abf4270172d2958bcec246032b7e88efc2720840cc80c93de334e',
        'source': 'https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-en_US-lessac-medium.tar.bz2',
        'license': 'Packaged MODEL_CARD links the Lessac Blizzard2013 dataset license; no SPDX grant is stated. License URL could not be independently read in this environment.',
        'dataset_source': 'https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/',
        'dataset_license_url': 'https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html',
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def normalize_and_encode(source: Path, target: Path, bitrate: str) -> dict:
    """Two-pass loudness normalization, then standard mono OGG/Vorbis encoding."""
    measured = run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(source), '-af',
                    'loudnorm=I=-18:TP=-1.5:LRA=7:print_format=json', '-f', 'null', '-'])
    blocks = re.findall(r'\{\s*"input_i".*?\}', measured.stderr, re.S)
    if not blocks:
        raise RuntimeError('ffmpeg did not return loudness measurements')
    values = json.loads(blocks[-1])
    for field in ('input_i', 'input_tp', 'input_lra', 'input_thresh', 'target_offset'):
        if not math.isfinite(float(values[field])):
            raise RuntimeError(f'Invalid loudness measurement: {field}')
    filters = (f'loudnorm=I=-18:TP=-1.5:LRA=7:measured_I={values["input_i"]}'
               f':measured_TP={values["input_tp"]}:measured_LRA={values["input_lra"]}'
               f':measured_thresh={values["input_thresh"]}:offset={values["target_offset"]}'
               ':linear=true')
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
         '-af', filters, '-ar', '24000', '-ac', '1', '-c:a', 'libvorbis', '-b:a', bitrate, str(target)])
    # Decode the entire file; metadata alone does not prove the stream is valid.
    run(['ffmpeg', '-v', 'error', '-i', str(target), '-f', 'null', '-'])
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scripts', type=Path, default=ROOT / 'content/spoken_scripts.json')
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--voice', choices=tuple(VOICE_MODELS), default='ljspeech-high')
    parser.add_argument('--archive', type=Path, help='Optionally verify the downloaded release archive too')
    parser.add_argument('--output-dir', type=Path, required=True, help='Staging root; contains audio/en and provenance.json')
    parser.add_argument('--only', help='Generate one exact asset key or basename for sample review')
    parser.add_argument('--speed', type=float, default=0.92)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--bitrate', choices=('48k', '64k'), default='64k')
    args = parser.parse_args()
    if not .7 <= args.speed <= 1.2 or not 1 <= args.threads <= 8:
        parser.error('Choose a speed from 0.7 to 1.2 and 1 to 8 CPU threads')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        parser.error('ffmpeg and ffprobe must be installed')
    destination = args.output_dir.resolve()
    forbidden = [ROOT / 'android/app/src/main/assets', ROOT / 'frontend/public', ROOT / 'frontend/dist']
    if any(destination == item or item in destination.parents for item in forbidden):
        parser.error('Output must be staged outside packaged app assets')
    voice = VOICE_MODELS[args.voice]
    model = args.model_dir / voice['file']
    actual_hash = sha256(model)
    if actual_hash != voice['model_sha256']:
        raise RuntimeError(f'Model SHA-256 mismatch: {actual_hash}')
    if args.archive and sha256(args.archive) != voice['archive_sha256']:
        raise RuntimeError('Release archive SHA-256 mismatch')
    source = json.loads(args.scripts.read_text())
    scripts = {path: text for path, text in source['scripts'].items() if path.startswith('audio/en/')}
    if len(scripts) != 30:
        raise RuntimeError(f'Expected 30 English asset keys, got {len(scripts)}')
    if args.only:
        scripts = {key: value for key, value in scripts.items() if key == args.only or PurePosixPath(key).name == args.only}
        if len(scripts) != 1:
            raise RuntimeError('--only must select exactly one existing English asset')
    import numpy as np
    import sherpa_onnx
    import soundfile as sf

    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(model), tokens=str(args.model_dir / 'tokens.txt'),
                data_dir=str(args.model_dir / 'espeak-ng-data')),
            num_threads=args.threads, provider='cpu'),
        max_num_sentences=1)
    if not config.validate():
        raise RuntimeError('Invalid neural TTS configuration')
    engine = sherpa_onnx.OfflineTts(config)
    destination.mkdir(parents=True, exist_ok=True)
    card = args.model_dir / 'MODEL_CARD'
    if card.is_file():
        shutil.copyfile(card, destination / 'MODEL_CARD.txt')
    rows = []
    for asset_path, spoken_text in scripts.items():
        path = PurePosixPath(asset_path)
        if '..' in path.parts or path.is_absolute() or len(path.parts) != 3 or path.suffix != '.ogg':
            raise RuntimeError(f'Unsafe speech asset key: {asset_path}')
        target = destination / asset_path
        target.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        audio = engine.generate(spoken_text, sid=0, speed=args.speed)
        raw = np.asarray(audio.samples, dtype=np.float32)
        if len(raw) < audio.sample_rate / 2 or not np.isfinite(raw).all() or np.max(np.abs(raw)) < .01:
            raise RuntimeError(f'Empty, non-finite or silent synthesis: {asset_path}')
        with tempfile.TemporaryDirectory(prefix='crop-neural-en-') as temporary:
            wav = Path(temporary) / 'speech.wav'
            sf.write(wav, raw, audio.sample_rate, subtype='PCM_16')
            loudness = normalize_and_encode(wav, target, args.bitrate)
        decoded, decoded_rate = sf.read(target, dtype='float32')
        if decoded_rate != 24000 or decoded.ndim != 1 or not np.isfinite(decoded).all():
            raise RuntimeError(f'Invalid encoded audio: {asset_path}')
        peak = float(np.max(np.abs(decoded)))
        if peak < .01 or peak > 1.0:
            raise RuntimeError(f'Silent or clipped encoded speech: {asset_path}: {peak}')
        row = {
            'path': asset_path, 'language': 'en', 'duration_seconds': round(len(decoded) / decoded_rate, 3),
            'bytes': target.stat().st_size, 'sha256': sha256(target),
            'source_text_sha256': hashlib.sha256(spoken_text.encode('utf-8')).hexdigest(),
            'engine': f'sherpa-onnx {sherpa_onnx.__version__}; VITS/Piper neural TTS',
            'voice': voice['name'], 'model_sha256': actual_hash,
            'sample_rate': 24000, 'native_model_sample_rate': audio.sample_rate,
            'channels': 1, 'codec': 'vorbis', 'bitrate': args.bitrate,
            'speed': args.speed, 'target_loudness_lufs': -18, 'target_true_peak_dbfs': -1.5,
            'decoded_peak': round(peak, 5), 'input_loudness': loudness,
            'review': 'full_decode_and_finite_audio_checked;human_listening_review_pending',
        }
        rows.append(row)
        print(json.dumps({'path': asset_path, 'seconds': row['duration_seconds'], 'bytes': row['bytes'],
                          'generation_and_encoding_seconds': round(time.monotonic() - started, 2)}), flush=True)
    receipt = {
        'schema_version': 1, 'script_version': source['script_version'],
        'engine': f'sherpa-onnx {sherpa_onnx.__version__}; VITS/Piper neural TTS',
        'model': voice['name'], 'source': voice['source'], 'sha256': actual_hash,
        'archive_sha256': voice['archive_sha256'], 'license': voice['license'],
        'dataset_source': voice['dataset_source'],
        'dataset_license_url': voice.get('dataset_license_url', ''),
        'packaged_model_card': 'MODEL_CARD.txt', 'sample_rate': 24000, 'channels': 1,
        'codec': 'ogg/vorbis', 'bitrate': args.bitrate, 'speed': args.speed,
        'normalization': 'Two-pass ffmpeg loudnorm: -18 LUFS, -1.5 dBTP, LRA 7',
        'source_scripts_sha256': sha256(args.scripts),
        'runtime': 'Build-time speech generation only; no speech model or speech server is shipped in the app.',
        'review': 'technical_decode_only;human_listening_and_pronunciation_review_pending',
        'dependencies': {name: importlib.metadata.version(name) for name in ('sherpa-onnx', 'soundfile', 'numpy')},
        'total_clips': len(rows), 'total_bytes': sum(row['bytes'] for row in rows), 'clips': rows,
    }
    (destination / 'provenance.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'clips': len(rows), 'bytes': receipt['total_bytes'], 'receipt': str(destination / 'provenance.json')}))


if __name__ == '__main__':
    main()
