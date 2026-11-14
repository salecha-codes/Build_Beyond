# Build Beyond ’26 — Final Project Report

## Project details

- **Hackathon:** Build Beyond ’26 (24-hour hackathon)
- **Project:** AgriScan — Offline Crop Disease Detection and Advisory on Low-End Phones
- **Problem statement:** PS 4.1 — Offline crop disease detection
- **Team:** Debuggers · Team 8
- **Team members:** Jeeveen MR · Ishank AB · Mahendra
- **Institution:** BMS College of Engineering / Gradient Club
- **GitHub:** https://github.com/salecha-codes/Build_Beyond
- **Live prototype:** https://salecha-codes.github.io/Build_Beyond/
- **Demo video:** To be added by the team; organizer limit is one minute.
- **Report date:** 15 November 2026

## 1. Analysis of the problem statement

### 1.1 Problem overview

Smallholder farmers need to recognize crop symptoms and decide what to inspect or do next. Existing expert support may not be immediately available, while a phone-based photo tool can be difficult to use when the phone has weak connectivity, limited memory, or an unfamiliar language. A photo alone also cannot reliably explain the extent of damage or the urgency of action.

PS 4.1 asks for an offline Android application for a small set of crops. Our prototype focuses on tomato, potato, and maize. It analyzes a leaf photo on-device, presents a model candidate with explicit uncertainty, asks about observable symptoms, and provides conditional care and recovery steps in English, Kannada, or Hindi.

### 1.2 Causes and impact

- **Connectivity:** network access in a field may be intermittent or unavailable. Requiring a server round-trip makes an assessment unavailable at the moment it is needed.
- **Visual ambiguity:** disease symptoms can overlap; lighting, background, leaf age, and camera quality also affect a photo classifier. A high image score is not proof of a correct field diagnosis.
- **Limited context:** image recognition cannot infer spread across plants, wilting, fruit/stem damage, or recent wet weather. Those observations can change how quickly a farmer should seek advice.
- **Language and literacy:** written instructions alone may be inaccessible. Local-language text and audio make the prototype usable without relying on reading fluency.
- **Device constraints:** large models, large photos, and network services can be impractical on budget phones. On-device inference and bounded photo processing reduce those dependencies, though physical-device performance still needs measurement.

The consequences of a mistaken disease guess can include delayed expert help or inappropriate crop treatment. Therefore the prototype distinguishes a model output from a confirmed diagnosis and directs uncertain or concerning cases toward local agricultural expertise. We do not claim a quantified reduction in crop loss.

## 2. Research gap

### 2.1 Existing solutions

Mobile crop advisory products and research systems already explore photo-based plant-health recognition and farmer guidance. Examples include Plantix and PlantVillage Nuru. Research datasets such as PlantVillage make image classification experiments possible. These efforts show that mobile image analysis is feasible, but dataset performance does not establish performance on field photographs, every phone, or every farming region.

Products differ in crop coverage, language availability, offline behavior, and the way they communicate confidence. Features can change between product versions and regions; this report does not make a universal claim that existing products lack offline or language support.

### 2.2 Identified gap

The design gap we address is a single, lightweight workflow that keeps the core photo analysis and advice on the device, asks about field-observable symptoms, shows when the result is uncertain, and offers spoken regional-language guidance. The key distinction is that the app keeps image classification separate from farmer-reported damage and urgency. It does not turn classifier confidence into a severity measurement.

Our prototype remains limited: its current disease model performs substantially worse on a small field-like benchmark than on source-dataset test images. Care guidance is authored and rule-based, not learned from treatment outcomes, and awaits agronomist and language review. These are open validation gaps rather than solved product claims.

## 3. Ideation of the solution

### 3.1 Proposed solution

AgriScan is an offline-first crop-health prototype for tomato, potato, and maize, with 17 supported image labels across the three crops.

- Capture a leaf with the camera or select a photo from the gallery.
- Run leaf/object checks and a MobileNetV3-Large image classifier locally; show the candidate and model score with a clear prototype/uncertainty message.
- Ask six questions about visible damage, spread, affected plants, wilting, fruit/stem symptoms, and wet weather.
- Use a separate offline decision model with 17 condition profiles to summarize reported damage and suggest an action timeframe. Unknown answers remain unknown.
- Show condition-specific confirmation checks, look-alikes, care options, avoidances, recovery signs, failure signs, and follow-up checkpoints. Disease-specific actions remain conditional on confirming the cause.
- Provide English, Kannada, and Hindi text and bundled audio, plus local scan history.
- Keep inference and saved records on the device. Android has no Internet permission; the browser downloads its app assets on first use and then supports offline use through its service worker.

### 3.2 How it works

