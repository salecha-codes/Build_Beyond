# Offline care and urgency model

This second model runs after disease recognition. It is a small expert decision
model with 17 trilingual knowledge profiles, not a neural network trained on
severity labels. PlantVillage supplies disease categories, not disease severity,
field spread, treatment outcomes or verified cure labels.

The model combines the leaf-supported candidate with six farmer observations:
visible damage, recent spread, affected plants, wilting, fruit/stem involvement
and wet weather. It separates reported severity from action urgency. A small
patch of suspected late blight can need same-day advice even when reported leaf
damage is mild. A high classifier score never makes damage severe.

The runtime implementations are `frontend/src/lib/advisory.ts` and the Android
advisory domain model. The canonical knowledge artifact is
[`content/advisory_model.json`](../../content/advisory_model.json). Package it with
`python3 tools/build_advisory_bundle.py`; the generated receipt records hashes,
model version, category/language coverage and explicit validation status.

Care is conditional on confirming the disease. Leaf/object rejection, a crop
mismatch, or a missing classifier cannot authorize disease-specific care.
Unanswered questions remain unknown. Healthy-looking predictions with reported
damage trigger rechecking rather than dismissing the farmer's observations.

The decision rules and translations are drafts requiring agronomist and native
speaker review. They do not guarantee a cure, measure lesion area, predict yield
loss, recommend pesticide doses or replace a crop examination. Viral profiles
explain that infected plants have no curative antiviral treatment; management
aims to prevent spread. Existing leaf damage does not heal after spraying.

See [research and source access status](../../docs/ADVISORY_RESEARCH.md) and
[model card](../../docs/ADVISORY_MODEL_CARD.md). The behavioral fixtures are hand
authored software checks, not training data or agricultural validation.
