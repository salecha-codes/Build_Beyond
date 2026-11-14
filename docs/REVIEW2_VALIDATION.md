# Review 2 validation evidence

## Final Android execution

The final corrected x86_64 APK and test APK were installed together. AndroidJUnitRunner reported **`OK (10 tests)` in 77.726 seconds**: six native integration methods and four Compose fixture-state smoke methods. Raw output: `/workspace/review2-final-instrumentation.log`; artifact-linked summary: `/workspace/review2-final-test-summary.json`.

| Native integration check | Result |
|---|---|
| Installed manifest declares CAMERA and omits INTERNET | Passed |
| Actual bundled MobileNetV4 loads, emits 17 finite scores/960-D embedding, and remains explicitly unvalidated | Passed |
| Unvalidated crop scores cannot assert the farmer chose the wrong crop | Passed |
| Bounded photo decoding applies EXIF rotation | Passed |
| Independent solid and textured Python tensor fixtures, every value within absolute 1e-5 | Passed; both max/mean/p99 errors zero across 150,528 values each |
| Room commits/reloads records; targeted deletion removes owned photos and preserves unrelated paths | Passed |

The four Compose tests cover Home/language action dispatch, uncertain-score wording, explicit symptom-answer gating, and empty History/Help navigation. Their input states are clearly marked test fixtures; they do not substitute for live ViewModel testing.

Final APK SHA-256: `73ff17e9944883f34abc0c5163a92f0407b78e673cadcf0738b2c1ee2a8be2c1` (44,510,819 bytes). Test APK SHA-256: `925c51473f471696d7a4f00a2f094ea848edc7e772487e867a23e902a90ff303`.

Bundled model SHA-256: `d157e7c8401319a700039de467caba6728b7bdbf35b4cdae1818757cf0ba7e3c`. Its APK bytes match metadata and export receipt. Model metadata and decision policy both remain unvalidated. Complete artifact evidence: `/workspace/review2-final-apk-evidence.json`.

## Actual app walkthrough

On the final APK, the system gallery picker imported the visibly named `REVIEW2-QA-real-leaf.jpg` pinned test photograph. The real ViewModel decoded it, executed V4, and displayed **Uncertain**, with actual unvalidated candidates healthy-looking leaf 41% and Septoria leaf spot 18%. Save scan created a local “Needs review” history entry; reopening it restored its photo and score while retaining uncertain wording. Screenshots:

- `/workspace/review2-final-real-result.png`
- `/workspace/review2-saved-history.png`
- `/workspace/review2-reopened-observation.png`

The QA entry was then deleted through its individual History delete control. Its owned image disappeared. The preceding unsaved QA import and public QA source photo were removed by exact known paths; no broad history/data wipe was performed. Final History is empty and `files/observations` contains no files. Evidence: `/workspace/review2-after-cleanup-history.png`, `/workspace/review2-photos-after-record-delete.txt`, `/workspace/review2-photos-after-cleanup.txt`.

The preceding UI-equivalent APK was also walked through all three explicit symptom questions, observation summary, Kannada guidance, and its offline audio button. Screenshots: `/workspace/review2-symptom-summary.png`, `/workspace/review2-guidance-kn.png`. Android created an actual application MediaPlayer in started state and decoded the bundled Vorbis asset with airplane mode on. The headless emulator used a NullSink because it lacked an audio output device; audible speaker output was **not** verified. Evidence: `/workspace/review2-offline-audio-player.txt`, `/workspace/review2-offline-audio-logcat.log`.

Actual Home/empty History/Help screenshots are `/workspace/review2-home.png`, `/workspace/review2-history.png`, and `/workspace/review2-help.png`. They contain real empty states rather than seeded diagnoses.

## Limits and resolved issue

This was AOSP 35 x86_64 software emulation, 3 GB RAM/two virtual CPU cores, without `/dev/kvm`; airplane mode was enabled, Bluetooth and animations disabled. The owned userdebug emulator used supported OS timeout multiplier 10. An earlier 1.5 GB/one-core attempt executed zero tests after Android timed out process startup; it was not counted as a pass or as six failed tests.

Final post-flow whole-app memory snapshot: **PSS 153,054 KB, RSS 280,808 KB**, `/workspace/review2-final-mainactivity-memory.txt`. This is one emulator snapshot, not peak memory or a 3–4 GB ARM-phone performance claim. Actual phone latency/RAM, camera behavior, audible Kannada, agricultural/translation review, and recognition quality remain unvalidated.

The first Skia tensor resize exposed a textured Python/native mismatch (normalized max 0.66526598, mean 0.03446083, p99 0.20915031). A Pillow-compatible separable bilinear helper fixed it; both golden fixtures now pass the strict same 1e-5 gate with zero error on the final APK. Historical evidence remains under `/workspace/review2-skia-*`. The two fixtures establish their tested preprocessing contract, not exhaustive image-decoder parity or model accuracy.

Fixture provenance and hashes are in `android/app/src/androidTest/assets/README.md`. Test images are not production history seeds and their source class is not used to assert model accuracy.
