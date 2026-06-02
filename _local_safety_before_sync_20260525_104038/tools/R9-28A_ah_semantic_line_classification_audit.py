from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


AH_FILENAMES = {
    "ah foto 1.pdf",
    "ah foto 2.jpeg",
    "ah foto 3.jpg",
    "ah app 1.pdf",
}

DEFAULT_BASE_URL = "http://localhost:8011"
DEFAULT_TOKEN = "rezzerv-dev-token::admin@rezzerv.local"
DEFAULT_HOUSEHOLD_ID = "1"

AMOUNT_RE = re.compile(r"(?<!\d)(-?\d{1,3}(?:[.,]\d{2}))(?!\d)")
NUMBER_RE = re.compile(r"(?<!\d)(\d+)(?!\d)")

TOTAL_PATTERNS = [
    r"\b(totaal|te\s*betalen|subtotaal|saldo)\b",
]
PAYMENT_PATTERNS = [
    r"\b(pin|maestro|visa|mastercard|contactloos|contant|betaald|betaling|wisselgeld|bankpas|transactie)\b",
]
TAX_PATTERNS = [
    r"\b(btw|vat|laag|hoog|tarief|netto|belasting)\b",
]
DISCOUNT_PATTERNS = [
    r"\b(bonus|korting|actie|voordeel|aanbieding|prijsvoordeel|koopkorting|bonuskaart|2e\s*halve|gratis|retour)\b",
]
LOYALTY_STAMP_PATTERNS = [
    r"\b(zegel|zegels|koopzegel|koopzegels|premiumzegel|premiumzegels|spaarzegel|spaarzegels)\b",
]
LOYALTY_POINTS_PATTERNS = [
    r"\b(punt|punten|air\s*miles|bonuspunten|loyalty|persoonlijke\s*bonus|kaartnummer)\b",
]
METADATA_PATTERNS = [
    r"\b(albert\s*heijn|ah\.?|winkel|filiaal|kassa|bonnr|bonnummer|datum|tijd|www\.|klantenservice|welkom|bedankt|adres|straat|tel|kvk|transactie)\b",
]
NOISE_PATTERNS = [
    r"^[\W_]+$",
    r"^\s*$",
]


@dataclass
class SemanticLine:
    raw_line: str
    normalized_line: str
    amount_detected: float | None
    line_type: str
    article_candidate: bool
    financial_effect: str
    loyalty_effect: bool
    include_in_article_count: bool
    include_in_article_sum: bool
    include_in_total_validation: bool
    rule_id: str
    reason: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _amount(text: str) -> float | None:
    matches = AMOUNT_RE.findall(text or "")
    if not matches:
        return None
    raw = matches[-1].replace(",", ".")
    try:
        return float(raw)
    except Exception:
        return None


def _match_any(norm: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, norm, re.IGNORECASE) for pattern in patterns)


