from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

PRICE_PATTERN = re.compile(r"\b\d+[\.,]\d{2}\b")
FOOTER_PATTERNS = [
    r"terminal",
    r"nfc",
    r"chip",
    r"kaart",
    r"pin",
    r"maestro",
    r"visa",
    r"mastercard",
    r"totaal",
    r"total",
    r"te betalen",
    r"datum",
    r"periode",
    r"bedankt",
    r"tot ziens",
    r"bonuskaart",
    r"ah\.nl",
]


def contains_price(text: str) -> bool:
    return bool(PRICE_PATTERN.search(text or ""))


def footer_keyword_hits(text: str) -> int:
    lowered = (text or "").lower()
    return sum(1 for pattern in FOOTER_PATTERNS if re.search(pattern, lowered, re.I))


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def score_region(region: dict[str, Any], any_price_anchor: bool) -> dict[str, Any]:
    price_anchor_count = int(region.get("price_anchor_count") or 0)
    semantic_noise_count = int(region.get("semantic_noise_count") or 0)
    ocr_box_count = int(region.get("ocr_box_count") or 0)
    article_candidate_count = int(region.get("article_candidate_count") or 0)
    pair_alignment_count = int(region.get("pair_alignment_count") or 0)
    footer_hit_count = int(region.get("footer_keyword_hit_count") or 0)
    density = float(region.get("article_candidate_density") or 0.0)

    price_anchor_score = clamp(price_anchor_count * 0.16, 0.0, 0.48)
    article_density_score = clamp(density * 0.36, 0.0, 0.36)
    article_candidate_score = clamp(article_candidate_count * 0.08, 0.0, 0.24)
    pair_alignment_score = clamp(pair_alignment_count * 0.10, 0.0, 0.30)
    ocr_presence_score = clamp(ocr_box_count * 0.002, 0.0, 0.08)

    semantic_noise_penalty = clamp(semantic_noise_count * 0.10, 0.0, 0.50)
    footer_keyword_penalty = clamp(footer_hit_count * 0.12, 0.0, 0.60)

    # R7c-14 allowed an empty/noise-free footer region to win. R7c-15 explicitly
    # prevents that diagnostic failure mode: when any region has price anchors,
    # a region without anchors gets a hard penalty and is marked ineligible.
    no_price_anchor_penalty = 0.45 if any_price_anchor and price_anchor_count == 0 else 0.0

    raw_score = (
        price_anchor_score
        + article_density_score
        + article_candidate_score
        + pair_alignment_score
        + ocr_presence_score
        - semantic_noise_penalty
        - footer_keyword_penalty
        - no_price_anchor_penalty
    )
    calibrated_score = round(clamp(raw_score, -1.0, 1.0), 4)

    eligible = bool(price_anchor_count > 0 or not any_price_anchor)
    explanation: list[str] = []
    if price_anchor_count == 0 and any_price_anchor:
        explanation.append("rejected_for_no_price_anchor_while_other_regions_have_anchors")
    if footer_hit_count:
        explanation.append("footer_or_payment_keywords_detected")
    if semantic_noise_count:
        explanation.append("semantic_noise_detected")
    if article_candidate_count or pair_alignment_count:
        explanation.append("positive_article_body_evidence_detected")
    if not explanation:
        explanation.append("weak_body_evidence")

    score_components = {
        "price_anchor_score": round(price_anchor_score, 4),
        "article_density_score": round(article_density_score, 4),
        "article_candidate_score": round(article_candidate_score, 4),
        "pair_alignment_score": round(pair_alignment_score, 4),
        "ocr_presence_score": round(ocr_presence_score, 4),
        "semantic_noise_penalty": round(semantic_noise_penalty, 4),
        "footer_keyword_penalty": round(footer_keyword_penalty, 4),
        "no_price_anchor_penalty": round(no_price_anchor_penalty, 4),
    }

    enriched = dict(region)
    enriched["eligible_body_region"] = eligible
    enriched["score_components"] = score_components
    enriched["calibrated_body_region_score"] = calibrated_score
    enriched["ranking_reason"] = ";".join(explanation)
    return enriched


