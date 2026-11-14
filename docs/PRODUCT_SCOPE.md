# Final product scope

## User and promise

A farmer with a **3–4 GB RAM Android phone** and intermittent connectivity can photograph a leaf, receive an assessment of a supported condition, and understand the next steps in text and audio. Processing and stored observations remain on the phone unless the user explicitly exports them. This hardware range is the required deployment target; actual compatibility and performance still require device testing.

The primary experience is designed for one leaf in a photo. It does not assess an entire field or estimate crop yield. The three selected crops are tomato, potato, and maize; the model taxonomy has 17 crop-condition outputs, as listed in the dataset audit. Healthy outputs mean no supported symptoms were identified in that photograph, not a guarantee that a plant is disease-free.

Languages are finalized as **English and Kannada** for this prototype, based on the Bengaluru event context. Kannada content starts as a translated draft and requires language/pronunciation checking before being described as reviewed.

## Features and acceptance

| Feature | Final behavior | Acceptance |
|---|---|---|
| First use | Choose language and see supported crops; no account | Entire installed experience starts in airplane mode |
| Crop selection | Tomato, potato, maize with accessible names and illustrations | Selected crop persists through the assessment |
| Photo input | CameraX capture or Android gallery picker, EXIF correction, user-adjustable crop | Rotated/large images and cancellation handled without crashing |
| Capture assistance | Blur/exposure checks on a downsampled photo; concrete retake instructions | Thresholds measured on a validation collection; no claim of perfect leaf detection |
| Local assessment | A single bundled model, CPU inference, no image upload | Works without connectivity or model downloads |
| Result states | Likely condition, healthy-looking, crop mismatch, uncertain, or recoverable error | Each has clear next steps and avoids forced disease assignments |
| Confidence | Calibrated score explained as model confidence, with validation-derived acceptance rules | Calibration and accepted-prediction coverage are reported |
| Severity guidance | A separate symptom-based concern check, with spoken prompts where needed; never inferred from classifier confidence | Concern rules checked against agronomic references; no claim of validated photo-based severity |
| Guidance | Short symptom checklist, practical management, prevention and escalation steps | Every enabled advice card has a source/version and verified condition mapping |
| Offline audio | Local English/Kannada clips with play/pause/replay | Works without installed TTS voices or network services |
| History | Local observations with image, crop, timestamp, outcome, model version; deletion | Survives restart; deletion removes owned files and records |
| Expert follow-up | Export observation card; optionally dial a saved contact via system dialer | No claim that a remote expert was contacted without connectivity |
| Model information | Supported labels, version, credits, known limitations | Matches the bundled model/content versions |

Condition-specific guidance is enabled only for classes with adequate validation and sourced content. A low-performing or unreviewed class returns an uncertain result. Its probability is not reassigned to another class.

## Screens

Language/onboarding → home → crop selection → capture/import → photo review → local assessment → result → guidance/audio. History and model information are secondary destinations. Expert follow-up is an action from the result, not a separate marketplace.

Use large primary actions, readable contrast, text alongside icons, and short sentences. Avoid color as the sole indicator of confidence. A restrained earthy green visual theme supports readability; the UI must communicate uncertainty as clearly as a successful diagnosis.

## Product boundaries

The first release has a local architecture. Accounts, cloud sync, weather predictions, marketplaces, chatbots, automatic pesticide prescriptions, severity percentages and segmentation heatmaps are outside the finalized scope. These features would require additional data or infrastructure and do not establish the statement's core outcomes.

## Differentiation hypothesis

The combination we will demonstrate is **complete offline operation, guided photo capture, measured uncertainty handling, regional-language audio, and transparent evaluation on varied images**. Offline crop diagnosis is already an established category; no first-of-its-kind claim is made. Symptom guidance explains known condition characteristics, not proof that the model localized those characteristics in a particular image.