1. **Input:** camera or gallery photo; selected crop.
2. **Image preparation:** resize and normalize locally, then check whether the input is leaf-like and usable.
3. **Image model:** bundled ONNX MobileNetV3-Large produces candidate scores for 17 labels. An input rejection or uncertainty path avoids presenting an unsupported disease result.
4. **Farmer context:** six optional symptom questions collect reported observations; these are not image-derived measurements.
5. **Care and urgency:** a separate transparent rules/profile system combines the candidate condition with reported observations. It selects an urgency summary and a care protocol; it is not a trained severity neural network.
6. **Output and storage:** show guidance and audio in the selected language. Save scans locally in Android Room/SQLite or browser IndexedDB.

**Technology:** Android Kotlin and Jetpack Compose; web React and TypeScript; ONNX Runtime; MobileNetV3-Large; Android Room/SQLite and browser IndexedDB; bundled audio and JSON content. No cloud inference or required paid API is used at runtime.

## 4. Implementation roadmap

### 4.1 Work completed in 24 hours

The hackathon prototype was developed through the review milestones. The final repository includes a native Android application and a browser preview with the same bundled disease model and condition content. The current source includes camera/gallery workflows, local inference, input screening, a six-question symptom flow, a separate care/urgency system, 17 condition-specific treatment and recovery protocols, English/Kannada/Hindi text and audio, local history, and offline web caching.

The disease image model was trained/evaluated using tomato, potato, and maize image categories. The provided dataset inventory showed 24,164 RGB files before deduplication; repository audit records 24,150 unique images after removing 14 exact duplicates. The current disease head used a capped subset of 6,324 PlantVillage training images, 632 PlantDoc field training images, and 448 additional maize Healthy training images. Other partitions were reserved for tuning, calibration, and tests as documented in the repository.

**Evaluation evidence and limits:** the repository reports 92.27% accuracy on 3,674 PlantVillage source test photos and 38.75% on a reused 80-photo PlantDoc field-like comparison. The latter is a small sample and indicates weak field generalization. A separate leaf/object screening test rejected 125/125 held-out non-leaf sample images; that is not a guarantee for every unseen object or plant. Field-diagnosis validation remains false. The care content is not agronomist-validated, and no pesticide doses are prescribed.

**Challenges addressed:** misleading high-confidence errors, crop mismatch, rejection of non-leaf images, uncertainty communication, variation in damage urgency, offline asset caching, local-language audio, and keeping manual care-library browsing separate from a saved photo diagnosis. Recent team commits also updated native camera/app entry points and added model reliability/acceptance tooling. This report describes the repository at source commit `313e820`.

### 4.2 Future roadmap

| Phase | Target | Work |
|---|---|---|
| 1. Field validation | 2–4 weeks | Collect consented field photos across devices, regions, seasons, and disease stages; define expert labels; evaluate per-class precision/recall and calibration; keep a frozen test set. |
| 2. Agronomy and language review | 2–3 weeks | Have agronomists review all 17 protocols and urgency rules; validate Kannada/Hindi terminology and narration with native speakers; revise unsafe or ambiguous advice. |
| 3. Device optimization | 1–2 weeks | Measure RAM, latency, battery, camera behavior, and install size on representative 3–4 GB Android phones; optimize model/runtime only against held-out field performance. |
| 4. Pilot | 4–8 weeks | Run a supervised farmer pilot with local extension workers; collect usability and failure reports; make escalation and correction paths clear. |
| 5. Release readiness | Ongoing | Add update/signing process, accessibility checks, privacy review, device matrix, monitoring of model regressions, and maintained care references. |

Resources needed: crop-protection agronomists, Kannada/Hindi reviewers, consented field-photo collection, several budget Android devices, and supervised access to local farmer/extension-worker feedback. A product release should depend on evidence from these steps, not the current prototype scores alone.

## 5. SDG mapping

- **SDG 2 — Zero Hunger:** contributes to the goal of supporting sustainable agriculture by exploring accessible crop-health guidance. A reduction in crop loss has not yet been measured.
- **SDG 9 — Industry, Innovation and Infrastructure:** demonstrates offline-capable digital innovation designed for constrained connectivity and devices.
- **SDG 10 — Reduced Inequalities:** regional-language text/audio and an offline workflow aim to reduce access barriers for farmers with limited connectivity or literacy. This benefit needs field usability evaluation.
- **SDG 12 — Responsible Consumption and Production:** conditional advice, uncertainty messaging, and the absence of automated pesticide dosing are intended to discourage action based solely on an unverified image result. Behavior change has not been measured.

## References

1. Build Beyond ’26 Problem Statement PS 4.1 and organizer final-report template supplied to the team.
2. PlantVillage Dataset: https://github.com/spMohanty/PlantVillage-Dataset
3. PlantDoc: Singh et al., “PlantDoc: A Dataset for Visual Plant Disease Detection,” 2020. https://arxiv.org/abs/1911.10317
4. Plantix product information: https://plantix.net/en/
5. PlantVillage Nuru / PlantVillage: https://plantvillage.psu.edu/
6. United Nations Sustainable Development Goals: https://sdgs.un.org/goals
7. Project README, dataset audit, evaluation receipts, model cards, care-protocol research, and Review 2 submission notes: https://github.com/salecha-codes/Build_Beyond
