from __future__ import annotations

import json
from typing import Any

from app.services.receipt_service import _extract_receipt_lines

TEST_LINES = [
    "Maaltijdsauzen SK7 1,79 B",
    "Lasagnebladen 500g 1,69 B",
    "Crème frache 30% 0,99 B",
    "Tortilla chips XXL 1,29 B",
    "AH soep 570ml 2,49",
    "Jumbo 4-pack wraps 3,19",
    "Totaal 40,75",
    "Bankpas 40,75",
    "B 9 37,39 3,36 40,75",
    "Lidl Plus korting -0,40",
]


def _line_payload(line: dict[str, Any]) -> dict[str, Any]:
    trace = line.get("producer_trace") if isinstance(line, dict) else None
    if not isinstance(trace, dict):
        trace = {}
    return {
        "source_index": line.get("source_index"),
        "raw_label": line.get("raw_label"),
        "normalized_label": line.get("normalized_label"),
        "quantity": line.get("quantity"),
        "unit": line.get("unit"),
        "unit_price": line.get("unit_price"),
        "line_total": line.get("line_total"),
        "discount_amount": line.get("discount_amount"),
        "classification": trace.get("classification"),
        "classification_rule": trace.get("classification_rule"),
        "classification_stage": trace.get("classification_stage"),
        "append_allowed": trace.get("append_allowed"),
    }


def main() -> int:
    results = []
    for source_line in TEST_LINES:
        parsed = _extract_receipt_lines([source_line], store_name="Lidl", filename="R9-38A2c candidate check")
        results.append(
            {
                "source_line": source_line,
                "parsed_count": len(parsed),
                "parsed_lines": [_line_payload(line) for line in parsed],
            }
        )

    output = {
        "test": "R9-38A2c embedded code product candidate check",
        "mode": "read_only_candidate_check",
        "parser_changed": False,
        "status_classification_changed": False,
        "results": results,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))

    failures = []
    expected_articles = TEST_LINES[:6]
    expected_non_articles = TEST_LINES[6:]
    for item in results:
        if item["source_line"] in expected_articles and item["parsed_count"] != 1:
            failures.append({"source_line": item["source_line"], "reason": "expected_article_not_parsed"})
        if item["source_line"] in expected_non_articles and item["parsed_count"] != 0:
            failures.append({"source_line": item["source_line"], "reason": "expected_non_article_was_parsed"})

    if failures:
        print("R9-38A2C EMBEDDED CODE CANDIDATE CHECK FAILED")
        print(json.dumps({"failures": failures}, indent=2, ensure_ascii=False))
        return 1

    print("R9-38A2C EMBEDDED CODE CANDIDATE CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