def build_regions(topology: dict[str, Any], semantic: dict[str, Any]) -> list[dict[str, Any]]:
    sample_pairs = topology.get("sample_pairs") or []
    semantic_rows = semantic.get("rows") or []

    estimated_total_boxes = int(topology.get("ocr_box_count") or 0)
    approx_boxes_per_region = max(1, (estimated_total_boxes + 3) // 4)

    regions: list[dict[str, Any]] = []
    for index in range(4):
        related_pairs = sample_pairs[index::4]
        related_semantic = semantic_rows[index::4]
        line_texts: list[str] = []

        for pair in related_pairs:
            article = str(pair.get("article") or "").strip()
            price = str(pair.get("price") or "").strip()
            line_texts.append(f"{article} {price}".strip())

        for row in related_semantic:
            line_texts.append(str(row.get("line_text") or "").strip())

        combined_text = " ".join(text for text in line_texts if text)
        price_anchor_count = sum(1 for pair in related_pairs if contains_price(str(pair.get("price") or "")))
        article_candidate_count = sum(1 for row in related_semantic if bool(row.get("is_article_candidate")))
        semantic_noise_count = sum(1 for row in related_semantic if not bool(row.get("is_article_candidate")))
        pair_alignment_count = sum(
            1
            for pair in related_pairs
            if contains_price(str(pair.get("price") or "")) and str(pair.get("article") or "").strip()
        )
        density = round(article_candidate_count / max(1, len(related_semantic)), 4) if related_semantic else 0.0

        regions.append(
            {
                "region_id": f"region_{index + 1}",
                "y_top": round(index * 0.25, 2),
                "y_bottom": round((index + 1) * 0.25, 2),
                "ocr_box_count": approx_boxes_per_region,
                "price_anchor_count": price_anchor_count,
                "semantic_noise_count": semantic_noise_count,
                "article_candidate_count": article_candidate_count,
                "article_candidate_density": density,
                "pair_alignment_count": pair_alignment_count,
                "footer_keyword_hit_count": footer_keyword_hits(combined_text),
                "sample_text": combined_text[:240],
            }
        )
    return regions


def main() -> int:
    parser = argparse.ArgumentParser(description="R7c-15 AH foto 3 region scoring calibration diagnostics")
    parser.add_argument("--topology-json", required=True)
    parser.add_argument("--semantic-json", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--csv-out", required=True)
    args = parser.parse_args()

    topology = json.loads(Path(args.topology_json).read_text(encoding="utf-8"))
    semantic = json.loads(Path(args.semantic_json).read_text(encoding="utf-8"))

    regions = build_regions(topology, semantic)
    any_price_anchor = any(int(region.get("price_anchor_count") or 0) > 0 for region in regions)
    calibrated = [score_region(region, any_price_anchor=any_price_anchor) for region in regions]
    ranked = sorted(calibrated, key=lambda item: float(item["calibrated_body_region_score"]), reverse=True)

    eligible_ranked = [region for region in ranked if bool(region.get("eligible_body_region"))]
    best_region = eligible_ranked[0] if eligible_ranked else (ranked[0] if ranked else None)

    result = {
        "fixture_file": "AH foto 3.jpg",
        "diagnostic_only": True,
        "calibration_rule": "regions_without_price_anchors_are_ineligible_when_any_region_has_price_anchors",
        "input_summary": {
            "topology_candidate_pairs": int(topology.get("candidate_article_price_pairs") or 0),
            "semantic_article_candidate_count": int(semantic.get("article_candidate_count") or 0),
            "semantic_filtered_noise_count": int(semantic.get("filtered_noise_count") or 0),
        },
        "regions": ranked,
        "best_region": best_region,
    }

    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    csv_out = Path(args.csv_out)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "region_id",
        "y_top",
        "y_bottom",
        "ocr_box_count",
        "price_anchor_count",
        "semantic_noise_count",
        "article_candidate_count",
        "article_candidate_density",
        "pair_alignment_count",
        "footer_keyword_hit_count",
        "eligible_body_region",
        "calibrated_body_region_score",
        "ranking_reason",
        "sample_text",
    ]
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ranked)

    print("R7c-15 AH foto 3 region scoring calibration diagnostics")
    print(f"region_count: {len(ranked)}")
    print(f"any_price_anchor: {any_price_anchor}")
    print(f"best_region: {(best_region or {}).get('region_id', '')}")
    print(f"best_region_score: {(best_region or {}).get('calibrated_body_region_score', '')}")
    print(f"json_written: {json_out}")
    print(f"csv_written: {csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
