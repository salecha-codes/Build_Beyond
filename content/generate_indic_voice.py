#!/usr/bin/env python3
"""Generate fixed Kannada clips locally with official AI4Bharat Indic-TTS weights.

No service key or runtime network request is needed. Keep downloaded checkpoints
outside the repository. The script writes to a separate staging directory, so an
operator can listen before replacing packaged audio. See --help for paths.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unicodedata

from generate_english_voice import normalize_and_encode

MODEL_SOURCE = "https://github.com/AI4Bharat/Indic-TTS/releases/download/v1-checkpoints-release/kn.zip"
PROJECT_SOURCE = "https://github.com/AI4Bharat/Indic-TTS"
ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-root", type=Path, required=True, help="Directory containing kn/fastpitch and kn/hifigan")
    parser.add_argument("--scripts", type=Path, default=ROOT / "content/spoken_scripts.json")
    parser.add_argument("--output", type=Path, required=True, help="Staging root; paths audio/kn/*.ogg are created below it")
    parser.add_argument("--python-packages", type=Path, help="Optional isolated packages directory added to sys.path")
    parser.add_argument("--archive", type=Path, help="Optional original kn.zip, recorded by SHA-256")
    parser.add_argument("--speaker", choices=["male", "female"], default="female")
    parser.add_argument("--only", help="Generate one asset basename first, e.g. prompt_uncertain")
    parser.add_argument("--threads", type=int, default=3)
    args = parser.parse_args()
    if args.python_packages:
        sys.path.insert(0, str(args.python_packages.resolve()))
    os.environ.setdefault("MPLCONFIGDIR", str(args.output / ".matplotlib"))
    os.environ.setdefault("NUMBA_CACHE_DIR", str(args.output / ".numba"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    import numpy as np
    import soundfile as sf
    import torch
    from TTS.utils.synthesizer import Synthesizer

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.manual_seed(2026)
    raw = json.loads(args.scripts.read_text())
    scripts = {key: value for key, value in raw["scripts"].items() if key.startswith("audio/kn/")}
    if args.only:
        scripts = {key: value for key, value in scripts.items() if Path(key).stem == args.only}
    if not scripts:
        raise ValueError("No matching Kannada scripts were found")
    for key, text in scripts.items():
        if Path(key).is_absolute() or ".." in Path(key).parts or not key.endswith(".ogg"):
            raise ValueError("Unsafe audio asset path")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Empty spoken text")
    checkpoint = args.checkpoint_root / "kn"
    if not checkpoint.exists() and (args.checkpoint_root / "fastpitch").exists():
        checkpoint = args.checkpoint_root
    files = {
        "tts": checkpoint / "fastpitch/best_model.pth",
        "tts_config": checkpoint / "fastpitch/config.json",
        "speakers": checkpoint / "fastpitch/speakers.pth",
        "vocoder": checkpoint / "hifigan/best_model.pth",
        "vocoder_config": checkpoint / "hifigan/config.json",
    }
    for path in files.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    # Official2023 configs contain training-machine-relative speaker paths.
    # Adapt only paths in a staging copy; checkpoint tensors remain untouched.
    config = json.loads(files["tts_config"].read_text())
    config["speakers_file"] = str(files["speakers"].resolve())
    if isinstance(config.get("model_args"), dict):
        config["model_args"]["speakers_file"] = str(files["speakers"].resolve())
    runtime_config = args.output / "runtime_fastpitch_config.json"
    runtime_config.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    synthesizer = Synthesizer(
        tts_checkpoint=str(files["tts"]), tts_config_path=str(runtime_config),
        tts_speakers_file=str(files["speakers"]), vocoder_checkpoint=str(files["vocoder"]),
        vocoder_config=str(files["vocoder_config"]), use_cuda=False,
    )
    sample_rate = synthesizer.output_sample_rate
    receipts = []
    # Give the caller an immediately playable uncertainty sample first.
    ordered = sorted(scripts, key=lambda key: (Path(key).stem != "prompt_uncertain", key))
    for key in ordered:
        text = unicodedata.normalize("NFC", scripts[key]).strip()
        # Native Kannada text needs no transliteration service. Split punctuation
        # locally to keep neural attention/length bounds short and predictable.
        sentences = [part.strip() for part in re.split(r"(?<=[.!?।])\s+", text) if part.strip()]
        chunks = []
        clip_started = time.monotonic()
        for sentence in sentences:
            audio = np.asarray(synthesizer.tts(sentence, speaker_name=args.speaker, split_sentences=False), dtype=np.float32)
            if not audio.size or not np.isfinite(audio).all():
                raise ValueError(f"Neural synthesis returned invalid audio for {key}")
            chunks.extend([audio, np.zeros(round(sample_rate * .22), dtype=np.float32)])
        audio = np.concatenate(chunks[:-1])
        peak = float(np.max(np.abs(audio)))
        if peak <= 0:
            raise ValueError(f"Neural synthesis returned silent audio for {key}")
        if peak > .97:
            audio *= .97 / peak
        target = args.output / key
        target.parent.mkdir(parents=True, exist_ok=True)
        wav = target.with_suffix(".wav")
        sf.write(wav, audio, sample_rate, subtype="PCM_16")
        loudness = normalize_and_encode(wav, target, "64k")
        # Decode the actual compressed result, not just its temporary source WAV.
        decoded, actual_rate = sf.read(target, dtype="float32")
        if decoded.size == 0 or not np.isfinite(decoded).all() or actual_rate != 24000:
            raise ValueError(f"Encoded neural clip failed decode checks: {key}")
        receipts.append({"path": key, "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                         "sha256": sha256(target), "bytes": target.stat().st_size,
                         "duration_seconds": len(decoded) / actual_rate, "sample_rate": actual_rate,
                         "native_model_sample_rate": sample_rate, "channels": 1, "bitrate": "64k",
                         "input_loudness": loudness,
                         "generation_seconds": time.monotonic() - clip_started})
        print(json.dumps({"generated": key, "duration_seconds": len(decoded) / actual_rate,
                          "elapsed_seconds": time.monotonic() - started}), flush=True)
    receipt = {
        "schema_version": 1, "engine": "AI4Bharat Indic-TTS / FastPitch + HiFiGAN",
        "runtime": {"coqui-tts": importlib.metadata.version("coqui-tts"), "torch": torch.__version__, "threads": args.threads},
        "model": "official kn Kannada, " + args.speaker + " speaker", "source": MODEL_SOURCE,
        "project_source": PROJECT_SOURCE, "license": "specific_checkpoint_license_not_declared",
        "code_license": "MIT; Copyright (c) 2023 AI4Bharat", "sample_rate": 24000,
        "native_model_sample_rate": sample_rate, "channels": 1, "bitrate": "64k",
        "normalization": "Two-pass ffmpeg loudnorm: -18 LUFS, -1.5 dBTP, LRA 7",
        "voice_kind": "neural", "generation_mode": "local_cpu_build_time", "runtime_network_required": False,
        "script_version": raw.get("script_version"), "script_sha256": sha256(args.scripts),
        "review_status": {"native_pronunciation": "pending_listening_review", "agronomy": "not_expert_reviewed"},
        "checkpoint_hashes": {key: sha256(path) for key, path in files.items()},
        "clips": receipts, "elapsed_seconds": time.monotonic() - started,
    }
    if args.archive:
        receipt["archive_sha256"] = sha256(args.archive)
        receipt["archive_bytes"] = args.archive.stat().st_size
    receipt_path = args.output / ("provenance.sample.json" if args.only else "provenance.json")
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"receipt": str(receipt_path), "clips": len(receipts)}), flush=True)


if __name__ == "__main__":
    main()
