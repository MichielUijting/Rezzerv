from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any

PRICE_PATTERN = re.compile(r"\b\d+[\.,]\d{2}\b")
NOISE_PATTERNS = [
    r'terminal',
    r'nfc',
    r'chip',
    r'totaal',
    r'total',
    r'datum',
    r'kaart',
    r'pin',
]


def is_price(text: str) -> bool:
    return bool(PRICE_PATTERN.search(text or ''))


def is_noise(text: str) -> bool:
    lowered = (text or '').lower()
    return any(re.search(pattern, lowered, re.I) for pattern in NOISE_PATTERNS)


def region_score(region: dict[str, Any]) -> float:
    density = float(region['article_candidate_density'])
    prices = int(region['price_anchor_count'])
    noise = int(region['semantic_noise_count'])
    boxes = int(region['ocr_box_count'])

    score = density * 0.55
    score += min(0.25, prices * 0.05)
    score += min(0.20, boxes * 0.01)
    score -= min(0.50, noise * 0.08)

    return round(score, 4)


def main() -> int:
    parser = argparse.ArgumentParser(description='R7c-14 AH foto 3 body region isolation diagnostics')
    parser.add_argument('--topology-json', required=True)
    parser.add_argument('--semantic-json', required=True)
    parser.add_argument('--json-out', required=True)
    parser.add_argument('--csv-out', required=True)
    args = parser.parse_args()

    topology = json.loads(Path(args.topology_json).read_text(encoding='utf-8'))
    semantic = json.loads(Path(args.semantic_json).read_text(encoding='utf-8'))

    sample_pairs = topology.get('sample_pairs') or []
    semantic_rows = semantic.get('rows') or []

    regions: list[dict[str, Any]] = []

    estimated_total_boxes = int(topology.get('ocr_box_count') or 0)
    estimated_lines = max(1, int(topology.get('topology_line_count') or 1))
    approx_boxes_per_region = max(1, math.ceil(estimated_total_boxes / 4))

    for index in range(4):
        y_top = index * 0.25
        y_bottom = (index + 1) * 0.25

        related_pairs = sample_pairs[index::4]
        related_semantic = semantic_rows[index::4]

        price_anchor_count = sum(1 for pair in related_pairs if is_price(str(pair.get('price') or '')))
        semantic_noise_count = sum(1 for row in related_semantic if not bool(row.get('is_article_candidate')))

        article_candidate_count = sum(1 for row in related_semantic if bool(row.get('is_article_candidate')))

        density = round(article_candidate_count / max(1, len(related_semantic)), 4) if related_semantic else 0.0

        region = {
            'region_id': f'region_{index + 1}',
            'y_top': round(y_top, 2),
            'y_bottom': round(y_bottom, 2),
            'ocr_box_count': approx_boxes_per_region,
            'price_anchor_count': price_anchor_count,
            'semantic_noise_count': semantic_noise_count,
            'article_candidate_density': density,
        }

        region['body_region_score'] = region_score(region)
        regions.append(region)

    ranked = sorted(regions, key=lambda item: float(item['body_region_score']), reverse=True)

    result = {
        'fixture_file': 'AH foto 3.jpg',
        'diagnostic_only': True,
        'regions': ranked,
        'best_region': ranked[0] if ranked else None,
    }

    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')

    csv_out = Path(args.csv_out)
    csv_out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        'region_id',
        'y_top',
        'y_bottom',
        'ocr_box_count',
        'price_anchor_count',
        'semantic_noise_count',
        'article_candidate_density',
        'body_region_score',
    ]

    with csv_out.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(ranked)

    best = ranked[0] if ranked else {}

    print('R7c-14 AH foto 3 body region isolation diagnostics')
    print(f"region_count: {len(ranked)}")
    print(f"best_region: {best.get('region_id', '')}")
    print(f"best_region_score: {best.get('body_region_score', '')}")
    print(f"json_written: {json_out}")
    print(f"csv_written: {csv_out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
