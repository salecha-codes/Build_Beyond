# Review 2 demonstration

Install the ARM64 APK on a compatible Android phone. Use the 32-bit APK if required. The app opens directly to Home; no account, server, or model download is needed.

## Two-minute flow

1. Turn on airplane mode and open Crop Health. Point out the offline badge and English/Kannada/Hindi language choices.
2. Choose Tomato, Potato, or Maize. Tap **Scan a leaf**, allow camera access, then photograph one clearly lit leaf. The gallery button can import an existing leaf photo.
3. Tap **Check this leaf**. The app checks the photo (including leaf detection) and runs the bundled MobileNetV3-Large locally. Show its actual candidate scores, prototype prediction, or explicit uncertain result.
4. Tap **Observe symptoms (3 questions)**. Answer each question; show the observation summary and general guidance. Explain that concern comes from the farmer’s answers, separate from the model score.
5. Switch to Kannada or Hindi and play the question/summary/guidance audio. All 90 recordings are bundled in the APK and work without an installed speech language pack. Reopen the app to demonstrate the saved language preference.
6. Return to the result and tap **Save scan**. Open History and reopen the observation. Saved photos and records remain on this phone unless the user explicitly shares or deletes them.

## Explain the prototype accurately

“Our native Android prototype runs MobileNetV3-Large on the phone, keeps the image local, and provides trilingual Kannada, Hindi and English audio. The current model incorporates ImageNet-pretrained features and a trained 17-class disease head with leaf-guard rejection. We show its real scores while keeping diagnosis validation off. When the model is uncertain or the photo is unclear, the app asks for a better photo or expert review rather than giving a pesticide prescription.”

The app supports 17 label categories for three crops. Its model file is approximately 9.57 MiB. The phone APK is approximately 41 MiB. Report the exact APK size/checksum from the delivery manifest.

The prepared software emulator has verified runtime behavior. It does not establish 3–4 GB ARM-phone speed, field accuracy, diagnosis validity, or Kannada agricultural pronunciation quality. These remain the next validation steps.

## Before presenting

- Open the APK once and grant camera access before the demonstration.
- Use a real leaf or a clearly identified sample photograph; do not present a test fixture as a farmer’s case.
- Set media volume high enough to hear the offline audio.
- Demonstrate an uncertain result with its real scores. Screenshots of a confident mockup are design references, not measured accuracy.
- Keep any existing saved observations private; sharing is a deliberate user action.
