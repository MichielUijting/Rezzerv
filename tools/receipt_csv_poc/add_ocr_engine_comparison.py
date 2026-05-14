from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pytesseract

from add_amount_region_zone_diagnostics import _image_by_stem, _should_run_for_image, build_amount_region_zone_diagnostics
from add_preprocessing_variant_diagnostics import _variant_images, _write_temp_variant
from add_ocr_region_diagnostics import extract_ocr_regions
from add_ocr_product_cluster_diagnostics import build_ocr_product_clusters

DEFAULT_TARGETS = {
    'AH foto 2',
    'Aldi foto 2',
    'Plus foto 2',
    'plus foto 1',
}
OCR_CONFIGS = [
    {'label': 'psm4_nld_eng', 'lang': 'nld+eng', 'config': '--psm 4'},
    {'label': 'psm6_nld_eng', 'lang': 'nld+eng', 'config': '--psm 6'},
    {'label': 'psm11_nld_eng', 'lang': 'nld+eng', 'config': '--psm 11'},
    {'label': 'psm11_eng', 'lang': 'eng', 'config': '--psm 11'},
    {'label': 'psm11_nld', 'lang': 'nld', 'config': '--psm 11'},
]
SELECTED_VARIANTS = {'original', 'contrast_scale_up_175', 'scale_up_175', 'threshold'}


def _read_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding='utf-8').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    return values


def _candidate_run_paths(raw_run_path: str) -> list[Path]:
    raw = Path(raw_run_path)
    candidates = [raw]
    prefix = Path('tools') / 'receipt_csv_poc'
    parts = raw.parts
    prefix_parts = prefix.parts
    if len(parts) > len(prefix_parts) and parts[:len(prefix_parts)] == prefix_parts:
        candidates.append(Path(*parts[len(prefix_parts):]))
    if raw.name:
        candidates.append(Path('test_runs') / raw.name)
    return candidates


def _is_valid_run_dir(path: Path) -> bool:
    return (path / 'json').exists() and (path / 'benchmark_summary.json').exists()


def _find_latest_valid_run(test_runs_dir: Path = Path('test_runs')) -> Path:
    valid_runs = [path for path in test_runs_dir.glob('run_*') if path.is_dir() and _is_valid_run_dir(path)]
    if not valid_runs:
        raise FileNotFoundError(f'No valid run directory found under {test_runs_dir}')
    return sorted(valid_runs, key=lambda path: path.name)[-1]


def _read_latest_run_path(latest_file: Path) -> Path:
    values = _read_key_values(latest_file)
    raw_run_path = values.get('run_path', '')
    if raw_run_path:
        for candidate in _candidate_run_paths(raw_run_path):
            if _is_valid_run_dir(candidate):
                return candidate
        print(f'[WARN] LATEST_PUSHED_RUN points to invalid or incomplete run: {raw_run_path}')
    fallback = _find_latest_valid_run()
    print(f'[INFO] Using latest valid local run instead: {fallback}')
    return fallback


def _norm(value: str) -> str:
    value = re.sub(r'[^a-z0-9à-ÿ]+', ' ', str(value or '').lower())
    return re.sub(r'\s+', ' ', value).strip()


def _is_product_like_region(text: str) -> bool:
    normalized = _norm(text)
    if len(normalized) < 3:
        return False
    blocked = (
        'totaal', 'subtotaal', 'betaling', 'betaald', 'kaart', 'btw', 'wisselgeld',
        'zegel', 'campagne', 'pluspunt', 'spaarkaart', 'omschrijving', 'prijs',
        'bedrag', 'aantal', 'tel', 'terminal', 'merchant', 'contactless', 'datum',
        'kassa', 'bon', 'chip', 'waarvan', 'albert heijn', 'polenplein',
    )
    if any(word in normalized for word in blocked):
        return False
    return bool(re.search(r'[a-zà-ÿ]{3,}', normalized))


def _count_product_regions(regions: list[dict]) -> int:
    return sum(1 for region in regions if _is_product_like_region(str(region.get('text') or '')))


def _patch_extract_with_config(config: str):
    original = pytesseract.image_to_data

    def patched(*args, **kwargs):
        existing = kwargs.get('config', '') or ''
        kwargs['config'] = f'{existing} {config}'.strip()
        return original(*args, **kwargs)

    return original, patched


def _extract_regions_with_config(image_path: Path, lang: str, config: str) -> list[dict]:
    original, patched = _patch_extract_with_config(config)
    try:
        pytesseract.image_to_data = patched
        return extract_ocr_regions(image_path, lang)
    finally:
        pytesseract.image_to_data = original


def _zone_diag_for_config(image_path: Path, receipt_json: dict, lang: str, config: str, temp_dir: Path) -> dict:
    original, patched = _patch_extract_with_config(config)
    try:
        pytesseract.image_to_data = patched
        return build_amount_region_zone_diagnostics(image_path, receipt_json, lang, temp_dir)
    finally:
        pytesseract.image_to_data = original


def _cluster_candidate_count_from_zone_diag(receipt_json: dict, zone_diag: dict) -> int:
    temp_payload = json.loads(json.dumps(receipt_json, ensure_ascii=False))
    temp_payload.setdefault('metadata', {})['amount_region_zone_diagnostics'] = zone_diag
    clusters = build_ocr_product_clusters(temp_payload)
    return int(clusters.get('linked_amount_candidate_count', 0) or 0)


