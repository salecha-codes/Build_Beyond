# Existing crop-diagnosis apps — preliminary comparison

The Review 1 research-gap slide now compares actual products instead of model papers/datasets. Named examples are Plantix, Agrio and PlantVillage Nuru.

**Evidence boundary:** direct requests to the apps' primary sites and Plantix's Google Play page returned proxy tunnel 403 errors. Current versions, feature matrices, language coverage, pricing and accuracy claims were not retrieved or hands-on tested. The broad product descriptions below are general reference descriptions, not a verified current inventory. GitHub repository discovery did not provide authoritative product documentation; unrelated similarly named projects were not treated as official apps.

| App | General product focus | Constraint or comparison question |
|---|---|---|
| Plantix | Photo-based crop diagnosis and crop-care information | Verify whether diagnosis, advice and Kannada audio all work without connectivity on the installed version. Obtain comparable independent validation before discussing relative accuracy. |
| Agrio | Plant-health diagnosis, monitoring and alerts | Live monitoring needs updated information; this does not establish that diagnosis itself is online-only. Verify offline behavior and regional spoken guidance. |
| PlantVillage Nuru | Established offline diagnosis for supported crop conditions | Offline inference is already an existing capability. Compare the current crop/disease taxonomy and Kannada/audio support with our target workflow. |

## Claims not justified by this research

- That all existing crop apps need internet.
- That Plantix, Agrio or Nuru lack regional languages or Kannada.
- That competitors report false accuracy or have a particular error rate.
- That our untrained model is more accurate than an existing product.
- That our proposed feature combination is unique in the market.

App-store user complaints alone would not establish a general model error rate. A fair accuracy comparison needs the same compatible classes, independently labeled images, declared test protocol and actual outputs from the tested versions.

## What to measure in our prototype

Complete installed scan-to-text/audio behavior in airplane mode; understandable photo-quality and uncertainty states; English/Kannada guidance; actual latency/memory on a 3–4 GB RAM phone; and transparent per-class/external-image results. These are proposed outcomes, not competitor deficiencies asserted without evidence.

## Primary pages to verify when access is available

- https://plantix.net/en/
- https://play.google.com/store/apps/details?id=com.peat.GartenBank
- https://agrio.app/
- https://plantvillage.psu.edu/

For each version, record diagnosis connectivity, offline guidance/audio, supported crops, supported text/speech languages, uncertainty behavior, device requirements and accessible validation evidence. Mark missing information as unknown rather than absent. No environment configuration was changed or published to create this comparison.
