# Offline disease-care and urgency model: evidence review

Research date: 14 November 2026. Scope: all 17 app categories, comprising 14 disease/pest categories and three healthy-looking categories across maize, potato and tomato.

## What the available training data can support

The existing stable contract is `contracts/labels.json`. PlantVillage supplies crop/disease image categories. The local PlantDoc and Kandahar additions also supply source image categories, with the limitations documented in `ml/README.md` and `ml/KANDAHAR_DATA.md`. These inspected project datasets do **not** supply a validated target for whole-plant severity, affected-field fraction, disease progression, urgency, cure, yield loss, pesticide choice or treatment response.

The upstream PlantVillage README was fetched successfully on the research date: <https://raw.githubusercontent.com/spMohanty/PlantVillage-Dataset/master/README.md>. The fetched bytes had SHA-256 `2c5b7ead9a632ffa11df28177e6e52979825ab727eb23faf0b31636954ee2658`; its content describes 54,306 healthy/diseased leaf images over 14 crop species and 26 diseases. Those are **whole-source dataset counts**, not the size of this app's selected three-crop subset. It describes image-based disease classification and does not document severity or treatment-response annotations. A disease classification label alone cannot establish how much of a leaf, plant or field is affected.

Consequently the second model should initially be an explicit, versioned **knowledge-based advisory decision model**, operating offline. It can combine a tentative disease candidate with farmer-reported extent, spread and red flags. It must identify reported observations as reported, inferred urgency as a decision rule, and unconfirmed disease as unconfirmed. It must not be described as a trained or agronomically validated severity network. A future trained severity component needs independently annotated field images, patient/plant-level separation, affected-area or ordinal labels, inter-rater agreement and external validation. Expert-labeled urgency requires symptom history and management context, not photos alone.

## Access and evidence status

The extension and Indian crop-protection sources below were attempted directly via HTTPS. The workspace network proxy returned `Tunnel connection failed: 403 Forbidden` for every extension/government URL on the research date. **Their contents were not read in this session.** They are reference leads for independent verification, not support for a claim that today's draft has been source-verified or expert-reviewed. Existing project observation content has the same earlier access limitation. No chemical dose, spray schedule, efficacy guarantee or agronomist endorsement is justified by this review.

| Reference lead | Intended scope | Access result |
|---|---|---|
| <https://agritech.tnau.ac.in/crop_protection/tomato_diseases.html> | Indian tomato disease-management reference | Proxy 403, not read |
| <https://ppqs.gov.in/divisions/integrated-pest-management/ipm-package-of-practices> | Indian government IPM package index; crop/local label checks | Proxy 403, not read |
| <https://extension.umn.edu/disease-management/early-blight-tomato-and-potato> | Tomato/potato early-blight reference | Proxy 403, not read |
| <https://extension.umn.edu/disease-management/late-blight> | Late-blight reference | Proxy 403, not read |
| <https://extension.umn.edu/plant-diseases/tomato-leaf-mold> | Tomato leaf-mold reference | Proxy 403, not read |
| <https://extension.umn.edu/plant-diseases/septoria-leaf-spot-tomatoes> | Tomato Septoria reference | Proxy 403, not read |
| <https://extension.umn.edu/plant-diseases/tomato-virus-diseases> | Tomato virus-management reference | Proxy 403, not read |
| <https://extension.psu.edu/late-blight-of-potato-and-tomato> | Late-blight confirmation/management lead | Proxy 403, not read |
| <https://www.vegetables.cornell.edu/pest-management/disease-factsheets/> | Extension disease factsheet index | Proxy 403, not read |
| <https://ipm.ucanr.edu/agriculture/tomato/tomato-yellow-leaf-curl/> | TYLCV/vector reference lead | Proxy 403, not read |
| <https://ipm.ucanr.edu/agriculture/tomato/bacterial-spot/> | Bacterial-spot reference lead | Proxy 403, not read |
| <https://extension.entm.purdue.edu/fieldcropsipm/insects/corn-common-rust.php> | Attempted maize-rust reference lead; exact path unverified | Proxy 403, not read |
| <https://ipmdata.ipmcenters.org/documents/cropprofiles/INcorn.pdf> | Maize crop-profile lead | Proxy 403, not read |
| <https://crop-protection-network.s3.amazonaws.com/publications/cpn-2005-corn-foliar-diseases.pdf> | Maize foliar-disease lead; exact filename unverified | Proxy 403, not read |

Because the proxy fails before origin, these results do not establish whether any individual page path currently exists. Persist both `verification_status` and `expert_reviewed=false` with advice content. The app must not collapse “URL present” into “evidence verified.”

## Decision inputs and outputs

Recommended inputs are the actual classifier result and support/uncertainty state; farmer-reported proportion of affected leaf; number/fraction of plants affected; speed of spread; wilting/whole-plant collapse; stem/fruit/tuber involvement; and maize ear-leaf involvement or reproductive stage where relevant. A single close-up does not establish field prevalence. Missing answers remain unknown and should trigger follow-up questions rather than silently becoming zero.

