from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from difflib import SequenceMatcher
from pathlib import Path

from add_amount_region_zone_diagnostics import _image_by_stem, _should_run_for_image

DEFAULT_TARGETS = {
    'AH foto 2',
    'Aldi foto 2',
    'Plus foto 2',
    'plus foto 1',
}
CHAR_REPLACEMENT_PATTERNS = {
    '0': 'O',
    '1': 'I',
    '5': 'S',
    '8': 'B',
    '@': 'O',
    '€': 'E',
    '£': 'E',
    '|': 'I',
}
AMOUNT_PATTERN = re.compile(r'(?<!\d)(?:€|eur|euro)?\s*-?\d+[\.,]\d{2}(?!\d)', re.IGNORECASE)


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
    prefix_parts = prefix.parts
    parts = raw.parts
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


def _normalize_text(value: str) -> str:
    value = str(value or '').lower()
    value = re.sub(r'[^a-z0-9à-ÿ]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def _alpha_tokens(text: str) -> list[str]:
    return [token for token in _normalize_text(text).split() if re.search(r'[a-zà-ÿ]', token)]


def _count_pseudo_amount_noise(lines: list[str]) -> int:
    count = 0
    for line in lines:
        if AMOUNT_PATTERN.search(line):
            count += 1
        elif re.search(r'\d+[,.]\s*\d{1,2}', line):
            count += 1
        elif re.search(r'[€£]\s*\d+', line):
            count += 1
    return count


def _character_replacement_patterns(text: str) -> list[dict[str, str]]:
    patterns = []
    for original, replacement in CHAR_REPLACEMENT_PATTERNS.items():
        if original in text:
            patterns.append({'observed': original, 'probable': replacement, 'reason': 'common_ocr_character_confusion'})
    if re.search(r'[a-zA-Z][0-9][a-zA-Z]', text):
        patterns.append({'observed': 'digit_inside_word', 'probable': 'letter_substitution', 'reason': 'digit_embedded_in_alpha_token'})
    if re.search(r'[a-zA-Z][.,][a-zA-Z]', text):
        patterns.append({'observed': 'punctuation_inside_word', 'probable': 'split_or_noise', 'reason': 'punctuation_embedded_in_alpha_token'})
    return patterns


def _probable_broken_word_joins(lines: list[str]) -> list[str]:
    joins: list[str] = []
    tokens = []
    for line in lines:
        tokens.extend(_alpha_tokens(line))
    for index in range(len(tokens) - 1):
        left = tokens[index]
        right = tokens[index + 1]
        if 1 <= len(left) <= 3 and len(right) >= 3:
            joined = f'{left}{right}'
            joins.append(f'{left} {right} -> {joined}')
        elif len(left) >= 3 and 1 <= len(right) <= 3:
            joined = f'{left}{right}'
            joins.append(f'{left} {right} -> {joined}')
    return joins[:8]


def _text_fragmentation_score(lines: list[str]) -> float:
    tokens = []
    short_tokens = 0
    empty_or_noise_lines = 0
    for line in lines:
        normalized = _normalize_text(line)
        line_tokens = normalized.split()
        if not line_tokens:
            empty_or_noise_lines += 1
        tokens.extend(line_tokens)
        short_tokens += sum(1 for token in line_tokens if len(token) <= 2)
    if not tokens:
        return 1.0
    line_factor = min(1.0, max(0, len(lines) - 1) / 4.0)
    short_factor = min(1.0, short_tokens / max(1, len(tokens)))
    noise_factor = min(1.0, empty_or_noise_lines / max(1, len(lines)))
    score = (line_factor * 0.35) + (short_factor * 0.45) + (noise_factor * 0.20)
    return round(score, 3)


def _cluster_text_consistency(lines: list[str]) -> float:
    normalized_lines = [_normalize_text(line) for line in lines if _normalize_text(line)]
    if len(normalized_lines) <= 1:
        return 1.0 if normalized_lines else 0.0
    similarities = []
    for index in range(len(normalized_lines) - 1):
        similarities.append(SequenceMatcher(None, normalized_lines[index], normalized_lines[index + 1]).ratio())
    token_sets = [set(line.split()) for line in normalized_lines]
    overlaps = []
    for index in range(len(token_sets) - 1):
        union = token_sets[index] | token_sets[index + 1]
        intersection = token_sets[index] & token_sets[index + 1]
        overlaps.append(len(intersection) / max(1, len(union)))
    raw_score = (statistics.mean(similarities) * 0.55) + (statistics.mean(overlaps) * 0.45)
    # Complement with fragmentation penalty: consistent product clusters are not overly similar line-to-line, but should be clean text.
    score = max(0.0, min(1.0, raw_score + 0.35))
    return round(score, 3)


def _confidence_variance(cluster_confidence: object, lines: list[str]) -> float:
    # Existing cluster diagnostics currently store averaged confidence. Until per-line confidence exists,
    # use deterministic text-derived proxy to surface instability without changing OCR output.
    values = []
    base = 0.0
    try:
        base = float(cluster_confidence) if cluster_confidence is not None else 50.0
    except Exception:
        base = 50.0
    for line in lines:
        penalty = 0
        penalty += len(_character_replacement_patterns(line)) * 6
        penalty += _count_pseudo_amount_noise([line]) * 10
        penalty += sum(1 for token in _normalize_text(line).split() if len(token) <= 2) * 2
        values.append(max(0.0, min(100.0, base - penalty)))
    if len(values) <= 1:
        return 0.0
    return round(float(statistics.pvariance(values)), 3)


def _multi_pass_similarity(cluster: dict, receipt_json: dict) -> float:
    cluster_text = _normalize_text(' '.join(cluster.get('cluster_text_lines', [])))
    if not cluster_text:
        return 0.0
    comparisons = []
    flex_diag = receipt_json.get('metadata', {}).get('flexible_alignment_validation', {})
    for variant in flex_diag.get('variants', []):
        for pair in variant.get('validated_pairs', []):
            text = _normalize_text(str(pair.get('product_name_text') or pair.get('product_name_raw_line') or ''))
            if text:
                comparisons.append(SequenceMatcher(None, cluster_text, text).ratio())
    if not comparisons:
        return 0.0
    return round(max(comparisons), 3)


def build_ocr_text_stability_diagnostics(receipt_json: dict) -> dict[str, object]:
    clusters_diag = receipt_json.get('metadata', {}).get('ocr_product_clusters', {})
    output_clusters = []
    for cluster in clusters_diag.get('clusters', []):
        lines = [str(line) for line in cluster.get('cluster_text_lines', [])]
        confidence = cluster.get('cluster_confidence')
        fragmentation = _text_fragmentation_score(lines)
        consistency = _cluster_text_consistency(lines)
        pseudo_amounts = _count_pseudo_amount_noise(lines)
        replacements = []
        for line in lines:
            replacements.extend(_character_replacement_patterns(line))
        broken_joins = _probable_broken_word_joins(lines)
        confidence_var = _confidence_variance(confidence, lines)
        multi_pass_similarity = _multi_pass_similarity(cluster, receipt_json)

        stability_score = (1.0 - fragmentation) * 0.35 + consistency * 0.25 + multi_pass_similarity * 0.20
        stability_score += max(0.0, 1.0 - min(1.0, confidence_var / 400.0)) * 0.10
        stability_score += max(0.0, 1.0 - min(1.0, pseudo_amounts / 3.0)) * 0.10
        stability_score = round(max(0.0, min(1.0, stability_score)), 3)

        output_clusters.append({
            'cluster_id': cluster.get('cluster_id'),
            'cluster_text_lines': lines,
            'cluster_confidence': confidence,
            'text_fragmentation_score': fragmentation,
            'cluster_text_consistency': consistency,
            'pseudo_amount_noise_count': pseudo_amounts,
            'ocr_character_replacement_patterns': replacements[:12],
            'probable_broken_word_joins': broken_joins,
            'multi_pass_ocr_text_similarity': multi_pass_similarity,
            'confidence_variance': confidence_var,
            'text_stability_score': stability_score,
            'linked_amount_candidate_count': len(cluster.get('linked_amount_candidates', [])),
            'rejected_amount_candidate_count': len(cluster.get('rejected_amount_candidates', [])),
            'diagnostic_only': True,
            'reconstruction_applied': False,
        })

    stable_clusters = [cluster for cluster in output_clusters if cluster.get('text_stability_score', 0) >= 0.65]
    unstable_clusters = [cluster for cluster in output_clusters if cluster.get('text_stability_score', 0) < 0.65]
    return {
        'diagnostic_scope': 'ocr_product_cluster_text_stability_diagnostics',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'cluster_count': len(output_clusters),
        'stable_cluster_count': len(stable_clusters),
        'unstable_cluster_count': len(unstable_clusters),
        'limits': {
            'stable_text_stability_score_min': 0.65,
        },
        'clusters': output_clusters,
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')

    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('ocr_text_stability_diagnostics', {})

    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_ocr_text_stability_diagnostics(payload)
        payload.setdefault('metadata', {})['ocr_text_stability_diagnostics'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['ocr_text_stability_diagnostics'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1

    summary['schema_version'] = 'receipt-ocr-benchmark-v25-ocr-text-stability-diagnostics'
    summary['ocr_text_stability_diagnostics_processed_receipts'] = processed
    summary['ocr_text_stability_diagnostics_skipped_receipts'] = skipped
    summary['ocr_text_stability_diagnostics_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] OCR text stability diagnostics added for {processed} receipts; skipped={skipped}')


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
