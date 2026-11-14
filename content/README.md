# Offline observation content and speech

The app packages its observation catalog and a separate **17-category offline advisory model**. Narration includes the original 90 observation clips plus 75 advisory clips: conditional care summaries, four urgency messages and four revised/new symptom questions in each language. Playback needs no network, downloaded language pack, API key or runtime speech model.

| Language | Build-time voice | Packaged output |
|---|---|---|
| Kannada | Official AI4Bharat Indic-TTS Kannada FastPitch + HiFiGAN, female preset | Mono 24 kHz OGG/Vorbis, 64 kbps target |
| English | Official Piper en_US-ljspeech-high VITS via sherpa-onnx | Mono 24 kHz OGG/Vorbis, 64 kbps target |
| Hindi | Official Piper hi_IN-pratham-medium VITS via sherpa-onnx | Mono 24 kHz OGG/Vorbis, 64 kbps target |

All generators run locally using publicly downloadable checkpoints. No paid speech API is used. Only the recordings are shipped; the large speech checkpoints remain outside the repository and app. Current audio totals **8,607,408 bytes**. FFmpeg applies two-pass loudness normalization to -18 LUFS with -1.5 dB true-peak target.

`build_offline_content.py` contains the editable screen/catalog copy: 17 condition entries, 13 general prompts and interface strings. `hindi.source.json` adds the Hindi guidance and scripts; `hindi_ui.json` supplies Hindi interface copy shared by Android and web. `spoken_scripts.json` contains concise spoken summaries for all 90 asset paths. Screen copy can be longer than narration. Model IDs match `contracts/labels.json`. The audio manifest records script version, engines, source/checkpoint hashes, normalized audio format, clip hashes, durations and mean-volume checks.

## Review status

The original catalog is general observation guidance. The new `advisory_model.json` adds disease-specific conditional care, curability, management, prevention and escalation in all three languages. Both remain **drafts requiring agronomist review**. No pesticide dose or application interval is supplied. PlantVillage is cited for taxonomy only, not management advice. Extension/government source retrieval was blocked by the environment proxy; no blocked source is represented as read or verified. Translations and neural pronunciation remain pending native-speaker review. Technical audio decoding does not validate translation, pronunciation or agricultural correctness.

The default model policy is unvalidated. It must not produce confirmed disease/crop assertions based on random or unvalidated output. Keep real model scores visible only as experimental evidence. Concern guidance uses farmer-reported signs, including approximate leaf-spot coverage; it does not measure photo severity.

## Advisory model and new speech

Run `python3 tools/build_advisory_bundle.py` after editing `advisory_model.json`
or either runtime decision implementation. It checks all 17 stable IDs, crop and
risk mappings, three-language profiles and honest validation flags, then packages
the model and a hash receipt. `npm run sync:assets` refuses stale knowledge assets.

`generate_advisory_voice.py` generates the new narration with the same cached,
pinned speech providers. Its separate `advisory_audio_manifest.json` binds every
clip to its text, model hash and provider provenance. A care clip speaks a short
conditional summary, not every bullet on the screen. Urgency and question clips
are separate; a fixed disease summary never invents a severity measurement.
Only audio files ship, not the speech-model weights. See the generator's `--help`
for staging and installation commands.

## Detailed treatment and recovery protocols

`care_protocols.json` adds all 17 conditions in all three languages with distinct
severity action paths, treatment use cases and ordered steps, identification
checks, look-alikes, recovery/failure signs and follow-up checkpoints. It is
separate from the original advisory artifact so its older recordings keep their
original source hashes. Run `python3 tools/build_care_protocols.py` after editing
protocols or their runtime selectors; stale source/package pairs fail web asset sync.

`generate_treatment_voice.py` adds 63 independent clips: 17 condition-specific
treatment overviews and four severity-stage summaries per language. The app
therefore packages 228 clips across the three manifests. Summaries explain the
main care and recovery steps; their labels do not claim to read every bullet.
The new manifest records both canonical summary hashes and actual spoken text,
including Kannada number normalization. Speech character validation, full
decoding and peak checks address dropped timing numerals and codec clipping.
These technical checks do not validate native pronunciation or treatment efficacy.

The care library is educational and explicitly selected by the user. It cannot
relabel an image prediction. [Source research](../docs/CARE_V2_RESEARCH.md) records
the limited retrieved secondary IPM data and blocked primary references. No
registered medicine dose or treatment-outcome accuracy is fabricated.

## Regenerate

The already-bundled assets do not need regeneration to build or run the app. Speech generation is an optional development task, separate from normal Android/web builds. Use separate Python environments for the providers, with FFmpeg on PATH.

Tested English dependencies: `sherpa-onnx==1.12.40`, `soundfile==0.13.1`, `numpy==2.4.2`. Download/extract the [official converted LJSpeech voice](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-en_US-ljspeech-high.tar.bz2) outside the checkout. The generator verifies its ONNX hash and optionally the archive hash:

```sh
python content/generate_english_voice.py --model-dir /external/vits-piper-en_US-ljspeech-high --output-dir /external/neural-en
```

Tested Kannada runtime: `coqui-tts==0.28.0` with CPU `torch==2.9.1`. Download/extract the [official Kannada checkpoint](https://github.com/AI4Bharat/Indic-TTS/releases/download/v1-checkpoints-release/kn.zip) outside the checkout. Its root contains `kn/fastpitch` and `kn/hifigan`. Training-machine speaker paths are adapted in a staging config; checkpoint tensors remain unchanged:

```sh
python content/generate_indic_voice.py --checkpoint-root /external/checkpoints --output /external/neural-kn --archive /external/kn.zip
```

Hindi uses the same sherpa-onnx Python environment as English. Download/extract the [official converted Pratham voice](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-hi_IN-pratham-medium.tar.bz2), then generate its 30 clips and install all three providers together:

```sh
python content/generate_hindi_voice.py --help
python content/install_neural_audio.py --english-root /external/neural-en --kannada-root /external/neural-kn --hindi-root /external/neural-hi
```

`install_neural_audio.py` validates all 90 referenced paths, generation-receipt text hashes, full audio decoding, duration, volume and provenance before installing the new clips and manifest. `--dry-run` validates without installation. Runtime `ContentCatalog` reads the JSON locally; `Guidance.audioAsset` and `Prompt.audioAsset` keep the same relative Android asset paths.

`build_offline_content.py` preserves current audio by default. To reproduce the former robotic voice explicitly, use `--legacy-espeak` and the pinned `requirements-audio.txt`; normal development should retain the current neural recordings.

## Sources and provenance

- AI4Bharat [Indic-TTS](https://github.com/AI4Bharat/Indic-TTS) publishes the Kannada checkpoint and inference instructions. Repository code is MIT; the downloaded checkpoint does not state separate model-specific license terms. Checkpoints are not redistributed in this repository or APK.
- The packaged Piper LJSpeech model card identifies its source dataset as public domain. It does not state a separate SPDX license for the converted model. The speech checkpoint is used only during development.
- The Piper Hindi Pratham model card identifies its dataset license as CC BY-NC-SA 4.0; its source and model/archive hashes are recorded in provenance. The Hindi checkpoint is also used only during development.
- Exact release URLs, checkpoint SHA-256 values and generator versions are retained in `android/app/src/main/assets/content/audio_manifest.json`. The original narration scripts are in `spoken_scripts.json`.

MediaPlayer should load the asset using `AssetManager.openFd` and close the descriptor after setting its range. Release previous MediaPlayers when switching clips/screens. OGG assets are generated recordings of text, not live expert responses.
