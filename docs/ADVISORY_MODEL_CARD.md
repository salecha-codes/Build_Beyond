# Offline care and urgency decision model

## Purpose and status

This is the app's second model: a small, deterministic **knowledge-based advisory decision model** following the image classifier. It combines the suspected crop condition with a farmer's answers to produce reported-damage and action-priority categories plus a conditional care plan. It runs locally on Android and in the browser; it requires no paid API, server database, large language model or runtime network connection after assets are installed/cached.

**It is not a trained severity neural network.** Its rules and care profiles are authored prototype content. `trained=false`, `agronomist_reviewed=false` and `field_validated=false` must remain true statements about its current status. The phrase `expert_decision_model` identifies the type of knowledge-based system; it does **not** mean an agronomist has reviewed or approved it.

The disease detector and this advisory model have different roles. The detector supplies a tentative category and actual model score; the advisory model does not change that score, confirm its correctness or improve disease-recognition accuracy. Classifier confidence is deliberately absent from damage calculations. A high classification score can accompany mild reported damage or a wrong disease prediction.

## Coverage and assets

The profile set covers all 17 stable IDs in `contracts/labels.json`: four maize categories, three potato categories and ten tomato categories, including each crop's healthy-looking category. The shared knowledge asset is `content/advisory_model.json`; Android packages it under its content assets and the browser receives it through the existing asset-sync/offline-cache pipeline. English, Kannada and Hindi care text are provided. Translations and pronunciation require language review; inclusion is not proof of native-language validation.

Care profiles distinguish healthy, fungal, oomycete, bacterial, viral and pest categories. These distinctions prevent blanket treatment advice: late blight is an oomycete condition, spider mites are a pest category, and viral infections have no curative spray. Risk classes (`routine`, `foliar`, `rapid_blight`, `virus`) provide decision context, not a laboratory pathogen identification.

## Inputs

- The supported condition ID, its assessment status and whether it is permitted to supply a conditional care profile.
- Whether symptoms are spreading quickly.
- Farmer-estimated visible damage to **this leaf**: none, less than 10%, approximately 10–30%, more than 30%, or not known/not reported.
- Whether several plants show symptoms. This is reported prevalence, not measured field incidence.
- Whether plants are wilting or dying.
- Whether fruit, tubers or stems also show symptoms.
- Whether conditions have been wet or humid.
- Whether answers are uncertain.

Missing answers remain unknown; missing leaf extent must not silently become zero or mild. Wet/humid weather adds context but does not by itself establish visible damage or contradict a healthy-looking leaf. Answers are observations reported by the farmer, not measurements made by the camera.

## Outputs and exact prototype rules

The outputs are reported-damage category, urgency, review time, explanation/reason codes, model version, the observations used and an eligible conditional care profile. Confirmation remains required. The care plan includes what to do now, management options, prevention, escalation signs and an explanation of recovery/curability.

### Reported damage

Rules are applied in priority order:

| Reported information | Output |
|---|---|
| Wilting/dying, fruit/tuber/stem symptoms, or more than 30% of this leaf affected | `SEVERE` / severe signs |
| Approximately 10–30% of this leaf affected | `MODERATE` |
| Less than 10% affected | `MILD` |
| Explicitly no visible damage, without wilting/dying or fruit/tuber/stem symptoms | `NONE` |
| No usable extent answer and no higher-priority warning sign | `UNKNOWN` |

These are authored operational categories, **not a validated plant-pathology severity scale**. Fruit/stem involvement and wilting elevate concern without measuring lesion area. A severe-sign result does not mean the entire field is severely diseased. The percentages are the farmer's chosen questionnaire ranges, not segmentation estimates, pathogen load, predicted yield loss or disease-confidence percentages. An explicit no-damage answer remains `NONE` even if symptoms are spreading on other plants; urgency is raised independently rather than changing the reported leaf extent.

### When to act

Rules are applied in priority order:

| Trigger | Output | Requested action/review time |
|---|---|---|
| Wilting/dying, or rapid spread together with several affected plants | `URGENT` | Contact an agriculture expert now; `reviewHours=0` |
| Severe reported signs, suspected late blight (`rapid_blight`), or suspected virus with rapid spread | `SAME_DAY` | Get advice today, within 24 hours |
| Moderate damage, spread, several affected plants, uncertain answers, unknown severity, a suspected virus, or contradiction of a healthy-looking prediction | `SOON` | Ask an expert within 48 hours |
| None of the above | `MONITOR` | Monitor and recheck within 48 hours |

These times are conservative prototype heuristics, not agronomically validated deadlines or guarantees that waiting is safe. A worsening crop should be reassessed immediately rather than waiting for a timer. Local extension advice and immediate observed deterioration take precedence. No weather forecast or automatic field measurement is performed.

Damage and urgency are deliberately separate. A small late-blight-like lesion can produce `MILD` damage and `SAME_DAY` urgency. The model must not weaken that priority simply because the visible damaged area is small.

## Disease support, uncertainty and conflicts

