#!/usr/bin/env python3
"""Validate and install generated speech without putting a TTS model in the app."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "android/app/src/main/assets"


def probe(path: pathlib.Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,sample_rate,channels",
         "-of", "json", str(path)], capture_output=True, text=True, check=True,
    )
    details = json.loads(result.stdout)
    streams = details["streams"]
    if len(streams) != 1 or streams[0]["codec_name"] != "vorbis" or streams[0]["channels"] != 1:
        raise ValueError(f"Expected one mono Vorbis audio stream: {path.name}")
    duration = float(details["format"]["duration"])
    if not 1.0 < duration < 45.0:
        raise ValueError(f"Unexpected speech duration: {path.name}: {duration}")
    decoded = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                             capture_output=True, text=True, check=True)
    match = re.search(r"mean_volume:\s*(-?[0-9.]+|-inf) dB", decoded.stderr)
    if not match or float(match.group(1)) < -55:
        raise ValueError(f"Generated speech is silent or unexpectedly quiet: {path.name}")
    return {"duration_seconds": round(duration, 3), "sample_rate": int(streams[0]["sample_rate"]),
            "channels": 1, "mean_volume_dbfs": float(match.group(1))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--english-root", type=pathlib.Path, required=True)
    parser.add_argument("--kannada-root", type=pathlib.Path, required=True)
    parser.add_argument("--scripts", type=pathlib.Path, default=ROOT / "content/spoken_scripts.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    scripts = json.loads(args.scripts.read_text())
    catalog = json.loads((ASSETS / "content/catalog.json").read_text())
    old_manifest = json.loads((ASSETS / "content/audio_manifest.json").read_text())
    expected = {clip["path"] for clip in old_manifest["clips"]}
    if len(expected) != 60 or set(scripts["scripts"]) != expected:
        raise ValueError("Spoken scripts must cover exactly the existing 60 asset paths.")
    roots = {"en": args.english_root.resolve(), "kn": args.kannada_root.resolve()}
    provenance = {language: json.loads((folder / "provenance.json").read_text()) for language, folder in roots.items()}
    clips = []
    sources = {}
    for asset, text in sorted(scripts["scripts"].items()):
        relative = pathlib.PurePosixPath(asset)
        if len(relative.parts) != 3 or relative.parts[0] != "audio" or relative.parts[1] not in roots or relative.suffix != ".ogg":
            raise ValueError(f"Unsupported audio asset path: {asset}")
        language = relative.parts[1]
        source = roots[language].joinpath(*relative.parts)
        details = probe(source)
        data = source.read_bytes()
        if len(data) < 1000:
            raise ValueError(f"Speech asset is unexpectedly small: {asset}")
        engine = provenance[language].get("engine") or provenance[language].get("model")
        if not isinstance(engine, str) or not engine:
            raise ValueError(f"Missing voice engine provenance: {language}")
        clips.append({"path": asset, "language": language, **details, "bytes": len(data),
                      "sha256": hashlib.sha256(data).hexdigest(),
                      "source_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                      "engine": engine, "review": "technical_decode_checked;native_pronunciation_review_pending"})
        sources[asset] = source
    manifest = {"schema_version": 1, "content_version": catalog["content_version"],
                "voice_version": scripts["script_version"], "speech_mode": "bundled_neural_recordings",
                "runtime_tts_model_bundled": False, "runtime_api_required": False,
                "scripts_file": "content/spoken_scripts.json", "voice_provenance": provenance, "clips": clips}
    if not args.dry_run:
        for asset, source in sources.items():
            target = ASSETS / asset
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        target = ASSETS / "content/audio_manifest.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(target)
    print(json.dumps({"installed": not args.dry_run, "clips": len(clips), "audio_bytes": sum(c["bytes"] for c in clips),
                      "voice_version": manifest["voice_version"], "runtime_api_required": False}))


if __name__ == "__main__":
    main()
