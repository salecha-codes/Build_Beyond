# MobileNetV3 healthy-field data update

Model SHA:`31b29158cc1fc1c07bdf3acc07cb6bb6da39eccb1050ffe6ed1d499811179fba`. Current disease head adds448audited Kandahar maize Healthy TRAIN photos to the previous6324PlantVillage+632PlantDoc TRAIN rows. Only maize Healthy is mapped to the existing taxonomy; new Blight/Spot labels are not used as exact disease labels. Backbone features and leaf-check output are unchanged, with exact runtime parity probes.

## Frozen results

Source3674 classifier accuracy92.27%, macro F1.91058. Reused PlantDoc field80:31/80=38.75% both before and after the leaf check, matching the prior model. Source acceptance criteria pass; selected-crop+score+leaf field predictions have20correct/34 delivered (58.82%), versus19/34before. This comparison set is reused, not newly blind data.

New locked maize Healthy fieldTEST14 (separate collection): control0/14 and candidate1/14 correct visible provisional prediction after the leaf check. Both have0/14 strict accepted Healthy result. Leaf check retains13/14. This is a small provisional gain, not a reliable field-health diagnosis. New VALID18 was used to select the head, so its1→5correct result is tuning evidence only. New test labels are source-provided and not independently verified by an agricultural expert.

## Input and product scope

The frozen leaf check retains the original object-rejection pathway, output and threshold. Bound leaf_validation.json contains original125-negative-test evidence marked reused with unchanged branch; export runtime probes confirm matching embeddings and leaf logits. Other crop leaves/objects can remain outside measured scope. No chemical treatment, image severity or field-diagnosis validation is claimed.

Graph outputs17disease scores,960features andleaf_logit[1,1]. The new source evaluation binds exact-model hashes and frozen CAL gates. Centroids use16,856PV+632PlantDoc+448Kandahar Healthy TRAIN images, with separate manifest/audit receipt identities. See ml/reports/healthy_field_update for provenance and separate test reports. Raw images/caches remain outside the repository and app.
