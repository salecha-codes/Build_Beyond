# Treatment and recovery expansion: source audit

Research performed on 14 November 2026. The user clarified that the missing
information is **specific treatment and recovery steps**. The relevant task is
therefore to improve disease-specific management pathways and follow-up, rather
than train another severity classifier from unrelated photographs.

## Primary reference access

Direct retrieval of TNAU's tomato disease page, University of Minnesota's
early-blight page, UC IPM's bacterial-spot page, PlantVillage's Penn State topic
pages, APS and EPA failed at the workspace proxy with `403 Forbidden` before
origin. These pages were not read. The result does not determine whether a
particular origin page exists. A URL alone must not be presented as verified
evidence, expert approval or current Indian pesticide registration.

GitHub web pages and raw files were reachable. GitHub API requests were blocked.
Searches for TNAU PDFs found three repositories, but inspection did **not** find
a usable primary treatment source:

| Repository inspected | Actual result |
|---|---|
| `notescultureweb/ICAR-TNAU-E-COURSE` | `lec02.html` is a frameset stub. The retrieved 807,326-byte `lec04.zip` contains a **tractors, types and utilities** lecture, not crop disease treatment. |
| `stephenpaul2509c-ship-it/agriculture_tamil_nadu` | README describes a TNAU crop-guide RAG pipeline. `AGRICULTURE.pdf`, `chunks.json` and `chunks_split.json` return 404; no underlying treatment document was obtained. |
| `ajmalaji81/SE-AI-B12-1-W2-Buildathan` | The uploaded document is Tamil Nadu agricultural policy `agri_e_pn_2026_27.pdf`, not a retrieved disease-management guide. It was not used for treatment claims. |

No active ingredient, dose, spray interval or product approval was source-verified
by these searches. The app should not fill that gap with an invented medicine
table or present a foreign product choice as approved in India.

## Actually retrieved comparative IPM data

Repository: <https://github.com/BioPabloCG/ipm_pest_identifier>

Pinned revision: `f4a93ab472002bebb9168e2156fe28705822fb29`.

Read `README.md`, `LICENSE`, and `Database/species_data.csv`,
`Database/control_data.csv`, `Database/monitoring_data.csv`. Its README describes
manual transcription from Spanish Ministry of Agriculture IPM guides and reports
12/44 guides processed. The repository license is **GPL-3.0**. The originating
Ministry guides were not retrieved here. This is a third-party transcription,
not a primary-source or India-registration verification. Raw CSVs are not
installed in the app or represented as a training set.

Rows actually inspected include potato row `109` (late blight; the source spells
the pathogen `Phytophtora infestans`) and row `111` (`Alternaria solani`, early
blight). Their content supports a **comparative consistency check**, not a new
verified prescription:

- Both controls discuss fungicides when weather favors disease, with different
  modes of action alternated to limit resistance. Neither names an active
  ingredient or dose.
- The late-blight monitoring row calls for inspection of leaf/stem symptoms.
  Prevention includes certified planting material, management of inoculum
  sources and excluding affected tubers before storage. Its threshold field
  explicitly says no defined threshold.
- Early-blight monitoring calls for visual observation supported by technician
  or laboratory diagnosis. Prevention includes broad rotation, adequate water
  and nutrition, and mature tubers at harvest. The dataset does not supply a
  scientifically measured recovery deadline or treatment-outcome target.
- Other crops and pest categories occur, but no complete matching 17-category,
  three-crop treatment-and-recovery label set was verified. Mite rows in other
  crops must not be treated as tomato-specific thresholds or chemical approvals.

Independently authored summaries can explain the general management concepts;
copying the CSV into a differently licensed application would require a separate
license assessment. The app's authored care protocols remain explicitly
unreviewed and are not relabeled as Ministry-approved advice.

## Dataset decision

The existing PlantVillage/PlantDoc image categories do not annotate treatment
efficacy, crop-stage-specific treatment, pesticide registration, remission or
validated recovery time. The reachable Spanish IPM CSVs are a small structured
knowledge resource, not outcome-labeled training examples. They do not justify
a supervised model claiming to predict a cure or a treatment-success percentage.
No new neural severity or treatment model was trained from these sources.

The appropriate upgrade is a versioned care-protocol system: expose the full
condition library; give distinct practical actions by disease; explain which
management protects new growth or limits spread; separate nonchemical actions
from product decisions requiring a valid local label; show what improvement
means; and provide follow-up checkpoints and failure/escalation signs.

## Recovery information to make explicit

These are product/content requirements for draft agronomic review, not measured
efficacy findings from the datasets:

- Existing dead or spotted leaf tissue usually does not return to normal. Monitor
  **new lesions, expanding lesions, new growth and spread to other plants** rather
  than promising that yesterday's brown spots disappear after treatment.
- For suspected late blight, expanding patches, stem symptoms or affected tubers
  warrant prompt confirmation and containment. Storage decisions must inspect
  tubers, not infer tuber health from one leaf photograph.
- Early blight, Septoria, target spot and maize foliar diseases need distinct
  canopy/splash/residue management and crop-stage context; a universal
  “remove every spotted leaf” instruction is inappropriate, especially in maize.
- Tomato leaf mold needs humidity, condensation and protected-cultivation airflow
  management. Spider mites need live-pest/underside/webbing checks and protection
  of natural enemies, not a fungal-disease spray recommendation.
- Bacterial spot requires transmission/hygiene management and confirmation;
  fungal disease products are not automatically suitable bacterial treatments.
- Tomato mosaic and yellow leaf curl have no curative in-plant antiviral spray.
  Distinguish contact/tool transmission management from whitefly-vector management.
  A guessed viral label must not automatically authorize destruction of plants.
- A follow-up date is an action/reassessment checkpoint, not a guaranteed cure
  deadline. Worsening or red flags should override any scheduled wait.

## Reproducible audit

Run `python3 tools/acquire_care_sources.py --output /tmp/care-source-audit`.
The tool records retrieved bytes, hashes, access failures, provenance, license,
and matched potato row IDs. Downloads remain research material. It neither
trains a model nor installs advice or third-party CSVs in the application.

Engineering tests can verify complete protocol coverage, language handling,
selection behavior, persistence and offline availability. They cannot establish
agronomic accuracy, treatment efficacy or a zero-error guarantee.

## Final authored-content consistency review

The treatment expansion was reviewed across all 17 English protocols and the
critical Kannada/Hindi viral, late-blight, mite and recovery sections. This was
a consistency review, not independent agronomist approval or native-speaker
certification. The frozen reviewed artifact has SHA-256
`a78b8b8bedb6836b1aa033c32089e846de3be20d583791075de515fc2d0e477a`.

The review checked for unsupported active ingredients/doses, promised cures or
fixed recovery deadlines, excessive maize defoliation, automatic destruction
from an uncertain diagnosis, and confusion between reassessment checkpoints
and spray intervals. No named active-ingredient prescription or dose was added.
Generic expert-led discussions remain conditional on the actual crop label and
local registration.

Issues corrected before narration was frozen:

- Removed unrelated late-blight boilerplate from other crop protocols.
- Made suspected late blight explicitly request same-day contact and inspection,
  without implying a 24–48-hour wait for help.
- Made viral no-curative-spray limitations and the mite/pest distinction audible.
- Qualified recovery statements as signs to look for, rather than guarantees.
- Clarified that urgent advice and low-risk care can start before disease-specific
  treatment confirmation; a healthy-looking image does not dismiss symptoms.

The resulting care pathways are more detailed authored information. These fixes
do not turn unavailable primary-source verification into verified evidence or
establish treatment efficacy.
