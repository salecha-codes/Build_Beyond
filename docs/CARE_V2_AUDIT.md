# Care model v1: functional and information audit

This is a read-only audit of the care implementation shipped in app 0.5.0. It
examines application behavior and information coverage, not agricultural accuracy.
No app, dataset, model or audio files were edited by the auditor.

## Main findings

| Priority | Finding | Evidence | User impact | Concrete repair |
|---|---|---|---|---|
| High | Severity changes the badge, reasons and urgency narration, but not the disease actions. | Web `AdvisoryPanel.tsx` renders the same `do_now`, `management`, `prevention` and `escalation` arrays regardless of `result.severity`; Android `GuidanceScreen` does the same. | A mild case and a severe case appear to receive essentially the same plan. The second model feels like a questionnaire attached to a static article. | Select a documented stage-specific action plan using severity and urgency; show the input parameters used, immediate priorities, a reassessment schedule, expected changes and explicit escalation triggers. Test action differences, not only badge differences. |
| High | All 17 profiles are inaccessible independently of image recognition. | `App.tsx` obtains the care condition only from an assessment or saved scan; there is no library screen or manual condition selection. Native `refreshCopy()` has the same dependency on live/stored candidate eligibility. | Classifier failures, crop mismatch or an unsupported input leave the user unable to read an otherwise existing care article. A farmer who already knows the disease cannot use the app for care alone. | Add a crop-filtered searchable care library reachable from Home and from a result. Label manual selection clearly as user-selected information, separate from the actual classifier output. Do not use manual browsing to relabel object photos as diagnosed disease. |
| High | A healthy-looking prediction conflicting with symptoms removes the entire profile and leaves only a very short generic response. | Web `evaluateAdvisory()` sets `profile = null` on `healthyConflict`; the generic detailed panel has two bullets. Native `refreshCopy()` drops `advisoryProfile` and `GuidanceScreen` shows two generic actions. | The most important contradictory case can look like the app has no useful information. | Keep a substantial symptom-led assessment: checks for water stress, roots, pests, disease look-alikes, whole-plant photos, nearby plants, urgent red flags and follow-up. Offer the library as an explicitly separate educational path. Preserve the original healthy-looking output and uncertainty. |
| High | The profiles are short first-aid notes, not a complete management workflow. | Example tomato early blight has 2 immediate bullets, 2 management bullets, 2 prevention bullets and 1 escalation bullet; chemical management ends at asking an adviser whether a registered fungicide is needed. | The user asks for treatment and recovery information but mostly receives checking, prevention and referral. | Add disease-specific identification checks, look-alikes, cultural/biological/chemical management categories where sources support them, what each option can and cannot do, prohibited/common mistakes, recheck timing and indicators of improvement. Product/dose recommendations require jurisdiction-specific verified labels and context; do not fill gaps with invented doses. |
| Medium | Wet weather is collected but barely personalizes the result. | Web/native add a generic reason for wet weather, but neither selects weather-specific care steps or alters follow-up. | The sixth question can feel pointless. | Use wetness as a context modifier in disease-specific actions (foliage handling, irrigation, scouting timing) with an explanation. Keep it separate from measured severity. |
| Medium | The questionnaire loses which individual questions were answered “not sure.” | ReportedSymptoms stores boolean values plus one `uncertainAnswers` flag. A question-specific unknown becomes false with a global uncertain flag. | A plan cannot distinguish uncertain wilting from uncertain weather or explain exactly which missing input matters. | Preserve answer-level tri-state values or an `unknownFields` list in a backward-compatible schema. Show missing parameters and avoid routine reassurance when a material parameter is unknown. |
| Medium | Native care-catalog failure is silently converted into generic care. | `CropHealthViewModel` constructs `AdvisoryCatalog` with `runCatching(...).getOrNull()` and no care-load error state. | A missing/corrupt asset looks like an unsupported disease instead of a technical failure. | Add a visible model-loading/failed state, an asset/version identifier and a retry or recovery path. Web already reports advisory load failure, but currently has no explicit retry control. |
| Medium | Editing a saved questionnaire starts over instead of showing saved values. | Web `beginConcern()` resets six answers to null. Native navigation into `CONCERN` resets all symptoms. | Revising one answer requires six new answers and obscures the saved parameters. | Populate edit controls from saved answers; use an explicit reassess/reset action if starting over is desired. |
| Medium | Web and Android use different save behavior for reassessment. | Web has explicit “Save care answers”; Android writes completed answers automatically when a savedObservationId exists. Native IO update has no local error handling around `history.updateSymptoms`. | A user can assume an update was saved across platforms when it was not, or fail to see a native write error. | Choose a consistent explicit-save or autosave convention, show saved/error status, preserve original photo and classifier output, and retain old answers if a write fails. |
| Medium | Existing speech intentionally summarizes only part of the plan. | The new care clip contains a conditional prefix, curability and the first two immediate actions. | A farmer unable to read cannot hear management, prevention or escalation sections. | Add accurately labeled per-section narration or composed offline narration for the actual selected plan. Retain exclusive playback and validate text/audio hash bindings. |
| Low | Sources do not provide the same information across clients. | Web exposes linked references with verification status; Android shows only reference titles. Existing extension URLs were not retrieved in the previous session. | A list of titles may suggest stronger evidence than the content has. | Show source/review status and URLs consistently. Separate retrieved evidence, taxonomy-only sources, inaccessible reference leads and expert review. |

