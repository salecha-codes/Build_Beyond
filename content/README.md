# Offline observation content and speech

The app packages `assets/content/catalog.json` and 60 real OGG speech clips (English and Kannada). Playback needs no network, downloaded language pack or runtime speech model. eSpeak NG synthesized the clips during development, via the checksum-verified `espeakng-loader 0.2.4` Linux x86_64 wheel; FFmpeg encoded OGG/Vorbis. This tool is not bundled in the APK, only its generated audio is.

`build_offline_content.py` contains the editable, versioned source copy. It generates 17 condition entries, 13 general prompts, interface strings, bilingual content and audio hashes/durations. Model IDs match `contracts/labels.json`.

## Review status

The text is **general observation guidance**, not expert-reviewed treatment. No chemical product, pesticide dose or application interval is supplied. PlantVillage is cited for taxonomy only, not management advice. UC IPM/TNAU retrieval was blocked by the environment proxy; no primary advisory content was read or represented as reviewed. Kannada text and eSpeak pronunciation are draft and not native-speaker-reviewed. Technical audio decoding does not validate translation, pronunciation or agricultural correctness.

The default model policy is unvalidated. It must not produce confirmed disease/crop assertions based on random or unvalidated output. Keep real model scores visible only as experimental evidence. Concern guidance uses farmer-reported signs, including approximate leaf-spot coverage; it does not measure photo severity.

## Regenerate

The already-bundled assets do not need regeneration to build or run the app. For Linux x86_64 development:

```sh
python3 -m pip install --require-hashes --target /workspace/audio-tools/python -r content/requirements-audio.txt
python3 content/build_offline_content.py --audio-python-path /workspace/audio-tools/python
python3 content/test_content.py
```

FFmpeg must be on PATH. `--skip-audio` regenerates text only; do not ship a stale audio manifest against changed text. The manifest includes each audio file SHA-256 and source-text SHA-256. Runtime `ContentCatalog` reads the JSON locally; `Guidance.audioAsset` and `Prompt.audioAsset` are relative Android asset paths.

MediaPlayer should load the asset using `AssetManager.openFd` and close the descriptor after setting its range. Release previous MediaPlayers when switching clips/screens. OGG assets are generated recordings of text, not live expert responses.
