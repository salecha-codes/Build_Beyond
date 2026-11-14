#!/usr/bin/env python3
"""Reproduce care-source access checks without treating a URL as verification.

Downloads are research-only, not training data or automatically approved app
advice. Third-party Spanish IPM CSVs are GPL-3.0 and are not installed in the app.
Use an output directory outside the checkout for downloaded research material.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
from pathlib import Path
import urllib.request

IPM_COMMIT = 'f4a93ab472002bebb9168e2156fe28705822fb29'
IPM_BASE = f'https://raw.githubusercontent.com/BioPabloCG/ipm_pest_identifier/{IPM_COMMIT}/'
SOURCES = [
    ('tnau-tomato', 'https://agritech.tnau.ac.in/crop_protection/tomato_diseases.html', 'primary_reference_lead'),
    ('umn-early-blight', 'https://extension.umn.edu/disease-management/early-blight-tomato-and-potato', 'primary_reference_lead'),
    ('ucipm-bacterial-spot', 'https://ipm.ucanr.edu/agriculture/tomato/bacterial-spot/', 'primary_reference_lead'),
    ('plantvillage-readme', 'https://raw.githubusercontent.com/spMohanty/PlantVillage-Dataset/master/README.md', 'disease_taxonomy_only'),
    *[(f'derived-ipm-{name.split("/")[-1]}', IPM_BASE + name, 'third_party_transcription_not_primary_verified')
      for name in ('README.md', 'LICENSE', 'Database/species_data.csv', 'Database/control_data.csv', 'Database/monitoring_data.csv')],
]


def acquire(item: tuple[str, str, str], output: Path) -> dict:
    name, url, provenance = item
    record = {'id': name, 'url': url, 'provenance': provenance,
              'agronomist_reviewed': False, 'india_registration_verified': False}
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'CropHealth-Source-Audit/1.0'})
        with urllib.request.urlopen(request, timeout=20) as response:
            content = response.read(16 * 1024 * 1024 + 1)
            if len(content) > 16 * 1024 * 1024:
                raise ValueError('Source exceeds research download limit')
            record.update(http_status=response.status, bytes=len(content),
                          sha256=hashlib.sha256(content).hexdigest(),
                          access_status='retrieved_not_automatically_validated')
            (output / name).write_bytes(content)
        if name.endswith('.csv'):
            rows = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig')), delimiter=';'))
            record['row_count'] = len(rows)
            record['potato_early_late_blight_row_ids'] = [row['id'] for row in rows if row.get('id') in ('109', '111')]
    except Exception as error:
        record.update(access_status='not_retrieved', error=str(error))
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda item: acquire(item, args.output), SOURCES))
    report = {'schema_version': 1, 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'purpose': 'source access/provenance audit, not model training or efficacy validation',
              'third_party_ipm_commit': IPM_COMMIT, 'third_party_ipm_license': 'GPL-3.0',
              'sources': results}
    (args.output / 'access-receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'sources': len(results), 'retrieved': sum('sha256' in row for row in results),
                      'report': str(args.output / 'access-receipt.json')}, indent=2))


if __name__ == '__main__':
    main()