## What is working and should be preserved

- The existing source explicitly identifies the advisory component as authored
  decision rules, with `trained=false` and `field_validated=false`.
- Severity does not derive from classifier confidence.
- Missing answers remain unknown or prevent routine reassurance.
- A small suspected late-blight area can receive same-day urgency.
- Retake, model-unavailable and crop-mismatch states do not authorize
  disease-specific care from the rejected prediction.
- Saved photo/inference preservation and Room v1-to-v2 migration have test evidence.
- Language switching refreshes native profile copy, and web profile copy is
  selected by the active language.
- The tested browser flow includes real inference, saved answers, offline
  playback, three languages and mouse rejection.

## Limits of existing test evidence

The recorded browser report checks that conditional care sections exist, audio
plays, severity/urgency labels change and saved answers persist. It does not
check that different symptom severities select different treatment steps, that
the management advice is agronomically complete, or that a farmer can access
care without a classifier result. Passing those tests therefore does not answer
the user's current complaint about insufficient information.

## Focused acceptance checks for the next revision

1. From Home, choose each crop and open every supported condition without a photo;
   keep manual selection provenance visible.
2. For one condition, compare mild, moderate, severe, missing-answer and rapid-spread
   plans; verify meaningful action/follow-up differences and explanatory reasons.
3. Show a healthy-looking result plus reported wilting; retain urgent help and a
   substantial symptom-led plan without claiming a confirmed disease.
4. Show an object photo; ensure no diagnosis or photo-derived disease care appears,
   while a separate educational library remains available.
5. Reopen and edit one saved answer; preserve other answers, photo and model output,
   and display save success/failure consistently.
6. Load/corrupt a care asset in a controlled test; show a technical loading error
   rather than silently presenting an empty generic plan.
7. Play every newly displayed plan section in all three languages after offline
   readiness; prove the narration matches its selected text/summary label.
8. Verify every disease-specific recommendation has an honest source/review status;
   never count rule-generated fixtures as independent field accuracy evidence.

## Implemented response in version 0.6.0

The revised clients add a standalone library with isolated manual sessions,
complete treatment/recovery protocols and distinct severity action paths.
Urgency appears before the long plan. Healthy conflicts retain evaluation
instructions. Protocol loading failures are explicit and retryable. Known
saved answers are prefilled; globally uncertain legacy answers are not guessed
as negative answers. New narration is explicitly a treatment overview and stage
summary, rather than a claim to read every on-screen reference or bullet.

The direct engine checks and real browser flow verify all 17 conditions,
severity action differences, manual-session isolation, offline text, answer
prefill and failure/retry recovery. Narration is checked separately against its
manifest and final packaged build. These are engineering checks; agronomist and
native-language validation remain outstanding. The source audit found no
verified full treatment-outcome dataset or registered dose table for all crops.
