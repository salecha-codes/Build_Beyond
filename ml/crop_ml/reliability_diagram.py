"""Render a reliability diagram from an exact-artifact qualification receipt.

Run: python -m crop_ml.reliability_diagram --receipt path/to/source_evaluation.json \
  --domain source_test --output path/to/reliability-source-test.svg

The receipt must contain per-bin counts, accuracy and mean confidence. Older receipts
with only an aggregate ECE cannot be used to reconstruct a reliability diagram.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def _domain(receipt: dict, domain: str) -> dict:
    value = receipt
    for part in domain.split('.'):
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"Domain path not found: {domain}")
        value = value[part]
    if not isinstance(value, dict):
        raise ValueError(f"Domain is not an evaluation report: {domain}")
    return value


def render(report: dict) -> str:
    bins = report.get('reliability_bins_15')
    if not isinstance(bins, list) or len(bins) != 15:
        raise ValueError('Receipt has no 15-bin reliability data; rerun exact-artifact qualification with this version.')
    width, height = 800, 570
    left, top, size = 92, 64, 420
    right, bottom = left + size, top + size
    samples = sum(int(row['count']) for row in bins)
    if samples != int(report.get('samples', -1)):
        raise ValueError('Reliability bin counts do not match report sample count')
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#24352e}.grid{stroke:#dfe7e2;stroke-width:1}.axis{stroke:#24352e;stroke-width:1.5}.diag{stroke:#86968e;stroke-width:2;stroke-dasharray:7 6}.bar{fill:#3d8f69;fill-opacity:.82;stroke:#286c4c}.tick{font-size:12px}.title{font-size:20px;font-weight:700}.sub{font-size:12px;fill:#52645b}</style>',
        f'<text class="title" x="{left}" y="30">Reliability diagram · {html.escape(str(report.get("scope", "")))}</text>',
        f'<text class="sub" x="{left}" y="49">{samples} examples · ECE(15) {float(report["expected_calibration_error_15_bins"]):.4f} · T {float(report["temperature"]):.4f}</text>',
    ]
    for tick in range(6):
        value = tick / 5
        x, y = left + size * value, bottom - size * value
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}"/>')
        parts.append(f'<line class="grid" x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}"/>')
        parts.append(f'<text class="tick" text-anchor="middle" x="{x:.1f}" y="{bottom+22}">{value:.1f}</text>')
        parts.append(f'<text class="tick" text-anchor="end" x="{left-10}" y="{y+4:.1f}">{value:.1f}</text>')
    parts.append(f'<line class="diag" x1="{left}" y1="{bottom}" x2="{right}" y2="{top}"/>')
    for index, row in enumerate(bins):
        confidence, accuracy, count = row['mean_confidence'], row['accuracy'], int(row['count'])
        if not count or confidence is None or accuracy is None:
            continue
        bw = size / 15 * .78
        x = left + size * (index + .11) / 15
        y = bottom - size * float(accuracy)
        bh = size * float(accuracy)
        parts.append(f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}"><title>Bin {index+1}: n={count}, confidence={float(confidence):.3f}, accuracy={float(accuracy):.3f}</title></rect>')
        cx = left + size * float(confidence)
        cy = bottom - size * float(accuracy)
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="#a14f24"/>')
    parts.extend([
        f'<line class="axis" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}"/>',
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{bottom}"/>',
        f'<text text-anchor="middle" x="{left+size/2}" y="{bottom+52}">Mean predicted confidence</text>',
        f'<text text-anchor="middle" transform="translate(24 {top+size/2}) rotate(-90)">Observed accuracy</text>',
        f'<text class="sub" x="{left}" y="{height-18}">Bars show per-bin accuracy; dots mark mean confidence and observed accuracy. Empty bins are omitted.</text>',
        '</svg>',
    ])
    return '\n'.join(parts) + '\n'


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--domain', default='source_test', help='Dot path within JSON; e.g. source_test or calibration_report')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = json.loads(args.receipt.read_text())
    report = _domain(receipt, args.domain)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(report))
    print(json.dumps({'diagram': str(args.output), 'domain': args.domain, 'samples': report['samples'],
                      'ece_15': report['expected_calibration_error_15_bins']}))


if __name__ == '__main__':
    main()
