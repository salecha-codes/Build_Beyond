#!/usr/bin/env python3
"""Build traceable prototype content and real local speech; no network or treatment service at runtime."""
from __future__ import annotations
import argparse, ctypes, hashlib, json, pathlib, subprocess, tempfile, wave, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'android/app/src/main/assets'
VERSION = 'review2-observation-1'
# Technical symptom names/descriptions are prototype copy, not expert-reviewed management recommendations.
DATA = [
('maize_gray_leaf_spot','Gray leaf spot','ಬೂದು ಎಲೆ ಚುಕ್ಕೆ','Look for long, rectangular gray or brown marks between leaf veins.','ಎಲೆಯ ನರಗಳ ನಡುವೆ ಉದ್ದವಾದ ಬೂದು ಅಥವಾ ಕಂದು ಚುಕ್ಕೆಗಳನ್ನು ಗಮನಿಸಿ.'),
('maize_common_rust','Common rust','ಸಾಮಾನ್ಯ ತುಕ್ಕು ರೋಗ','Look for small raised rust-colored spots on the leaf surfaces.','ಎಲೆಯ ಮೇಲ್ಮೈಯಲ್ಲಿ ತುಕ್ಕಿನ ಬಣ್ಣದ ಸಣ್ಣ ಉಬ್ಬಿದ ಚುಕ್ಕೆಗಳನ್ನು ಗಮನಿಸಿ.'),
('maize_northern_leaf_blight','Northern leaf blight','ಉತ್ತರ ಎಲೆ ಅಂಗಮಾರಿ','Look for long gray-green or brown damaged areas. Similar symptoms can have other causes.','ಉದ್ದವಾದ ಬೂದು ಹಸಿರು ಅಥವಾ ಕಂದು ಹಾನಿಯ ಭಾಗಗಳನ್ನು ಗಮನಿಸಿ. ಇಂತಹ ಲಕ್ಷಣಗಳಿಗೆ ಬೇರೆ ಕಾರಣಗಳೂ ಇರಬಹುದು.'),
('maize_healthy','Healthy-looking leaf','ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವ ಎಲೆ','A healthy-looking photograph does not rule out hidden or unsupported conditions.','ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವ ಚಿತ್ರದಿಂದ ಕಾಣಿಸದ ಅಥವಾ ಬೆಂಬಲಿಸದ ಸಮಸ್ಯೆಗಳಿಲ್ಲ ಎಂದು ಖಚಿತಪಡಿಸಲಾಗುವುದಿಲ್ಲ.'),
('potato_early_blight','Early blight','ಆರಂಭಿಕ ಅಂಗಮಾರಿ','Look for brown marks with ring-like patterns, often on older leaves.','ಹಳೆಯ ಎಲೆಗಳಲ್ಲಿ ಉಂಗುರದಂತಹ ಕಂದು ಚುಕ್ಕೆಗಳನ್ನು ಗಮನಿಸಿ.'),
('potato_late_blight','Late blight','ತಡವಾದ ಅಂಗಮಾರಿ','Look for expanding dark damaged patches. Record how quickly symptoms change.','ಹರಡುತ್ತಿರುವ ಗಾಢ ಬಣ್ಣದ ಹಾನಿಯ ಭಾಗಗಳನ್ನು ಗಮನಿಸಿ. ಲಕ್ಷಣಗಳು ಎಷ್ಟು ಬೇಗ ಬದಲಾಗುತ್ತಿವೆ ಎಂದು ದಾಖಲಿಸಿ.'),
('potato_healthy','Healthy-looking leaf','ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವ ಎಲೆ','A healthy-looking photograph does not rule out hidden or unsupported conditions.','ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವ ಚಿತ್ರದಿಂದ ಕಾಣಿಸದ ಅಥವಾ ಬೆಂಬಲಿಸದ ಸಮಸ್ಯೆಗಳಿಲ್ಲ ಎಂದು ಖಚಿತಪಡಿಸಲಾಗುವುದಿಲ್ಲ.'),
('tomato_bacterial_spot','Bacterial spot','ಬ್ಯಾಕ್ಟೀರಿಯಾ ಎಲೆ ಚುಕ್ಕೆ','Look for small dark spots, sometimes with a yellow margin.','ಕೆಲವೊಮ್ಮೆ ಹಳದಿ ಅಂಚಿರುವ ಸಣ್ಣ ಕಪ್ಪು ಚುಕ್ಕೆಗಳನ್ನು ಗಮನಿಸಿ.'),
('tomato_early_blight','Early blight','ಆರಂಭಿಕ ಅಂಗಮಾರಿ','Look for brown marks with ring-like patterns, often on older leaves.','ಹಳೆಯ ಎಲೆಗಳಲ್ಲಿ ಉಂಗುರದಂತಹ ಕಂದು ಚುಕ್ಕೆಗಳನ್ನು ಗಮನಿಸಿ.'),
('tomato_late_blight','Late blight','ತಡವಾದ ಅಂಗಮಾರಿ','Look for expanding dark damaged patches. Record how quickly symptoms change.','ಹರಡುತ್ತಿರುವ ಗಾಢ ಬಣ್ಣದ ಹಾನಿಯ ಭಾಗಗಳನ್ನು ಗಮನಿಸಿ. ಲಕ್ಷಣಗಳು ಎಷ್ಟು ಬೇಗ ಬದಲಾಗುತ್ತಿವೆ ಎಂದು ದಾಖಲಿಸಿ.'),
('tomato_leaf_mold','Leaf mold','ಎಲೆಯ ಶಿಲೀಂಧ್ರ ಕಲೆ','Photograph both sides of the leaf and note yellow patches or unusual growth underneath.','ಎಲೆಯ ಎರಡೂ ಬದಿಗಳ ಚಿತ್ರ ತೆಗೆದು ಹಳದಿ ಕಲೆಗಳು ಅಥವಾ ಕೆಳಭಾಗದ ಅಸಾಮಾನ್ಯ ಬೆಳವಣಿಗೆಯನ್ನು ಗಮನಿಸಿ.'),
('tomato_septoria_leaf_spot','Septoria leaf spot','ಸೆಪ್ಟೋರಿಯಾ ಎಲೆ ಚುಕ್ಕೆ','Look for small round spots with a darker border and lighter center.','ಗಾಢ ಅಂಚು ಮತ್ತು ತಿಳಿ ಮಧ್ಯಭಾಗ ಇರುವ ಸಣ್ಣ ಗುಂಡಾದ ಚುಕ್ಕೆಗಳನ್ನು ಗಮನಿಸಿ.'),
('tomato_spider_mites','Two-spotted spider mites','ಎರಡು ಚುಕ್ಕೆ ಜೇಡನುಸಿ','Check the underside for fine webbing, tiny pests or many small pale speckles.','ಎಲೆಯ ಕೆಳಭಾಗದಲ್ಲಿ ಸೂಕ್ಷ್ಮ ಜಾಲ, ಸಣ್ಣ ಕೀಟಗಳು ಅಥವಾ ತಿಳಿ ಚುಕ್ಕೆಗಳನ್ನು ಗಮನಿಸಿ.'),
('tomato_target_spot','Target spot','ಗುರಿ ಆಕಾರದ ಎಲೆ ಚುಕ್ಕೆ','Look for brown circular marks; similar rings can occur in several conditions.','ಕಂದು ಗುಂಡಾದ ಚುಕ್ಕೆಗಳನ್ನು ಗಮನಿಸಿ. ಇಂತಹ ಉಂಗುರದ ಗುರುತುಗಳು ಹಲವು ಸಮಸ್ಯೆಗಳಲ್ಲಿ ಕಾಣಬಹುದು.'),
('tomato_yellow_leaf_curl_virus','Yellow leaf curl virus','ಹಳದಿ ಎಲೆ ಸುರುಳಿ ವೈರಸ್','Note yellowing, curled leaves and changes in new growth. These signs are not unique.','ಹಳದಿ ಬಣ್ಣ, ಸುರುಳಿಯಾದ ಎಲೆಗಳು ಮತ್ತು ಹೊಸ ಬೆಳವಣಿಗೆಯ ಬದಲಾವಣೆಗಳನ್ನು ಗಮನಿಸಿ. ಈ ಲಕ್ಷಣಗಳು ಒಂದೇ ರೋಗಕ್ಕೆ ಸೀಮಿತವಲ್ಲ.'),
('tomato_mosaic_virus','Mosaic virus','ಮೊಸಾಯಿಕ್ ವೈರಸ್','Note uneven light and dark green patterns and distorted leaves.','ಅಸಮವಾದ ತಿಳಿ ಮತ್ತು ಗಾಢ ಹಸಿರು ಗುರುತುಗಳು ಹಾಗೂ ವಿಕೃತ ಎಲೆಗಳನ್ನು ಗಮನಿಸಿ.'),
('tomato_healthy','Healthy-looking leaf','ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವ ಎಲೆ','A healthy-looking photograph does not rule out hidden or unsupported conditions.','ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವ ಚಿತ್ರದಿಂದ ಕಾಣಿಸದ ಅಥವಾ ಬೆಂಬಲಿಸದ ಸಮಸ್ಯೆಗಳಿಲ್ಲ ಎಂದು ಖಚಿತಪಡಿಸಲಾಗುವುದಿಲ್ಲ.'),
]
PROMPTS = {
'uncertain':('Let’s take another look','The model is not validated for diagnosis yet. Take a clear close-up of one leaf in daylight. Save this observation and consult a local agriculture adviser if symptoms spread.','ಮತ್ತೊಮ್ಮೆ ಪರಿಶೀಲಿಸೋಣ','ಈ ಮಾದರಿಯನ್ನು ರೋಗ ನಿರ್ಣಯಕ್ಕಾಗಿ ಇನ್ನೂ ಪರಿಶೀಲಿಸಲಾಗಿಲ್ಲ. ಹಗಲಿನ ಬೆಳಕಿನಲ್ಲಿ ಒಂದು ಎಲೆಯ ಸ್ಪಷ್ಟ ಚಿತ್ರ ತೆಗೆದುಕೊಳ್ಳಿ. ಲಕ್ಷಣಗಳು ಹರಡಿದರೆ ಸ್ಥಳೀಯ ಕೃಷಿ ಸಲಹೆಗಾರರನ್ನು ಸಂಪರ್ಕಿಸಿ.'),
'retake':('Try a clearer photo','Hold the phone steady. Place one leaf in the frame, use natural light and avoid shadows.','ಸ್ಪಷ್ಟವಾದ ಚಿತ್ರ ತೆಗೆದುಕೊಳ್ಳಿ','ಫೋನನ್ನು ಸ್ಥಿರವಾಗಿ ಹಿಡಿಯಿರಿ. ಒಂದು ಎಲೆಯನ್ನು ಚೌಕಟ್ಟಿನಲ್ಲಿ ಇರಿಸಿ. ಸಹಜ ಬೆಳಕನ್ನು ಬಳಸಿ ನೆರಳನ್ನು ತಪ್ಪಿಸಿ.'),
'offline':('Works offline','Assessment, guidance and audio work on this phone without internet. Sharing or calling may need a connection.','ಇಂಟರ್ನೆಟ್ ಇಲ್ಲದೆ ಕೆಲಸ ಮಾಡುತ್ತದೆ','ಪರಿಶೀಲನೆ, ಮಾರ್ಗದರ್ಶನ ಮತ್ತು ಧ್ವನಿ ಈ ಫೋನಿನಲ್ಲಿ ಇಂಟರ್ನೆಟ್ ಇಲ್ಲದೆ ಕೆಲಸ ಮಾಡುತ್ತವೆ. ಹಂಚಿಕೊಳ್ಳಲು ಅಥವಾ ಕರೆ ಮಾಡಲು ಸಂಪರ್ಕ ಬೇಕಾಗಬಹುದು.'),
'crop_mismatch':('Check the selected crop','Check which crop you selected and take another clear photo. The prototype model’s crop prediction is not a confirmed identification.','ಆಯ್ಕೆ ಮಾಡಿದ ಬೆಳೆ ಪರಿಶೀಲಿಸಿ','ನೀವು ಆಯ್ಕೆ ಮಾಡಿದ ಬೆಳೆಯನ್ನು ಪರಿಶೀಲಿಸಿ ಮತ್ತೊಂದು ಸ್ಪಷ್ಟ ಚಿತ್ರ ತೆಗೆದುಕೊಳ್ಳಿ. ಈ ಮಾದರಿಯ ಬೆಳೆ ಊಹೆ ಖಚಿತ ಗುರುತಿಸುವಿಕೆ ಅಲ್ಲ.'),
'model_unavailable':('Model not available','The packaged model is not ready, so this photo cannot be assessed. You can still read photo tips and save an observation.','ಮಾದರಿ ಲಭ್ಯವಿಲ್ಲ','ಫೋನಿನ ಮಾದರಿ ಸಿದ್ಧವಾಗಿಲ್ಲ. ಆದ್ದರಿಂದ ಈ ಚಿತ್ರವನ್ನು ಪರಿಶೀಲಿಸಲಾಗುವುದಿಲ್ಲ. ಚಿತ್ರ ತೆಗೆಯುವ ಸಲಹೆಗಳನ್ನು ಓದಿ ವೀಕ್ಷಣೆಯನ್ನು ಉಳಿಸಬಹುದು.'),
'model_prototype':('Prototype assessment','Scores are experimental model output, not a confirmed disease diagnosis.','ಮಾದರಿ ಪರಿಶೀಲನೆ','ಅಂಕಗಳು ಪ್ರಾಯೋಗಿಕ ಮಾದರಿಯ ಫಲಿತಾಂಶಗಳು. ಅವು ಖಚಿತ ರೋಗ ನಿರ್ಣಯವಲ್ಲ.'),
'healthy':('Healthy-looking photo','No supported signs were identified in this photograph. Keep monitoring; a photo cannot rule out every problem.','ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವ ಚಿತ್ರ','ಈ ಚಿತ್ರದಲ್ಲಿ ಬೆಂಬಲಿತ ಲಕ್ಷಣಗಳು ಗುರುತಿಸಲ್ಪಟ್ಟಿಲ್ಲ. ಗಮನಿಸುವುದನ್ನು ಮುಂದುವರಿಸಿ. ಒಂದು ಚಿತ್ರದಿಂದ ಎಲ್ಲಾ ಸಮಸ್ಯೆಗಳನ್ನೂ ತಳ್ಳಿಹಾಕಲಾಗುವುದಿಲ್ಲ.'),
'concern_spreading':('Are symptoms spreading?','Have the marks spread quickly since your last observation?','ಲಕ್ಷಣಗಳು ಹರಡುತ್ತಿವೆಯೇ?','ಹಿಂದಿನ ವೀಕ್ಷಣೆಯಿಂದ ಈ ಗುರುತುಗಳು ಬೇಗ ಹರಡಿವೆಯೇ?'),
'concern_coverage':('How much of the leaf has spots?','Choose the area you can see: a few spots, some spots or many spots. This is your observation, not an AI measurement.','ಎಲೆಯ ಎಷ್ಟು ಭಾಗದಲ್ಲಿ ಚುಕ್ಕೆಗಳಿವೆ?','ನಿಮಗೆ ಕಾಣುವ ಭಾಗವನ್ನು ಆಯ್ಕೆ ಮಾಡಿ. ಕಡಿಮೆ ಚುಕ್ಕೆಗಳು, ಕೆಲವು ಚುಕ್ಕೆಗಳು ಅಥವಾ ಹೆಚ್ಚು ಚುಕ್ಕೆಗಳು. ಇದು ನಿಮ್ಮ ವೀಕ್ಷಣೆ. ಕೃತಕ ಬುದ್ಧಿಮತ್ತೆಯ ಅಳತೆಯಲ್ಲ.'),
'concern_plants':('Are nearby plants affected?','Check whether several nearby plants have similar symptoms.','ಹತ್ತಿರದ ಸಸ್ಯಗಳಿಗೂ ಸಮಸ್ಯೆಯಿದೆಯೇ?','ಹತ್ತಿರದ ಹಲವು ಸಸ್ಯಗಳಲ್ಲಿ ಇದೇ ರೀತಿಯ ಲಕ್ಷಣಗಳಿವೆಯೇ ಎಂದು ಪರಿಶೀಲಿಸಿ.'),
'concern_expert':('Check with a local expert','You reported spreading symptoms, many spots, affected plants or wilting. Keep photos and ask a local agriculture adviser to review them. This is not a confirmed severity grade.','ಸ್ಥಳೀಯ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ','ಹರಡುವ ಲಕ್ಷಣಗಳು, ಹೆಚ್ಚು ಚುಕ್ಕೆಗಳು, ಬಾಧಿತ ಸಸ್ಯಗಳು ಅಥವಾ ಬಾಡುವಿಕೆ ಇದೆ ಎಂದು ನೀವು ತಿಳಿಸಿದ್ದೀರಿ. ಚಿತ್ರಗಳನ್ನು ಉಳಿಸಿ ಸ್ಥಳೀಯ ಕೃಷಿ ಸಲಹೆಗಾರರಿಂದ ಪರಿಶೀಲಿಸಿಕೊಳ್ಳಿ. ಇದು ಖಚಿತ ತೀವ್ರತೆಯ ಅಂಕವಲ್ಲ.'),
'concern_observe':('Record and recheck','Record symptoms and watch for changes. If they worsen, contact a local agriculture adviser. This checklist does not diagnose a disease or measure its severity.','ದಾಖಲಿಸಿ ಮತ್ತೆ ಗಮನಿಸಿ','ಲಕ್ಷಣಗಳನ್ನು ದಾಖಲಿಸಿ ಬದಲಾವಣೆಗಳನ್ನು ಗಮನಿಸಿ. ಅವು ಹೆಚ್ಚಾದರೆ ಸ್ಥಳೀಯ ಕೃಷಿ ಸಲಹೆಗಾರರನ್ನು ಸಂಪರ್ಕಿಸಿ. ಈ ಪ್ರಶ್ನಾವಳಿ ರೋಗ ನಿರ್ಣಯ ಅಥವಾ ತೀವ್ರತೆಯ ಅಳತೆ ಮಾಡುವುದಿಲ್ಲ.'),
'check_expert':('Check before treatment','Do not choose a pesticide or dosage from this prototype result. Confirm the condition and appropriate action with a local agriculture adviser.','ಚಿಕಿತ್ಸೆಗೆ ಮೊದಲು ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ','ಈ ಮಾದರಿಯ ಫಲಿತಾಂಶದಿಂದ ಕೀಟನಾಶಕ ಅಥವಾ ಪ್ರಮಾಣವನ್ನು ಆಯ್ಕೆ ಮಾಡಬೇಡಿ. ಸ್ಥಳೀಯ ಕೃಷಿ ಸಲಹೆಗಾರರಿಂದ ಸಮಸ್ಯೆ ಮತ್ತು ಸರಿಯಾದ ಕ್ರಮವನ್ನು ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ.'),
}