def classify_ah_line(raw_line: str) -> SemanticLine:
    norm = _normalize(raw_line)
    amount = _amount(norm)

    if _match_any(norm, NOISE_PATTERNS):
        return SemanticLine(raw_line, norm, amount, "AH_NOISE", False, "none", False, False, False, False, "AH_NOISE_RULE", "lege of niet-informatieve OCR-regel")

    if _match_any(norm, TOTAL_PATTERNS):
        return SemanticLine(raw_line, norm, amount, "AH_TOTAL", False, "total", False, False, False, True, "AH_TOTAL_RULE", "totaal/subtotaalregel; niet als artikel tellen")

    if _match_any(norm, PAYMENT_PATTERNS):
        return SemanticLine(raw_line, norm, amount, "AH_PAYMENT", False, "payment", False, False, False, False, "AH_PAYMENT_RULE", "betaalregel; niet als artikel tellen")

    if _match_any(norm, TAX_PATTERNS):
        return SemanticLine(raw_line, norm, amount, "AH_TAX", False, "tax", False, False, False, False, "AH_TAX_RULE", "btw/fiscale regel; niet als artikel tellen")

    if _match_any(norm, LOYALTY_STAMP_PATTERNS):
        financial = "loyalty_amount" if amount is not None else "none"
        include_total = amount is not None
        return SemanticLine(raw_line, norm, amount, "AH_LOYALTY_STAMPS", False, financial, True, False, False, include_total, "AH_LOYALTY_STAMPS_RULE", "zegels/koopzegels expliciet bewaren, maar niet als artikel tellen")

    if _match_any(norm, LOYALTY_POINTS_PATTERNS):
        return SemanticLine(raw_line, norm, amount, "AH_LOYALTY_POINTS", False, "none", True, False, False, False, "AH_LOYALTY_POINTS_RULE", "punten/klantkaartinformatie expliciet bewaren, maar niet als artikel tellen")

    if _match_any(norm, DISCOUNT_PATTERNS):
        financial = "discount" if amount is not None else "discount_metadata"
        include_total = amount is not None
        return SemanticLine(raw_line, norm, amount, "AH_DISCOUNT", False, financial, False, False, False, include_total, "AH_DISCOUNT_RULE", "korting/bonus bewaren als financiële correctie, niet als artikel")

    if _match_any(norm, METADATA_PATTERNS) and amount is None:
        return SemanticLine(raw_line, norm, amount, "AH_METADATA", False, "none", False, False, False, False, "AH_METADATA_RULE", "metadata zonder bedrag; niet als artikel tellen")

    # Article rule: has text and a price amount, while not matching total/payment/tax/discount/loyalty.
    # Deliberately conservative: short numeric-only lines are not articles.
    alpha_chars = len(re.findall(r"[a-zA-ZÀ-ÿ]", norm))
    if amount is not None and alpha_chars >= 3:
        return SemanticLine(raw_line, norm, amount, "AH_ARTICLE", True, "article_price", False, True, True, True, "AH_ARTICLE_WITH_PRICE_RULE", "artikelkandidaat met tekst en bedrag")

    if amount is not None:
        return SemanticLine(raw_line, norm, amount, "AH_METADATA", False, "amount_metadata", False, False, False, True, "AH_AMOUNT_METADATA_RULE", "bedrag zonder duidelijke artikeltekst; bewaren voor validatie maar niet als artikel")

    return SemanticLine(raw_line, norm, amount, "AH_METADATA", False, "none", False, False, False, False, "AH_METADATA_FALLBACK_RULE", "geen artikel-, korting-, loyalty-, totaal- of betaalpatroon")


def _http_json(url: str, token: str) -> Any:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_line_diagnosis(base_url: str, household_id: str, token: str) -> Any:
    url = f"{base_url.rstrip('/')}/api/testing/receipt-line-diagnosis/download?householdId={household_id}"
    return _http_json(url, token)


