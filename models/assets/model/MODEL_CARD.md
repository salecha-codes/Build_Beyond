# MobileNetV3 healthy-field data update

Model SHA:`31b29158cc1fc1c07bdf3acc07cb6bb6da39eccb1050ffe6ed1d499811179fba`. Current disease head adds448audited Kandahar maize Healthy TRAIN photos to the previous6324PlantVillage+632PlantDoc TRAIN rows. Only maize Healthy is mapped to the existing taxonomy; new Blight/Spot labels are not used as exact disease labels. Backbone features and leaf-check output are unchanged, with exact runtime parity probes.

## Frozen results

Source3674 classifier accuracy92.27%, macro F1.91058. Reused PlantDoc field80:31/80=38.75% both before and after the leaf check, matching the prior model. Source acceptance criteria pass; selected-crop+score+leaf field predictions have20correct/34 delivered (58.82%), versus19/34before. This comparison set is reused, not newly blind data.

New locked maize Healthy fieldTEST14 (separate collection): control0/14 and candidate1/14 correct visible provisional prediction after the leaf check. Both have0/14 strict accepted Healthy result. Leaf check retains13/14. This is a small provisional gain, not a reliable field-health diagnosis. New VALID18 was used to select the head, so its1→5correct result is tuning evidence only. New test labels are source-provided and not independently verified by an agricultural expert.

## Input and product scope

The frozen leaf check retains the original object-rejection pathway, output and threshold. Bound leaf_validation.json contains original125-negative-test evidence marked reused with unchanged branch; export runtime probes confirm matching embeddings and leaf logits. Other crop leaves/objects can remain outside measured scope. No chemical treatment, image severity or field-diagnosis validation is claimed.

Graph outputs17disease scores,960features andleaf_logit[1,1]. The new source evaluation binds exact-model hashes and frozen CAL gates. Centroids use16,856PV+632PlantDoc+448Kandahar Healthy TRAIN images, with separate manifest/audit receipt identities. See ml/reports/healthy_field_update for provenance and separate test reports. Raw images/caches remain outside the repository and app.


## Diagnosis workflow correction

Disease graph, head weights and classifier source-evaluation gates are unchanged. Leaf threshold search was corrected to examine all TUNE score intervals rather than only a positive-recall cutoff per regularization setting. The active frozen threshold is0.4514392108851361. New leaf_validation.json links the unchanged classifier-only source evaluation and preserves its historical original-leaf-report hash; original receipts are archived in ml/reports/diagnosis_workflow_fix. Reused comparison: field leaves77/80 retained (previous76), source3674/3674 retained (previous3668), nonleaf125/125 stillrejected. These reused results do not certify every image.

Only after the binary leaf check passes, unfamiliar disease outputs remain visible as explicitly uncertain model candidates; no crop/disease confidence gates are falsely marked accepted. Object rejection still returns no disease candidates. Minimum capture dimension128px (recommended224px orlarger); blur/exposure checks remain. The updated service worker refreshes older cached pages when a new offline bundle replaces them so stale code cannot bypass the active leaf check.