UI_EN = {'home':'Home','help':'Help','scan_leaf':'Scan a leaf','select_crop':'Select your crop','take_photo':'Take photo','choose_photo':'Choose photo','listen':'Listen','pause':'Pause','replay':'Replay','retake':'Retake photo','save':'Save observation','delete':'Delete','history':'Recent scans','do_now':'Do now','expert_check':'Check with an expert','precaution':'Precaution','prototype':'Prototype','offline':'Offline','concern_check':'Symptom check','next':'Next','yes':'Yes','no':'No','few_spots':'A few spots (<10%)','some_spots':'Some spots (10–30%)','many_spots':'Many spots (>30%)','not_reported':'Not sure','review_pending':'General observation guidance; expert review pending.'}
UI_KN = {'home':'ಮುಖಪುಟ','help':'ಸಹಾಯ','scan_leaf':'ಎಲೆಯನ್ನು ಪರಿಶೀಲಿಸಿ','select_crop':'ನಿಮ್ಮ ಬೆಳೆ ಆಯ್ಕೆ ಮಾಡಿ','take_photo':'ಚಿತ್ರ ತೆಗೆದುಕೊಳ್ಳಿ','choose_photo':'ಚಿತ್ರ ಆಯ್ಕೆ ಮಾಡಿ','listen':'ಕೇಳಿ','pause':'ನಿಲ್ಲಿಸಿ','replay':'ಮತ್ತೆ ಕೇಳಿ','retake':'ಮತ್ತೆ ಚಿತ್ರ ತೆಗೆಯಿರಿ','save':'ವೀಕ್ಷಣೆ ಉಳಿಸಿ','delete':'ಅಳಿಸಿ','history':'ಇತ್ತೀಚಿನ ಪರಿಶೀಲನೆಗಳು','do_now':'ಈಗ ಮಾಡಬೇಕಾದುದು','expert_check':'ತಜ್ಞರಿಂದ ಪರಿಶೀಲಿಸಿಕೊಳ್ಳಿ','precaution':'ಮುನ್ನೆಚ್ಚರಿಕೆ','prototype':'ಪ್ರಾಯೋಗಿಕ ಮಾದರಿ','offline':'ಇಂಟರ್ನೆಟ್ ಇಲ್ಲದೆ','concern_check':'ಲಕ್ಷಣಗಳ ಪರಿಶೀಲನೆ','next':'ಮುಂದೆ','yes':'ಹೌದು','no':'ಇಲ್ಲ','few_spots':'ಕಡಿಮೆ ಚುಕ್ಕೆಗಳು (10% ಕ್ಕಿಂತ ಕಡಿಮೆ)','some_spots':'ಕೆಲವು ಚುಕ್ಕೆಗಳು (10–30%)','many_spots':'ಹೆಚ್ಚು ಚುಕ್ಕೆಗಳು (30% ಕ್ಕಿಂತ ಹೆಚ್ಚು)','not_reported':'ಖಚಿತವಿಲ್ಲ','review_pending':'ಸಾಮಾನ್ಯ ವೀಕ್ಷಣೆಯ ಮಾರ್ಗದರ್ಶನ. ತಜ್ಞರ ಪರಿಶೀಲನೆ ಬಾಕಿಯಿದೆ.'}