All disease-specific care is **conditional on confirmation**. A displayed low-confidence disease candidate remains a candidate; answering the damage questionnaire does not confirm its cause. A retake/nonleaf result, unavailable model or crop mismatch must not unlock a disease-specific profile. General triage can still use reported warning signs without assigning a disease.

If the classifier says healthy-looking but the farmer reports spots, spread, several affected plants, wilting or fruit/stem/tuber symptoms, the advice uses a `healthy_conflict` explanation, suppresses healthy-specific reassurance and asks for cause confirmation. It preserves any higher urgency caused by those observations. Wet weather alone does not create that conflict. A single normal-looking leaf cannot rule out disease elsewhere on the plant or an unsupported condition.

The advisory model cannot correct false disease classifications, detect nutrient deficiencies, identify every unsupported disease, determine pesticide susceptibility, distinguish all similar pathogens, inspect an entire field or predict yield loss. The existing classifier's field-accuracy limitations remain relevant to all conditional care.

## Worked examples

| Example | Reported damage | Priority and behavior |
|---|---|---|
| Suspected tomato early blight; a few localized spots (<10%); stable; one plant; no wilting or fruit/stem signs | `MILD` | `MONITOR`; low-risk conditional care and recheck within 48 hours |
| Suspected potato late blight with the same small, stable visible extent | `MILD` | `SAME_DAY`; get local confirmation today because suspected disease risk differs from visible extent |
| No damage answers yet, suspected ordinary foliar disease | `UNKNOWN` | `SOON`; ask the questions and seek review within 48 hours rather than labeling the crop mild |
| No damage answers yet, suspected late blight | `UNKNOWN` | `SAME_DAY`; unknown extent does not erase the suspected rapid-blight risk |
| Any candidate with wilting/dying plants | `SEVERE` | `URGENT`; contact an expert now; the cause still requires confirmation |
| Healthy-looking leaf, explicitly no damage and no warning signs | `NONE` | `MONITOR`; continued observation, with no disease-treatment claim |
| Healthy-looking prediction but rapid spread and several affected plants | Depends on reported leaf extent | `URGENT`; generic cause-confirmation guidance, no healthy-profile reassurance |
| Explicitly no damage on this leaf, but rapid spread and several other affected plants | `NONE` | `URGENT`; the leaf answer does not erase field-level warning signs |
| Mouse/nonleaf rejected by the diagnosis pipeline | No image-derived grade | No disease-specific care profile; retake or report symptoms separately |

## Care and intervention boundaries

The plan emphasizes practical nonchemical steps and local confirmation. It does not generate pesticide doses, mixtures, spray calendars or an approved-product prescription. Registered products, crop stage, weather, local resistance, pre-harvest/re-entry intervals, PPE and jurisdiction-specific labeling cannot be inferred from one photo and this questionnaire.

For tomato yellow leaf curl virus and mosaic virus, explain that no treatment restores an infected plant to virus-free health. TYLCV containment involves appropriate whitefly/vector management; mosaic guidance emphasizes contact/tool hygiene rather than copying the TYLCV vector advice. Do not recommend destructive plant removal solely from an uncertain photo. For maize foliar disease, avoid blanket defoliation. For spider mites, ask for underside/webbing inspection and avoid treating a pest category as a fungal infection. Existing damaged tissue may not recover even when management protects new growth or reduces spread; do not promise a cure for every category.

Speech must match its label. Existing bundled observation audio is not a personalized spoken version of a newly calculated plan. New plan clips or composed narration should identify which advice is spoken; missing generated audio must not be hidden behind a claim that every care plan has verified speech. A static clip must not speak an urgency that contradicts the calculated result.

## Evidence and source access

See [ADVISORY_RESEARCH.md](ADVISORY_RESEARCH.md) for the full per-category care review, attempted URLs, access results and dataset evidence. PlantVillage's upstream README was retrieved and supports disease-image taxonomy. The project's examined disease datasets do not supply validated severity, urgency or treatment-response targets.

Attempts to retrieve TNAU, PPQS, UMN, UCIPM and other extension references were blocked by the workspace proxy before reaching the sites. Those pages were **not read** in this session; their URLs are leads for later checking, not evidence of source verification. Current care copy remains conservative draft knowledge, not expert-reviewed prescribing guidance. Presence of a source URL must never be interpreted as successful source access or endorsement.

## Engineering validation and future evaluation

Unit, content-coverage and cross-platform golden-case checks can demonstrate complete profiles, rule consistency, uncertainty handling and parity between Android and the browser. They do not establish agronomic accuracy. Rule-generated examples are not an independently labeled training/test set and must not be reported as measured model accuracy.

Before stronger claims, obtain independent agronomist review of every profile and urgency rule; native-language review; field examples labeled for leaf/plant severity, spread, crop stage and urgency; inter-rater agreement; held-out evaluation separated by plant/farm/collection; and prospective error analysis. A future image-severity model should be trained on those annotations and evaluated independently of this rule engine. Treatment efficacy requires separate outcome evidence rather than inference from disease labels.