def build_ocr_engine_comparison(image_path: Path, receipt_json: dict, output_dir: Path) -> dict[str, object]:
    temp_dir = output_dir / 'debug_images' / 'ocr_engine_comparison'
    variant_outputs = []

    variants = [(name, image) for name, image in _variant_images(image_path) if name in SELECTED_VARIANTS]
    for variant_name, variant_image in variants:
        variant_path = _write_temp_variant(temp_dir, image_path, f'engine_{variant_name}', variant_image)
        config_results = []
        for ocr_config in OCR_CONFIGS:
            label = ocr_config['label']
            lang = ocr_config['lang']
            config = ocr_config['config']
            try:
                regions = _extract_regions_with_config(variant_path, lang, config)
                product_region_count = _count_product_regions(regions)
                amount_region_count = sum(1 for region in regions if region.get('amounts'))
                zone_diag = _zone_diag_for_config(variant_path, receipt_json, lang, config, temp_dir)
                best_zone_variant = zone_diag.get('best_article_zone_variant', {})
                article_zone_amount_count = int(best_zone_variant.get('article_zone_amount_count', 0) or 0)
                cluster_alignment_candidate_count = _cluster_candidate_count_from_zone_diag(receipt_json, zone_diag)
                config_results.append({
                    'config_label': label,
                    'config': f'{config} {lang}',
                    'psm_config': config,
                    'lang': lang,
                    'ocr_region_count': len(regions),
                    'product_region_count': product_region_count,
                    'amount_region_count': amount_region_count,
                    'article_zone_amount_count': article_zone_amount_count,
                    'cluster_alignment_candidate_count': cluster_alignment_candidate_count,
                    'diagnostic_only': True,
                    'reconstruction_applied': False,
                })
            except Exception as exc:
                config_results.append({
                    'config_label': label,
                    'config': f'{config} {lang}',
                    'psm_config': config,
                    'lang': lang,
                    'ocr_region_count': 0,
                    'product_region_count': 0,
                    'amount_region_count': 0,
                    'article_zone_amount_count': 0,
                    'cluster_alignment_candidate_count': 0,
                    'error': str(exc),
                    'diagnostic_only': True,
                    'reconstruction_applied': False,
                })
        best_config = max(
            config_results,
            key=lambda item: (
                int(item.get('cluster_alignment_candidate_count', 0)),
                int(item.get('article_zone_amount_count', 0)),
                int(item.get('product_region_count', 0)),
                int(item.get('amount_region_count', 0)),
            ),
            default={},
        )
        variant_outputs.append({
            'variant': variant_name,
            'best_config': {
                'config_label': best_config.get('config_label', ''),
                'config': best_config.get('config', ''),
                'product_region_count': best_config.get('product_region_count', 0),
                'amount_region_count': best_config.get('amount_region_count', 0),
                'article_zone_amount_count': best_config.get('article_zone_amount_count', 0),
                'cluster_alignment_candidate_count': best_config.get('cluster_alignment_candidate_count', 0),
            },
            'ocr_configs': config_results,
        })

    best_overall = max(
        [cfg for variant in variant_outputs for cfg in variant.get('ocr_configs', [])],
        key=lambda item: (
            int(item.get('cluster_alignment_candidate_count', 0)),
            int(item.get('article_zone_amount_count', 0)),
            int(item.get('product_region_count', 0)),
            int(item.get('amount_region_count', 0)),
        ),
        default={},
    )
    return {
        'diagnostic_scope': 'tesseract_ocr_engine_config_comparison',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'image_file': image_path.name,
        'selected_variants': sorted(SELECTED_VARIANTS),
        'tested_config_count_per_variant': len(OCR_CONFIGS),
        'best_overall_config': {
            'config_label': best_overall.get('config_label', ''),
            'config': best_overall.get('config', ''),
            'product_region_count': best_overall.get('product_region_count', 0),
            'amount_region_count': best_overall.get('amount_region_count', 0),
            'article_zone_amount_count': best_overall.get('article_zone_amount_count', 0),
            'cluster_alignment_candidate_count': best_overall.get('cluster_alignment_candidate_count', 0),
        },
        'variants': variant_outputs,
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')

    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('ocr_engine_comparison', {})

    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_ocr_engine_comparison(image_path, payload, output_dir)
        payload.setdefault('metadata', {})['ocr_engine_comparison'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['ocr_engine_comparison'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1

    summary['schema_version'] = 'receipt-ocr-benchmark-v22-ocr-engine-comparison'
    summary['ocr_engine_comparison_processed_receipts'] = processed
    summary['ocr_engine_comparison_skipped_receipts'] = skipped
    summary['ocr_engine_comparison_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] OCR engine comparison added for {processed} receipts; skipped={skipped}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='input_receipts')
    parser.add_argument('--output', default='')
    parser.add_argument('--latest-file', default='LATEST_PUSHED_RUN.txt')
    parser.add_argument('--targets', nargs='*', default=sorted(DEFAULT_TARGETS))
    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else _read_latest_run_path(Path(args.latest_file))
    update_targeted_run(Path(args.input), output_dir, set(args.targets))


if __name__ == '__main__':
    main()