def build_catalog():
    conditions={};speech=[]
    for cid,en,kn,sym_en,sym_kn in DATA:
        healthy=cid.endswith('_healthy')
        actions_en=['Take clear photos of the top and underside of one leaf in daylight.','Record when the marks began and whether nearby plants show similar changes.','Keep this observation for a local agriculture adviser to review.']
        actions_kn=['ಹಗಲಿನ ಬೆಳಕಿನಲ್ಲಿ ಒಂದು ಎಲೆಯ ಮೇಲ್ಭಾಗ ಮತ್ತು ಕೆಳಭಾಗದ ಸ್ಪಷ್ಟ ಚಿತ್ರಗಳನ್ನು ತೆಗೆದುಕೊಳ್ಳಿ.','ಗುರುತುಗಳು ಯಾವಾಗ ಆರಂಭವಾದವು ಮತ್ತು ಹತ್ತಿರದ ಸಸ್ಯಗಳಲ್ಲೂ ಬದಲಾವಣೆಗಳಿವೆಯೇ ಎಂದು ದಾಖಲಿಸಿ.','ಸ್ಥಳೀಯ ಕೃಷಿ ಸಲಹೆಗಾರರ ಪರಿಶೀಲನೆಗಾಗಿ ಈ ವೀಕ್ಷಣೆಯನ್ನು ಉಳಿಸಿ.']
        caution_en='Prototype observation guidance. Confirm the condition with a local agriculture adviser before choosing treatment.'
        caution_kn='ಇದು ಮಾದರಿ ವೀಕ್ಷಣೆಯ ಮಾರ್ಗದರ್ಶನ. ಚಿಕಿತ್ಸೆ ಆಯ್ಕೆ ಮಾಡುವ ಮೊದಲು ಸ್ಥಳೀಯ ಕೃಷಿ ಸಲಹೆಗಾರರಿಂದ ಸಮಸ್ಯೆಯನ್ನು ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ.'
        copies={}
        for lang,name,sym,actions,caution in [('en',en,sym_en,actions_en,caution_en),('kn',kn,sym_kn,actions_kn,caution_kn)]:
            audio=f'audio/{lang}/{cid}.ogg'
            if lang=='en':
                summary=('Healthy-looking is not a guarantee of plant health.' if healthy else f'Reference signs to check for {name}. A photograph alone cannot confirm the condition.')
                prevention=['Continue observing the plant and note changes before taking further action.']
                spoken=f'{name}. {sym} {actions[0]} {caution}'
            else:
                summary=('ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವುದು ಸಸ್ಯದ ಸಂಪೂರ್ಣ ಆರೋಗ್ಯದ ಖಾತರಿಯಲ್ಲ.' if healthy else f'{name} ಲಕ್ಷಣಗಳನ್ನು ಪರಿಶೀಲಿಸುವ ಮಾರ್ಗದರ್ಶನ. ಒಂದು ಚಿತ್ರದಿಂದ ಸಮಸ್ಯೆಯನ್ನು ಖಚಿತಪಡಿಸಲಾಗುವುದಿಲ್ಲ.')
                prevention=['ಮುಂದಿನ ಕ್ರಮಕ್ಕೆ ಮೊದಲು ಸಸ್ಯವನ್ನು ಗಮನಿಸಿ ಬದಲಾವಣೆಗಳನ್ನು ದಾಖಲಿಸಿ.']
                spoken=f'{name}. {sym} {actions[0]} {caution}'
            copies[lang]={'name':name,'summary':summary,'symptoms':[sym],'actions':actions,'prevention':prevention,'caution':caution,'audio_asset':audio,'translation_status':'original_prototype_copy' if lang=='en' else 'draft_not_native_reviewed'}
            speech.append((lang,audio,spoken))
        conditions[cid]={'review_status':'general_observation_only_not_expert_reviewed','chemical_treatment_enabled':False,'sources':[{'id':'plantvillage_taxonomy','title':'PlantVillage label taxonomy — not treatment guidance','url':'https://github.com/spMohanty/PlantVillage-Dataset','verification_status':'taxonomy_only'}],'translations':copies}
    prompts={}
    for key,(te,me,tk,mk) in PROMPTS.items():
        prompts[key]={}
        for lang,title,message in [('en',te,me),('kn',tk,mk)]:
            audio=f'audio/{lang}/prompt_{key}.ogg';prompts[key][lang]={'title':title,'message':message,'audio_asset':audio};speech.append((lang,audio,message))
    result={'schema_version':1,'content_version':VERSION,'review_notice':'Prototype observation guidance, not expert-reviewed treatment. Kannada translation and pronunciation review remain pending.','conditions':conditions,'prompts':prompts,'ui_strings':{'en':UI_EN,'kn':UI_KN},'primary_advisory_access':[{'url':'https://ipm.ucanr.edu/agriculture/','status':'blocked_by_environment_proxy_not_read'},{'url':'https://agritech.tnau.ac.in/','status':'blocked_by_environment_proxy_not_read'}]}
    # Additive language source: keep the existing English/Kannada records unchanged.
    hindi_path=ROOT/'content/hindi.source.json'
    if hindi_path.exists():
        hindi=json.loads(hindi_path.read_text())
        if set(hindi['conditions']) != set(conditions) or set(hindi['prompts']) != set(prompts):
            raise ValueError('Hindi guidance/prompt keys must match the existing catalog exactly')
        for cid,copy in hindi['conditions'].items():result['conditions'][cid]['translations']['hi']=copy
        for key,copy in hindi['prompts'].items():result['prompts'][key]['hi']=copy
        result['ui_strings']['hi']=hindi['ui_strings']
        result['language_reviews']={'hi':hindi['review_status']}
        for asset,text in hindi['spoken_scripts'].items():speech.append(('hi',asset,text))
        hindi_ui_path=ROOT/'content/hindi_ui.json'
        if hindi_ui_path.exists():
            hindi_ui=json.loads(hindi_ui_path.read_text())
            result['ui_english']={'hi':hindi_ui}
            ui_target=ASSETS/'content/hindi_ui.json';ui_target.parent.mkdir(parents=True,exist_ok=True)
            ui_target.write_text(json.dumps(hindi_ui,ensure_ascii=False,indent=2)+'\n')
    target=ASSETS/'content/catalog.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (ROOT/'content/catalog.source.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result,speech