Separate four concepts in the output:

1. **Disease candidate**: the real classification output, with its original uncertainty.
2. **Reported extent**: mild/moderate/extensive based on explicit questionnaire ranges. Percentage cutoffs are prototype operational bins, not scientifically validated disease thresholds.
3. **Urgency**: monitor / act soon / contact an expert today, using transparent disease-specific rules and red flags.
4. **Care plan**: immediate low-risk actions; prevention/containment; what to avoid; when to reassess; whether cure exists; and source/review status.

Do not convert a 90% classifier score into 90% severity or a 90% guarantee of correct diagnosis. Do not display “not severe” when answers or image support are missing. Suspected late blight can warrant same-day expert contact even with a small visible affected area, because extent and urgency differ. A healthy-looking prediction with rapid wilting or fruit/tuber symptoms warrants reassessment and should never override the reported warning sign.

Suggested prototype urgency rules are transparent product behavior, **not expert-validated agronomic thresholds**: fast spread, whole-plant collapse or substantial stem/fruit/tuber damage prompts same-day expert contact; modest localized stable spotting prompts monitoring and targeted care; extensive damage/multiple affected plants prompts earlier review. A disease-specific rule may raise urgency but must not falsely confirm the disease. Use “if this suspected condition is confirmed” for disease-specific actions when classification remains tentative.

## Draft care knowledge for every supported category

The table below is conservative domain-informed draft IPM content. It has **not** been verified against the inaccessible references or reviewed by an agronomist in this session. It is intended for versioned prototype advice, with that status preserved in metadata. It deliberately avoids prescription doses and automatic spraying. “Urgent” means seek confirmation and management advice promptly; it does not establish a confirmed diagnosis or authorize a chemical treatment.

| Stable category | Practical care / prevention | Raise urgency when | Important limitation / avoid |
|---|---|---|---|
| `maize_gray_leaf_spot` | Inspect additional leaves and plants; record rectangular lesions and progression. Preserve healthy canopy; plan crop rotation/residue management and resistant varieties for subsequent crops. | Damage reaches the ear leaf/upper canopy near flowering, expands rapidly or affects many plants. | Do not strip maize leaves as a generic cure. Existing lesions are not repaired by treatment; local growth-stage and economic context determine any fungicide decision. |
| `maize_common_rust` | Inspect both leaf surfaces for rust pustules, track spread and crop stage; prefer resistant varieties in future plantings. | Rapid upper-canopy spread, substantial green-leaf loss or flowering/ear-leaf involvement. | Distinguishing common from southern rust matters; the app does not support every rust type. No routine fungicide based solely on this photo label. |
| `maize_northern_leaf_blight` | Record elongated/cigar-shaped lesions and upper-canopy involvement; maintain crop health; plan resistant varieties, rotation and residue management. | Rapid spread, ear-leaf damage or substantial foliage damage around flowering. | Do not remove large parts of canopy; management benefit depends on crop stage, susceptibility and local assessment. |
| `maize_healthy` | Continue periodic whole-plant scouting and sensible water/nutrition management. | Farmer reports wilting, fast spread, ear/stem damage or symptoms on leaves not pictured. | Healthy-looking is a photo category, not confirmation that the plant/field is disease-free. No preventive spray solely from the app. |
| `potato_early_blight` | Keep foliage dry where practical; irrigate at soil level; record older-leaf lesions; manage stress and nutrition; use clean planting material and rotation. | Rapid progression, substantial defoliation or suspected tuber involvement. | Concentric spots overlap with other causes. No blanket instruction to remove most leaves; no automatic fungicide selection. |
| `potato_late_blight` | Seek prompt local confirmation; avoid overhead irrigation/handling wet foliage; keep suspect harvested tubers separate; do not save suspect tubers for planting. | Suspected late blight merits same-day expert contact, especially with wet weather, rapid spread, stem lesions or tuber rot. | It can progress rapidly. Do not promise a cure or continue spreading suspect planting material. Expert/local guidance controls any plant disposal or registered-treatment decision. |
| `potato_healthy` | Continue scouting several leaves and inspect plants/tubers when symptoms are reported; maintain sound storage and planting-material hygiene. | Wilting, stem symptoms, rapid field spread or tuber rot despite a healthy-looking leaf. | One healthy leaf does not rule out tuber disease or unsupported conditions. |
| `tomato_bacterial_spot` | Avoid working wet plants; reduce splashing/overhead irrigation; clean tools and use clean seed/transplants; separate suspect transplants for assessment. | Rapid spread, leaf drop or fruit lesions. | Bacterial disease is not automatically treated with a fungal product. Copper efficacy/resistance and permitted products vary; no automatic copper prescription. |
| `tomato_early_blight` | Improve airflow; use mulch to reduce soil splash; water at soil level; remove only a few badly affected lower leaves if practical, without excessive defoliation; rotate next season. | Progression to upper canopy, major foliage loss or fruit/stem symptoms. | Existing spots will not heal; compare new growth/progression. Avoid working wet plants and avoid removing most of the canopy. |
| `tomato_late_blight` | Seek same-day confirmation; avoid handling wet foliage and overhead irrigation; isolate suspect plants/produce for assessment; record rapid spread. | A suspected match merits prompt expert contact; wet-weather spread, expanding water-soaked patches or fruit/stem involvement increases concern. | Not a guaranteed curable condition; prompt containment and locally approved management depend on confirmation. |
| `tomato_leaf_mold` | Reduce sustained humidity/condensation; ventilate protected cultivation; improve spacing/airflow and avoid wetting leaves; inspect leaf undersides. | Rapid spread, extensive foliage damage or persistent humid conditions in protected cultivation. | Yellow patches alone are nonspecific. Do not equate ventilation with a guaranteed cure or prescribe an unspecified fungicide. |
| `tomato_septoria_leaf_spot` | Reduce splash with soil-level watering/mulch; remove limited badly affected lower foliage when dry; clean tools and manage infected residues between crops. | Lower-to-upper spread, extensive defoliation or many affected plants. | A close-up cannot establish whole-plant extent; retain healthy foliage. |
| `tomato_spider_mites` | Check undersides with magnification for live mites/webbing; reduce plant water stress and dusty conditions; a gentle water rinse of undersides may help a limited infestation where practical. | Heavy webbing, bronzing, rapid spread or leaf loss. | This is a pest-symptom class. Fungal sprays do not diagnose/control mites; indiscriminate broad-spectrum spraying can harm natural enemies. Local expert advice should guide any registered miticide and resistance management. |
| `tomato_target_spot` | Reduce leaf wetness and prolonged humidity; improve airflow; manage crop residues and inspect fruit as well as foliage. | Rapid defoliation, many affected plants or fruit lesions. | Several leaf-spot diseases look similar. Confirm before condition-specific treatment; avoid treating a label as a confirmed pathogen test. |
| `tomato_yellow_leaf_curl_virus` | Seek confirmation; inspect young leaves and nearby plants; monitor whiteflies; use clean/resistant transplants and locally appropriate integrated vector/weed-host management. | Young plants with strong curling/stunting or rapidly increasing affected plants need prompt expert advice. | No treatment restores an infected plant to virus-free health. Vector control limits transmission; it does not cure existing infection. Do not prescribe fungicides as a cure. Plant removal should follow confirmed/local advice. |
| `tomato_mosaic_virus` | Limit contact between suspect and healthy plants; clean hands/tools; avoid handling healthy plants after suspect plants; use clean seed/transplants and seek confirmation. | New cases after handling, marked stunting or widespread mosaic/fruit symptoms. | No curative spray. Mosaic appearance has multiple causes; ToMV is commonly mechanically/contact transmitted, so do not copy whitefly instructions from TYLCV. Do not recommend destructive removal solely from an uncertain photo. |
| `tomato_healthy` | Continue scouting, maintain irrigation/nutrition and inspect new growth and fruit. | Rapid wilting, new widespread symptoms, fruit/stem involvement or contradictory reported symptoms. | Healthy-looking leaf is not a whole-plant health certificate; no routine pesticide recommendation. |

