#!/usr/bin/env python3
"""Build the Review 2 report from actual model receipts; never run model inference.

Example:
  python3 scripts/build-review2-report.py --bundle /external/final_bundle \
    --reports ml/reports/review2_full --runtime-evidence dist/evidence/model-retraining-validation.json

Missing evaluation/runtime evidence is printed as pending. --draft marks every page.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]
W, H = A4
M = 44
CW = W - 2 * M
PURPLE = colors.HexColor('#4e2c99')
INK = colors.HexColor('#251448')
MUTED = colors.HexColor('#625a70')
LAVENDER = colors.HexColor('#f5f1fb')
LINE = colors.HexColor('#ded5ec')
GREEN = colors.HexColor('#4e7a50')
GOLD = colors.HexColor('#aa7a24')
PALE_GOLD = colors.HexColor('#fff6e3')
WHITE = colors.white


def load(path: Path | None) -> dict:
    return json.loads(path.read_text()) if path and path.is_file() else {}


def pct(value, digits=2):
    return f'{float(value) * 100:.{digits}f}%' if value is not None else 'Pending'


def number(value):
    return f'{int(value):,}' if value is not None else 'Pending'


def find_metric_file(bundle: Path, reports: Path | None):
    paths = [bundle / 'source_evaluation.json']
    if reports:
        paths += [reports / 'source_evaluation.json', reports / 'source_evaluation_receipt.json']
    return next((path for path in paths if path.is_file()), None)


class Report:
    def __init__(self, output: Path, draft: bool):
        output.parent.mkdir(parents=True, exist_ok=True)
        self.c = canvas.Canvas(str(output), pagesize=A4, pageCompression=1)
        self.c.setTitle('Offline Crop Health — Review 2 Technical Report')
        self.c.setAuthor('Team Debuggers · Build Beyond 26')
        self.draft = draft
        self.page_number = 0
        for name, filename in [('Body', 'OpenSans-Regular.ttf'), ('Strong', 'OpenSans-Semibold.ttf'), ('Light', 'OpenSans-Light.ttf')]:
            path = Path('/usr/share/fonts/truetype/open-sans') / filename
            if path.is_file():
                pdfmetrics.registerFont(TTFont(name, str(path)))
        self.body_font = 'Body' if 'Body' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
        self.strong_font = 'Strong' if 'Strong' in pdfmetrics.getRegisteredFontNames() else 'Helvetica-Bold'
        self.light_font = 'Light' if 'Light' in pdfmetrics.getRegisteredFontNames() else self.body_font

    def text(self, text, x=M, y=150, width=CW, size=12, leading=17, color=INK, strong=False):
        style = ParagraphStyle('p', fontName=self.strong_font if strong else self.body_font,
                               fontSize=size, leading=leading, textColor=color, alignment=TA_LEFT,
                               spaceAfter=0, splitLongWords=True)
        paragraph = Paragraph(str(text), style)
        _, height = paragraph.wrap(width, H)
        paragraph.drawOn(self.c, x, H-y-height)
        return y + height

    def rect(self, x, y, width, height, fill=LAVENDER, radius=14, stroke=None):
        self.c.setFillColor(fill)
        self.c.setStrokeColor(stroke or fill)
        self.c.roundRect(x, H-y-height, width, height, radius, fill=1, stroke=bool(stroke))

    def arrow(self, x1, y1, x2, y2, color=colors.HexColor('#afa5bd')):
        import math
        self.c.setStrokeColor(color)
        self.c.setFillColor(color)
        self.c.setLineWidth(1.2)
        self.c.line(x1, H-y1, x2, H-y2)
        angle = math.atan2(y2-y1, x2-x1)
        size = 5
        left = (x2-size*math.cos(angle-.45), y2-size*math.sin(angle-.45))
        right = (x2-size*math.cos(angle+.45), y2-size*math.sin(angle+.45))
        path = self.c.beginPath()
        path.moveTo(x2, H-y2); path.lineTo(left[0], H-left[1]); path.lineTo(right[0], H-right[1]); path.close()
        self.c.drawPath(path, fill=1, stroke=0)

    def page(self, title, subtitle='', section=''):
        if self.page_number:
            self.c.showPage()
        self.page_number += 1
        self.c.setFillColor(WHITE); self.c.rect(0, 0, W, H, fill=1, stroke=0)
        self.c.setFillColor(PURPLE); self.c.rect(0, H-9, W, 9, fill=1, stroke=0)
        self.text(f'BUILD BEYOND 26  /  REVIEW 2  /  {section.upper()}', y=35, size=9.5, leading=13, color=PURPLE)
        self.text(title, y=64, size=25, leading=31, color=INK)
        if subtitle:
            self.text(subtitle, y=108, size=12, leading=17, color=MUTED)
        self.c.setStrokeColor(LINE); self.c.line(M, 38, W-M, 38)
        self.text('Team Debuggers · PS 4.1', y=H-29, size=9.3, leading=12, color=MUTED)
        self.text(f'{self.page_number:02d} / 08', x=W-M-55, y=H-29, width=55, size=9.3, leading=12, color=MUTED)
        if self.draft:
            self.text('DRAFT · runtime evidence may still be pending', x=M+160, y=H-29, width=290, size=8.8, leading=12, color=GOLD)

    def card(self, x, y, width, height, title, body, accent=PURPLE, fill=LAVENDER):
        self.rect(x, y, width, height, fill)
        self.c.setFillColor(accent); self.c.roundRect(x, H-y-height, 4, height, 2, fill=1, stroke=0)
        end = self.text(title, x=x+16, y=y+14, width=width-32, size=13, leading=18, strong=True)
        self.text(body, x=x+16, y=end+8, width=width-32, size=11.7, leading=16.4, color=MUTED)

    def node(self, x, y, width, height, title, body='', purple=False):
        self.rect(x, y, width, height, PURPLE if purple else LAVENDER, radius=12)
        end = self.text(title, x=x+14, y=y+10, width=width-28, size=12.4, leading=16, color=WHITE if purple else INK, strong=True)
        if body:
            self.text(body, x=x+14, y=end+4, width=width-28, size=11.5, leading=15.5,
                      color=colors.HexColor('#eee6ff') if purple else MUTED)

    def bullet(self, text, y, x=M, width=CW):
        self.c.setFillColor(PURPLE); self.c.circle(x+3, H-y-7, 2.3, fill=1, stroke=0)
        return self.text(text, x=x+16, y=y, width=width-16, size=12, leading=17) + 10

    def split_bar(self, labels, counts, y):
        shades = [PURPLE, colors.HexColor('#997ac8'), GREEN, GOLD]
        x = M
        total = sum(counts)
        for value, shade in zip(counts, shades):
            width = CW * value / total
            self.c.setFillColor(shade); self.c.rect(x, H-y-14, width, 14, fill=1, stroke=0)
            x += width
        col = CW / 4
        for i, (label, count, shade) in enumerate(zip(labels, counts, shades)):
            self.text(label, x=M+i*col, y=y+26, width=col-8, size=11.5, leading=16, color=MUTED)
            self.text(f'{count:,}', x=M+i*col, y=y+49, width=col-8, size=21, leading=27, color=shade)

    def status_row(self, name, evidence, y, passed=False):
        self.rect(M, y, CW, 43, WHITE, radius=7, stroke=LINE)
        self.text(name, x=M+12, y=y+10, width=205, size=11.6, leading=16)
        self.text(evidence, x=M+230, y=y+10, width=CW-242, size=11.6, leading=16, color=GREEN if passed else GOLD)

    def save(self):
        self.c.save()


def runtime_rows(evidence):
    verification = evidence.get('verification', evidence)
    aliases = [
        ('Android build', ['android_build', 'android_build_passed', 'android_build_success', 'android_assemble']),
        ('Web production build', ['web_build', 'web_build_passed', 'typescript_build_passed', 'web_typescript_production_build']),
        ('Android policy unit tests', ['android_unit_tests', 'android_unit_tests_passed', 'android_policy_tests']),
        ('ML checks', ['ml_unit_tests', 'ml_tests_passed', 'ml_tests']),
        ('Web policy checks', ['web_policy_tests', 'web_policy_tests_passed', 'web_policy_unit_tests']),
        ('Actual app/model execution', ['runtime_passed', 'browser_runtime_passed', 'actual_wasm_inference_passed']),
    ]
    rows = []
    for name, keys in aliases:
        value = next((verification[key] for key in keys if key in verification), None)
        if value is True or value == 'passed': rows.append((name, 'Passed', True))
        elif isinstance(value, int) and not isinstance(value, bool): rows.append((name, f'{value} passed', True))
        elif isinstance(value, dict) and isinstance(value.get('passed'), int): rows.append((name, f'{value["passed"]} passed', value.get('failures', 0) == 0))
        else: rows.append((name, 'Pending current-run receipt', False))
    return rows


def build(args):
    metadata = load(args.bundle / 'model_metadata.json')
    evaluation_path = find_metric_file(args.bundle, args.reports)
    evaluation = load(evaluation_path)
    evidence = load(args.runtime_evidence)
    if evaluation and evaluation.get('model_sha256') != metadata.get('model_sha256'):
        raise ValueError('Evaluation receipt belongs to a different model artifact.')
    evidence_sha = evidence.get('model_sha256')
    if evidence_sha and evidence_sha != metadata.get('model_sha256'):
        raise ValueError('Runtime evidence belongs to a different model artifact.')
    source = evaluation.get('source_test', {})
    field = evaluation.get('external_field_test', {})
    qualified = evaluation.get('source_acceptance_qualified') is True
    voice = load(ROOT / 'android/app/src/main/assets/content/audio_manifest.json')
    r = Report(args.output, args.draft)
    field_accuracy = pct(field.get('accuracy'), 1)
    source_accuracy = pct(source.get('accuracy'))

    # 01 / Cover: the field limit is visible before the technical detail.
    r.page('Offline Crop Health', 'A practical guide to what we built, how it works, and what the results mean.', 'overview')
    r.rect(M, 161, CW, 145, PURPLE)
    r.text('Crop observation that stays\nwith the farmer.'.replace('\n', '<br/>'), x=M+22, y=180, width=CW-44, size=27, leading=35, color=WHITE)
    r.text('Native Android + browser preview · English, Kannada and Hindi', x=M+22, y=266, width=CW-44, size=12, leading=17, color=colors.HexColor('#ede5fa'))
    col = (CW-24)/3
    for i, (value, label) in enumerate([('3','supported crops'),('17','image categories'),(str(len(voice.get('clips', [])) or 90),'offline voice clips')]):
        r.rect(M+i*(col+12), 326, col, 86)
        r.text(value, x=M+i*(col+12)+16, y=336, width=col-32, size=27, leading=33, color=PURPLE)
        r.text(label, x=M+i*(col+12)+16, y=379, width=col-32, size=11.5, leading=16, color=MUTED)
    r.text('What the prototype delivers', y=443, size=18, leading=24, color=PURPLE)
    r.text('A farmer can photograph one leaf, receive a local model estimate, answer three symptom questions, hear general guidance, and save the observation on the device.', y=479, size=12.5, leading=18)
    r.card(M, 558, CW, 115, 'Source-tested prototype; field recognition is not ready',
           f'The frozen model scored {source_accuracy} on the controlled source test, but only {field_accuracy} on the small external field-like test. It is not ready for reliable field-camera diagnosis. Scores do not authorize treatment.', accent=GOLD, fill=PALE_GOLD)
    r.text('Team Debuggers · Team 8', y=703, size=13, leading=18, color=PURPLE)
    r.text(escape(args.members) + '<br/>BMS College of Engineering · Gradient Club<br/>Build Beyond 26 · PS 4.1 · Review 2', y=730, size=11.5, leading=16, color=MUTED)

    # 02 / Farmer-facing workflow.
    r.page('How a farmer uses the app', 'The interface follows one short journey, with clear ways to retry or ask for help.', 'experience')
    steps = [
        ('1  Choose', 'Select tomato, potato or maize, and a preferred language.'),
        ('2  Capture', 'Photograph one leaf or import an existing leaf image.'),
        ('3  Check the photo', 'The app checks basic image quality and runs the local model.'),
        ('4  Read the estimate', 'See a likely condition, healthy-looking result, or explicit uncertainty.'),
        ('5  Describe symptoms', 'Answer three questions about spreading, spots and affected plants.'),
        ('6  Hear and save', 'Play local guidance, then save or reopen the observation in History.'),
    ]
    for i, (title, body) in enumerate(steps):
        y = 155 + i*77
        r.node(M, y, 307, 63, title, body, purple=i in (0, 3))
        if i < len(steps)-1: r.arrow(M+153, y+63, M+153, y+77)
    r.card(379, 232, W-M-379, 110, 'Retake a poor photo', 'A dark, blurry, tiny or unreadable photo returns practical capture tips.', accent=GOLD, fill=PALE_GOLD)
    r.arrow(351, 330, 379, 286)
    r.card(379, 386, W-M-379, 125, 'Uncertainty is visible', 'A rejected or ambiguous image offers another photo and local expert follow-up.', accent=GOLD, fill=PALE_GOLD)
    r.arrow(351, 418, 379, 418)
    r.card(M, 668, CW, 96, 'The concern check is user-reported', 'The three answers help describe what the farmer sees. The app does not estimate a validated disease-severity grade from the photograph.', accent=GREEN)

    # 03 / Architecture.
    r.page('System architecture', 'The model and observation data stay with the client. The web host serves files.', 'architecture')
    r.node(M, 153, CW, 57, 'Preview host: Node or static hosting', 'Serves the browser app, model, content and audio assets only.')
    r.arrow(430, 210, 430, 245)
    r.node(M, 245, 244, 84, 'Native Android client', 'Kotlin / Compose, CameraX and ONNX Runtime CPU.', purple=True)
    r.node(308, 245, 244, 84, 'Browser preview', 'React / TypeScript, CPU WASM and an offline service worker.', purple=True)
    r.arrow(166, 329, 247, 365); r.arrow(430, 329, 348, 365)
    r.node(148, 365, 300, 74, 'Shared MobileNetV4 bundle', 'The same ONNX weights, labels, preprocessing contract and policy.')
    r.arrow(298, 439, 298, 471)
    r.node(M, 471, CW, 64, 'On-device acceptance and result', 'Quality, score, margin, class enablement, feature distance and crop checks.')
    r.node(M, 579, 244, 71, 'Room / SQLite', 'Android metadata plus app-private photo files.')
    r.node(308, 579, 244, 71, 'IndexedDB', 'Browser metadata and local photo Blobs in one record.')
    r.arrow(65, 329, 65, 579); r.arrow(530, 329, 530, 579)
    r.node(M, 693, CW, 64, 'Local guidance and narration', 'General observation content and 90 English / Kannada / Hindi clips.')
    r.arrow(298, 535, 298, 693)

    # 04 / Model explanation.
    r.page('From a photo to an estimate', 'MobileNetV4-Conv-Small is a compact classifier; acceptance gates control what the UI shows.', 'model pipeline')
    pipeline = [
        ('1  Decode and orient', 'Apply EXIF orientation and bound the working photo size.'),
        ('2  Prepare the tensor', 'Pillow-compatible bilinear letterbox to 224 × 224; RGB, float32 NCHW.'),
        ('3  Run MobileNetV4', '2,514,801 parameters; CPU execution through the packaged ONNX runtime.'),
        ('4  Read two outputs', '17 class logits and a 960-value pooled feature embedding.'),
        ('5  Apply the frozen policy', 'Temperature scaling, per-class score/margin limits and centroid-distance checks.'),
        ('6  Choose the result state', 'Likely / healthy-looking only after gates pass; otherwise uncertainty or retake.'),
    ]
    for i, (title, body) in enumerate(pipeline):
        y = 151+i*69
        r.node(M, y, CW, 56, title, body, purple=i==2)
        if i < 5: r.arrow(W/2, y+56, W/2, y+69)
    half=(CW-16)/2
    r.card(M, 603, half, 137, 'A score is not field accuracy', 'A high score means a strong match among the 17 training labels. It does not prove the cause of a farmer’s field problem.', accent=GOLD)
    r.card(M+half+16, 603, half, 137, 'Distance is a safeguard', 'A distant feature embedding can trigger uncertainty. This gate is not a certified detector of every unfamiliar image.', accent=GREEN)

    # 05 / Dataset and training discipline.
    r.page('Datasets and training protocol', 'Source and field-like images are kept separate when reporting performance.', 'data')
    r.text('PlantVillage · controlled leaf photographs', y=154, size=16, leading=22, color=PURPLE)
    r.text('24,164 verified images; 14 exact copies excluded, leaving 24,150 unique images. Pinned commit: 7f7ecc7e… · CC BY-SA 3.0.', y=188, size=11.7, leading=16.5)
    r.split_bar(['TRAIN','TUNE','CAL','SOURCE TEST'], [16856,2228,1392,3674], 238)
    r.text('Learn weights', x=M, y=326, width=120, size=11.5, leading=16, color=MUTED)
    r.text('Select model', x=M+CW/4, y=326, width=120, size=11.5, leading=16, color=MUTED)
    r.text('Fit policy', x=M+CW/2, y=326, width=120, size=11.5, leading=16, color=MUTED)
    r.text('Evaluate frozen model', x=M+3*CW/4, y=326, width=125, size=11.5, leading=16, color=MUTED)
    r.text('PlantDoc · field-like internet images', y=377, size=16, leading=22, color=PURPLE)
    r.text('987 selected candidate images after quarantine. Pinned commit: 5467f601… · CC BY 4.0. Labels are mostly not visually or agronomist reviewed.', y=410, size=11.7, leading=16.5)
    r.split_bar(['FIELD TRAIN','FIELD TUNE','FIELD CAL','EXTERNAL TEST'], [632,138,137,80], 461)
    r.text('What the split protects', y=570, size=16, leading=22, color=PURPLE)
    y=r.bullet('Training and mixed-domain adaptation use TRAIN. Checkpoint selection uses TUNE; temperature and acceptance limits use CAL. Final TEST is evaluated after freezing.',604)
    y=r.bullet('Known leaf groups and exact image hashes are separated. Complete physical-leaf independence and perceptual duplicate removal are not established.',y)
    r.bullet('Eight potato-healthy CAL images had prior selection exposure; an older 536-image source-test subset was historically inspected. These limits remain disclosed.',y)

    # 06 / Actual frozen-artifact results, never TUNE-as-test.
    r.page('What the results actually show', 'These are separate distributions. Controlled-source performance is not farmer-field accuracy.', 'evaluation')
    half=(CW-16)/2
    for x, title, metrics, color in [(M,'PlantVillage source test',source,PURPLE),(M+half+16,'PlantDoc external field test',field,GOLD)]:
        r.rect(x,155,half,214,LAVENDER if color==PURPLE else PALE_GOLD)
        r.text(title,x=x+16,y=170,width=half-32,size=13,leading=18,strong=True,color=color)
        r.text(pct(metrics.get('accuracy')),x=x+16,y=207,width=half-32,size=31,leading=38,color=color)
        r.text('classification accuracy',x=x+16,y=251,width=half-32,size=11.7,leading=16,color=MUTED)
        macro=metrics.get('macro_f1_all_labels') if color==PURPLE else metrics.get('macro_f1_supported_labels')
        body=f'{number(metrics.get("samples"))} images<br/>Macro F1: {macro:.4f}' if macro is not None else 'Frozen-artifact evaluation pending'
        if color==GOLD: body+='<br/>10 supported field-label classes'
        r.text(body,x=x+16,y=284,width=half-32,size=11.7,leading=17,color=MUTED)
    r.text('Selective acceptance after the frozen gates',y=398,size=16,leading=22,color=PURPLE)
    r.text(f'Source test: {number(source.get("accepted_correct"))} correct / {number(source.get("accepted_predictions"))} accepted. Precision {pct(source.get("accepted_precision"))}; coverage {pct(source.get("coverage"))}.',y=433,size=12,leading=17)
    r.text(f'External field test: {number(field.get("accepted_correct"))} correct / {number(field.get("accepted_predictions"))} accepted. Precision {pct(field.get("accepted_precision"))}; coverage {pct(field.get("coverage"))}.',y=483,size=12,leading=17,color=GOLD)
    r.card(M, 550, CW, 114, 'Field recognition remains a major limitation', 'The external result is poor, even among accepted predictions. The 80-image challenge covers only ten candidate label mappings and is not an expert-reviewed field trial. Reliable field-camera diagnosis and treatment recommendations are not established.', accent=GOLD, fill=PALE_GOLD)
    r.text('Acceptance scope: ' + ('source-tested prototype enabled for 17 classes' if qualified else 'pending / disabled') + '. Field diagnosis validation: false.',y=688,size=11.7,leading=17,color=MUTED)
    r.text('Exact exported model SHA-256',y=734,size=11.5,leading=16,color=PURPLE)
    r.c.setFont('Courier',9.8);r.c.setFillColor(MUTED);r.c.drawString(M,H-772,metadata.get('model_sha256','Pending final artifact'))

    # 07 / Implementation and recorded runtime evidence.
    r.page('Offline behavior and verification', 'The app includes the assets it needs; the browser caches them after its first successful visit.', 'implementation')
    third=(CW-24)/3
    for i,(title,body) in enumerate([('English · 30 clips','Piper LJSpeech neural narration.'),('Kannada · 30 clips','AI4Bharat Indic-TTS narration.'),('Hindi · 30 clips','Piper Pratham neural narration.')]):
        r.card(M+i*(third+12),154,third,116,title,body)
    r.text('Speech models are used during development. The phone stores only audio recordings; playback needs no paid speech API or installed voice pack.',y=293,size=12,leading=17)
    r.text('Observation storage stays local',y=355,size=16,leading=22,color=PURPLE)
    r.text('Android uses Room/SQLite plus app-private photos. The browser uses IndexedDB for metadata and photo Blobs. Language selection persists locally. There is no account or central photo database.',y=387,size=12,leading=17)
    r.text('Current-run technical evidence',y=456,size=16,leading=22,color=PURPLE)
    for i,(name,value,passed) in enumerate(runtime_rows(evidence)):
        r.status_row(name,value,491+i*46,passed)
    r.text('A real 3–4 GB ARM-phone benchmark, native-speaker listening review and an agricultural field trial remain pending. Software-emulator/browser timings are not phone performance.',y=778,size=11.5,leading=16,color=MUTED)

    # 08 / Presenter guide and honest next steps.
    r.page('Review 2 speaking guide', 'Show the working prototype, then explain its measured limits and the next learning step.', 'presenter notes')
    demo=[
        ('0:00–0:20','Choose a crop and language. Show camera capture or a clearly identified sample photo.'),
        ('0:20–0:50','Run real local inference. Explain the condition, actual model score and the uncertainty path.'),
        ('0:50–1:20','Complete the three symptom questions. Play Kannada or Hindi guidance and show general precautions.'),
        ('1:20–1:45','Save the observation, open History, and reopen its photo/result. Show offline readiness.'),
        ('1:45–2:00','State the source-versus-field results. Describe field-data improvement as the next step.'),
    ]
    y=153
    for timing,description in demo:
        r.text(timing,x=M,y=y,width=91,size=12,leading=17,color=PURPLE,strong=True)
        end=r.text(description,x=M+105,y=y,width=CW-105,size=12,leading=17)
        y=end+18
    r.card(M, 486, CW, 133, 'A clear answer to “How accurate is it?”', f'“The exact model reached {source_accuracy} on the controlled source test. On the separate field-like set it reached only {field_accuracy}. We therefore present a source-tested prototype, keep uncertainty visible, and do not claim reliable field diagnosis or pesticide advice.”', accent=GOLD, fill=PALE_GOLD)
    r.text('Next steps — planned, not completed',y=642,size=16,leading=22,color=PURPLE)
    r.text('Curate and expert-review local field photos; expand independent field labels and unknown-image challenges; repeat frozen calibration/testing; listen with native speakers; benchmark actual budget Android devices.',y=675,size=12,leading=17)
    r.text('Evidence sources',y=740,size=11.5,leading=16,color=PURPLE)
    r.text('Repository: github.com/salecha-codes/Build_Beyond<br/>Datasets: spMohanty/PlantVillage-Dataset · pratikkayal/PlantDoc-Dataset<br/>Exact receipts: models/assets/model/source_evaluation.json and ml/reports/review2_full/',y=760,size=10.2,leading=14,color=MUTED)
    r.save()
    print(json.dumps({'output':str(args.output),'pages':8,'model_sha256':metadata.get('model_sha256'),
                      'evaluation':str(evaluation_path) if evaluation_path else None,'draft':args.draft},indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,default=ROOT/'models/assets/model')
    parser.add_argument('--reports',type=Path,default=ROOT/'ml/reports/review2_full')
    parser.add_argument('--runtime-evidence',type=Path,default=ROOT/'dist/evidence/model-retraining-validation.json')
    parser.add_argument('--protocol',type=Path,help='Reserved explicit source protocol path for provenance')
    parser.add_argument('--members',default='Jeveen MR · Ishank AB · Mahendra')
    parser.add_argument('--output',type=Path,default=ROOT/'dist/Build_Beyond26_Review2_Technical_Report.pdf')
    parser.add_argument('--draft',action='store_true')
    args=parser.parse_args()
    build(args)


if __name__=='__main__':
    main()