class Synthesizer:
    def __init__(self):
        import espeakng_loader
        self.lib=ctypes.CDLL(espeakng_loader.get_library_path());self.buffers=[]
        callback=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.POINTER(ctypes.c_short),ctypes.c_int,ctypes.c_void_p)
        def collect(data,count,events):
            if data and count>0:self.buffers.append(ctypes.string_at(data,count*2))
            return 0
        self.callback=callback(collect)
        self.lib.espeak_Initialize.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_char_p,ctypes.c_int]
        self.sample_rate=self.lib.espeak_Initialize(2,0,str(espeakng_loader.get_data_path()).encode(),0)
        if self.sample_rate<=0:raise RuntimeError('Speech engine initialization failed')
        self.lib.espeak_SetSynthCallback.argtypes=[callback];self.lib.espeak_SetSynthCallback(self.callback)
        self.lib.espeak_SetVoiceByName.argtypes=[ctypes.c_char_p]
        self.lib.espeak_SetParameter.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int]
        self.lib.espeak_Synth.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint,ctypes.c_int,ctypes.c_uint,ctypes.c_uint,ctypes.POINTER(ctypes.c_uint),ctypes.c_void_p]
    def write(self,lang,text,path):
        self.buffers=[]
        if self.lib.espeak_SetVoiceByName(lang.encode())!=0:raise RuntimeError(f'Voice unavailable: {lang}')
        self.lib.espeak_SetParameter(1,145 if lang=='kn' else 155,0)
        buffer=ctypes.create_string_buffer(text.encode('utf-8'));ident=ctypes.c_uint()
        code=self.lib.espeak_Synth(buffer,len(buffer),0,1,0,1|0x1000,ctypes.byref(ident),None)
        if code!=0:raise RuntimeError(f'Synthesis failed {code}')
        self.lib.espeak_Synchronize()
        pcm=b''.join(self.buffers)
        if len(pcm)<1000:raise RuntimeError('No speech samples produced')
        with tempfile.TemporaryDirectory() as temp:
            wav=pathlib.Path(temp)/'speech.wav'
            with wave.open(str(wav),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(self.sample_rate);out.writeframes(pcm)
            path.parent.mkdir(parents=True,exist_ok=True)
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(wav),'-c:a','libvorbis','-b:a','32k',str(path)],check=True)
        return len(pcm)/2/self.sample_rate

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skip-audio',action='store_true');parser.add_argument('--legacy-espeak',action='store_true',help='Explicitly regenerate the former robotic prototype voice; current neural clips are preserved by default.');parser.add_argument('--audio-python-path',type=pathlib.Path);args=parser.parse_args()
    if args.audio_python_path:sys.path.insert(0,str(args.audio_python_path))
    catalog,speech=build_catalog();rows=[]
    if args.legacy_espeak and not args.skip_audio:
        synth=Synthesizer()
        for lang,asset,text in speech:
            path=ASSETS/asset;duration=synth.write(lang,text,path)
            rows.append({'path':asset,'language':lang,'duration_seconds':round(duration,3),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_text_sha256':hashlib.sha256(text.encode()).hexdigest(),'engine':'eSpeak NG via espeakng-loader 0.2.4','review':'technical_decode_checked;native_pronunciation_review_pending'})
        (ASSETS/'content/audio_manifest.json').write_text(json.dumps({'schema_version':1,'content_version':VERSION,'clips':rows},ensure_ascii=False,indent=2))
    print(json.dumps({'conditions':len(catalog['conditions']),'prompts':len(catalog['prompts']),'clips':len(rows),'audio_bytes':sum(x['bytes'] for x in rows)}))
if __name__=='__main__':main()
