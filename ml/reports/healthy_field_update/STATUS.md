# Targeted healthy-maize field update

Current model adds448audited real maize Healthy TRAIN photos; source Blight/Spot labels are not mapped to exact17-class disease labels. Backbone/leaf-path outputs remain unchanged. Sourceclassifier accuracy92.27%; sourceleaf+classifier92.11%. Existing reused PlantDoc80 stays31/80=38.75% afterleafgate. Delivered strict field conditions20/34correct versus19/34before.

New independent-collection Healthy TEST14 was opened once after candidate selection/old-field non-regression. Currentcontrol0/14 andcandidate1/14 correct visibleprovisional prediction; both0/14strict accepted Healthy. Leafgate passes13/14. This is a small provisionalgain and substantial field-generalization weakness, notvalidated maize-health diagnosis. New VALID18 improved1→5 butwasusedforselection, notfinalaccuracy.

Three-epoch box-tail and broad3class auxiliary-transfer attempts failed selection and were notdeployed. Healthy-only training usesexact compatible sourceHealthy+knownmaize labels. Allmain17-class labels are preserved. Rawimages/caches stayexternal; sourceGPL/imageprovenance limits are in ml/KANDAHAR_DATA.md.