## Content and behavior requirements

- Cover all 17 stable IDs exactly once; healthy categories receive monitoring, not disease treatments.
- Keep `curable=false` for supported viral candidates and explain containment rather than promising elimination. More generally avoid an absolute “curable” claim for the other conditions: treatment can protect new growth/reduce spread without repairing existing tissue.
- Advice should be conditional when the classifier is uncertain, mismatched, unsupported or a farmer has selected a hypothetical disease. Preserve the actual source-model score and provenance.
- A nonleaf image must never obtain a disease-specific prescription simply because the advisory model exists. General symptom triage can still act on farmer-reported red flags without asserting disease.
- Keep fixed nonchemical care steps distinct from any expert/local treatment decision. No pesticide active ingredient/dose/interval/mixture should be generated as if approved. Weather, growth stage, local registration, product label, pre-harvest/re-entry interval, resistance and PPE matter.
- Keep severity assessment independent of confidence, support unknown answers, and make reason codes visible for urgency. Do not silently infer field prevalence from lesion coverage.
- Store knowledge/model version, source IDs, source verification, review status, farmer answers and advisory output with saved observations so future content changes are traceable.
- Current static bundled disease audio is general observation guidance. Do not label it as the spoken version of a new personalized care plan unless its text actually matches. Regenerate or concatenate verified plan speech, or clearly identify that audio as general guidance. Hindi/Kannada translations require explicit draft-review status until reviewed.

## Verification targets for the implementation

Meaningful behavior checks should include each of the 17 categories; suspected late blight with mild extent but raised urgency; extensive/rapidly spreading symptoms; a healthy-looking result contradicted by wilting; missing answers; viral no-cure language; nonleaf and unsupported-classifier suppression; and identical advisory results between browser and Android from shared golden cases. These are engineering checks of decision consistency, **not measured agronomic accuracy**. Do not report synthetic rule-generated cases as independent clinical/agronomic validation or a trained-model test dataset.
