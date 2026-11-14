#!/usr/bin/env python3
"""Generate bundled Hindi narration with a pinned build-time Piper/VITS voice.

The speech model stays outside the repository and phone app. Existing asset keys
are staged under audio/hi for later installation by the parent integration tool.
Dependencies: sherpa-onnx==1.12.40, soundfile==0.13.1, numpy==2.4.2 and FFmpeg.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import time
import unicodedata

from generate_english_voice import normalize_and_encode, sha256

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-hi_IN-pratham-medium.tar.bz2"
ARCHIVE_SHA256 = "2084d321e1d2752f2b64ed3012ba27751df01a80da46f52920098cdcb7e35648"
MODEL_SHA256 = "1d77908e8ab724c813c5cefaa48feadc9f2670ec5d145f83bade981c428740a0"
VOICE = "Piper hi_IN-pratham-medium"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scripts", type=Path, default=ROOT / "content/spoken_scripts.json")
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--only", help="Select one existing basename for sample listening")
    parser.add_argument("--speed", type=float, default=0.94)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if not 0.7 <= args.speed <= 1.2 or not 1 <= args.threads <= 8:
        parser.error("Choose speed 0.7–1.2 and 1–8 threads")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        parser.error("FFmpeg and ffprobe must be installed")
    destination = args.output_dir.resolve()
    forbidden = [ROOT / "android/app/src/main/assets", ROOT / "frontend/public", ROOT / "frontend/dist"]
    if any(destination == folder or folder in destination.parents for folder in forbidden):
        parser.error("Generate into a staging directory outside packaged app assets")
    model = args.model_dir / "hi_IN-pratham-medium.onnx"
    if sha256(model) != MODEL_SHA256:
        raise RuntimeError("Hindi voice ONNX checksum mismatch")
    if args.archive and sha256(args.archive) != ARCHIVE_SHA256:
        raise RuntimeError("Hindi voice release archive checksum mismatch")
    source = json.loads(args.scripts.read_text())
    scripts = {key: text for key, text in source["scripts"].items() if key.startswith("audio/hi/")}
    if args.only:
        scripts = {key: text for key, text in scripts.items() if PurePosixPath(key).stem == args.only or PurePosixPath(key).name == args.only}
        if len(scripts) != 1:
            raise RuntimeError("--only must select exactly one Hindi asset")
    elif len(scripts) != 30:
        raise RuntimeError(f"Expected 30 Hindi narration scripts, found {len(scripts)}")
    for key, text in scripts.items():
        path = PurePosixPath(key)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 3 or path.suffix != ".ogg":
            raise RuntimeError(f"Unsafe Hindi audio key: {key}")
        if not isinstance(text, str) or not text.strip() or not any("\u0900" <= char <= "\u097f" for char in text):
            raise RuntimeError(f"Missing Devanagari Hindi text: {key}")

    import hashlib
    import numpy as np
    import sherpa_onnx
    import soundfile as sf

    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(model), tokens=str(args.model_dir / "tokens.txt"),
                data_dir=str(args.model_dir / "espeak-ng-data")),
            num_threads=args.threads, provider="cpu"),
        max_num_sentences=1,
    )
    if not config.validate():
        raise RuntimeError("Invalid Hindi neural voice configuration")
    engine = sherpa_onnx.OfflineTts(config)
    destination.mkdir(parents=True, exist_ok=True)
    card = args.model_dir / "MODEL_CARD"
    if card.is_file():
        shutil.copyfile(card, destination / "MODEL_CARD.txt")
    rows = []
    for key in sorted(scripts, key=lambda value: (PurePosixPath(value).stem != "prompt_uncertain", value)):
        text = scripts[key]
        synthesis_text = unicodedata.normalize("NFC", text).strip()
        target = destination / key
        target.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        audio = engine.generate(synthesis_text, sid=0, speed=args.speed)
        raw = np.asarray(audio.samples, dtype=np.float32)
        if len(raw) < audio.sample_rate / 2 or not np.isfinite(raw).all() or np.max(np.abs(raw)) < 0.01:
            raise RuntimeError(f"Silent or invalid Hindi speech: {key}")
        with tempfile.TemporaryDirectory(prefix="crop-neural-hi-") as temporary:
            wav = Path(temporary) / "speech.wav"
            sf.write(wav, raw, audio.sample_rate, subtype="PCM_16")
            loudness = normalize_and_encode(wav, target, "64k")
        decoded, sample_rate = sf.read(target, dtype="float32")
        if sample_rate != 24000 or decoded.ndim != 1 or not np.isfinite(decoded).all():
            raise RuntimeError(f"Invalid encoded Hindi audio: {key}")
        peak = float(np.max(np.abs(decoded)))
        if not 0.01 < peak <= 1.0:
            raise RuntimeError(f"Silent or clipped Hindi speech: {key}")
        rows.append({
            "path": key, "language": "hi", "duration_seconds": round(len(decoded) / sample_rate, 3),
            "bytes": target.stat().st_size, "sha256": sha256(target),
            "source_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "synthesis_text_sha256": hashlib.sha256(synthesis_text.encode()).hexdigest(),
            "engine": f"sherpa-onnx {sherpa_onnx.__version__}; VITS/Piper neural TTS",
            "voice": VOICE, "model_sha256": MODEL_SHA256, "sample_rate": sample_rate,
            "native_model_sample_rate": audio.sample_rate, "channels": 1, "codec": "vorbis", "bitrate": "64k",
            "speed": args.speed, "input_loudness": loudness, "decoded_peak": round(peak, 5),
            "review": "full_decode_and_finite_audio_checked;human_listening_review_pending",
        })
        print(json.dumps({"generated": key, "seconds": rows[-1]["duration_seconds"],
                          "generation_and_encoding_seconds": round(time.monotonic() - started, 2)}), flush=True)
    receipt = {
        "schema_version": 1, "script_version": source["script_version"],
        "engine": f"sherpa-onnx {sherpa_onnx.__version__}; VITS/Piper neural TTS",
        "model": VOICE, "language": "hi-IN", "speaker": "pratham", "source": SOURCE,
        "model_sha256": MODEL_SHA256, "archive_sha256": ARCHIVE_SHA256,
        "license": "Packaged model card identifies its dataset license as CC BY-NC-SA 4.0. It does not state separate converted-model SPDX terms. Checkpoint weights are build-time only and are not packaged in the app.",
        "dataset_source": "https://github.com/AI4Bharat/indicnlp_corpus",
        "dataset_license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "converted_model_source": "https://github.com/k2-fsa/sherpa-onnx",
        "trained_by": "https://github.com/PravalX", "packaged_model_card": "MODEL_CARD.txt",
        "sample_rate": 24000, "channels": 1, "codec": "ogg/vorbis", "bitrate": "64k", "speed": args.speed,
        "normalization": "Two-pass ffmpeg loudnorm: -18 LUFS, -1.5 dBTP, LRA 7",
        "source_scripts_sha256": sha256(args.scripts),
        "runtime": "Build-time speech generation only; no speech model or speech API runs in the app.",
        "runtime_api_required": False,
        "review": "technical_decode_only;human_listening_and_pronunciation_review_pending",
        "dependencies": {name: importlib.metadata.version(name) for name in ("sherpa-onnx", "soundfile", "numpy")},
        "total_clips": len(rows), "total_bytes": sum(row["bytes"] for row in rows), "clips": rows,
    }
    name = "provenance.sample.json" if args.only else "provenance.json"
    (destination / name).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"clips": len(rows), "bytes": receipt["total_bytes"], "receipt": str(destination / name)}), flush=True)


if __name__ == "__main__":
    main()