def _find_latest_line_diagnosis(reports_dir: Path) -> Path | None:
    candidates = sorted(
        [*reports_dir.glob("*receipt_line_diagnosis*.json"), *reports_dir.glob("*line_diagnosis*.json"), *reports_dir.glob("R9-23*.json")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _load_input(args: argparse.Namespace) -> Any:
    if args.input_json:
        return json.loads(Path(args.input_json).read_text(encoding="utf-8"))

    if args.download:
        return _download_line_diagnosis(args.base_url, args.household_id, args.token)

    latest = _find_latest_line_diagnosis(Path(args.reports_dir))
    if latest:
        print(f"R9-28A gebruikt bestaande diagnose: {latest}")
        return json.loads(latest.read_text(encoding="utf-8"))

    raise SystemExit(
        "Geen input gevonden. Gebruik --download of geef --input-json mee met een bestaande line-diagnosis JSON."
    )


def _iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_dicts(item)


def _filename_of(record: dict[str, Any]) -> str | None:
    for key in ("bestand", "filename", "file", "source_filename", "member", "name"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value).name
    return None


def _line_text_of(record: dict[str, Any]) -> str | None:
    for key in ("raw_line", "raw_text", "line", "text", "ocr_text", "normalized_line"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _extract_ah_lines(data: Any) -> dict[str, list[str]]:
    by_file: dict[str, list[str]] = {name: [] for name in sorted(AH_FILENAMES)}

    current_file: str | None = None

    for record in _iter_dicts(data):
        fname = _filename_of(record)
        if fname and fname.lower() in AH_FILENAMES:
            current_file = fname.lower()

            # Common structure: record has lines as list.
            for line_key in ("lines", "classified_lines", "ocr_lines", "raw_lines", "diagnostic_lines"):
                lines = record.get(line_key)
                if isinstance(lines, list):
                    for item in lines:
                        if isinstance(item, str):
                            by_file[current_file].append(item)
                        elif isinstance(item, dict):
                            text = _line_text_of(item)
                            if text:
                                by_file[current_file].append(text)

        text = _line_text_of(record)
        if text and current_file:
            # Avoid adding filename metadata rows as OCR lines.
            if text.lower() not in AH_FILENAMES:
                by_file[current_file].append(text)

    # Deduplicate while preserving order
    result: dict[str, list[str]] = {}
    for fname, lines in by_file.items():
        seen = set()
        out = []
        for line in lines:
            key = line.strip()
            if key and key not in seen:
                seen.add(key)
                out.append(line)
        result[fname] = out
    return result


def _summarize(lines: list[SemanticLine]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    article_sum = 0.0
    validation_sum = 0.0
    discounts = 0.0
    loyalty_amount = 0.0

    for line in lines:
        counts[line.line_type] = counts.get(line.line_type, 0) + 1
        if line.include_in_article_sum and line.amount_detected is not None:
            article_sum += line.amount_detected
        if line.include_in_total_validation and line.amount_detected is not None:
            validation_sum += line.amount_detected
        if line.line_type == "AH_DISCOUNT" and line.amount_detected is not None:
            discounts += line.amount_detected
        if line.line_type == "AH_LOYALTY_STAMPS" and line.amount_detected is not None:
            loyalty_amount += line.amount_detected

    return {
        "line_type_counts": counts,
        "article_count": sum(1 for line in lines if line.include_in_article_count),
        "article_sum": round(article_sum, 2),
        "validation_sum": round(validation_sum, 2),
        "discount_amount_sum": round(discounts, 2),
        "loyalty_amount_sum": round(loyalty_amount, 2),
        "loyalty_line_count": sum(1 for line in lines if line.loyalty_effect),
    }


def build_audit(data: Any) -> dict[str, Any]:
    ah_lines = _extract_ah_lines(data)
    receipts: list[dict[str, Any]] = []

    for fname, raw_lines in sorted(ah_lines.items()):
        semantic = [classify_ah_line(line) for line in raw_lines]
        receipts.append(
            {
                "bestand": fname,
                "line_count": len(raw_lines),
                "summary": _summarize(semantic),
                "lines": [asdict(line) for line in semantic],
            }
        )

    return {
        "audit": "R9-28A AH semantic line classification audit",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "AH only; audit only; no parser/status/baseline mutation",
        "line_types": [
            "AH_ARTICLE",
            "AH_DISCOUNT",
            "AH_LOYALTY_STAMPS",
            "AH_LOYALTY_POINTS",
            "AH_TOTAL",
            "AH_SUBTOTAL",
            "AH_PAYMENT",
            "AH_TAX",
            "AH_METADATA",
            "AH_NOISE",
        ],
        "rules": {
            "discounts": "kept as AH_DISCOUNT; not counted as article; may affect total validation",
            "loyalty": "kept as AH_LOYALTY_*; not counted as article",
            "articles": "only AH_ARTICLE contributes to article_count and article_sum",
        },
        "receipts": receipts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="R9-28A AH semantic line classification audit.")
    parser.add_argument("--input-json", default=None, help="Optional existing receipt-line diagnosis JSON.")
    parser.add_argument("--download", action="store_true", help="Download current line diagnosis from backend testing endpoint.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    parser.add_argument("--household-id", default=DEFAULT_HOUSEHOLD_ID)
    parser.add_argument("--reports-dir", default="tools/reports")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    data = _load_input(args)
    audit = build_audit(data)

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else reports_dir / f"R9-28A_ah_semantic_line_classification_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"R9-28A AH semantic audit geschreven naar: {out}")
    for receipt in audit["receipts"]:
        print(
            f"{receipt['bestand']}: lines={receipt['line_count']} "
            f"article_count={receipt['summary']['article_count']} "
            f"article_sum={receipt['summary']['article_sum']} "
            f"types={receipt['summary']['line_type_counts']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
