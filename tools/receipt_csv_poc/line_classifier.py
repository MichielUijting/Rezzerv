import re
from dataclasses import dataclass

AMOUNT_RE = re.compile(r"(?<!\d)-?\d{1,4}[\.,]\d{2}(?!\d)")
TIME_RANGE_RE = re.compile(r"\b\d{1,2}[\.:,]\d{2}\s*[-–~]\s*\d{1,2}[\.:,]\d{2}\b")
DATE_RE = re.compile(r"\b\d{1,2}[-\./]\d{1,2}[-\./]\d{2,4}\b")
QUANTITY_MULTIPLIER_RE = re.compile(r"\b\d+(?:[\.,]\d+)?\s*[xX]\s*\d+[\.,]\d{2}\b")
WEIGHT_PRICE_RE = re.compile(r"\b\d+[\.,]\d{3}\s*(kg|g|l|ml)\s*[xX]\s*\d+[\.,]\d{2}\b", re.I)

LINE_TYPES = {
    "product_line",
    "quantity_line",
    "discount_line",
    "total_line",
    "payment_line",
    "vat_line",
    "metadata_line",
    "noise_line",
    "unknown_line",
}

TOTAL_KEYWORDS = ["totaal", "sub totaal", "subtotaal", "bedrag euro", "bedrag = euro"]
PAYMENT_KEYWORDS = [
    "pin", "pinnen", "bankpas", "betaald", "betaling", "v pay", "v-pay",
    "visa", "maestro", "mastercard", "contant", "contactless",
    "kaartbetaling", "akkoord", "wisselgeld",
]
VAT_KEYWORDS = [
    "btw", "biw", "bedrag excl", "bedr.excl", "btw-bedrag",
    "netto", "bruto", "incl", "excl", "9,00%", "0,00%",
]
DISCOUNT_KEYWORDS = [
    "korting", "bonus", "actie", "prijsvoordeel", "gratis",
    "jouw voordeel", "lidl plus korting", "totaal korting",
]
METADATA_KEYWORDS = [
    "openingstijd", "openingstijden", "maandag", "dinsdag", "woensdag",
    "donderdag", "vrijdag", "zaterdag", "zondag", "ma-vr", "ma tm",
    "poi", "terminal", "merchant", "periode", "transactie",
    "autorisatie", "klantticket", "kopie kaarthouder", "kaart",
    "kaartnr", "kaartserienummer", "aantal artikelen", "aantal art",
    "gespaard", "ingewisseld", "nieuw saldo", "oud saldo", "pasnummer",
    "store", "pos", "bonnr", "merchant ref", "filiaal", "bedankt",
    "dank u", "vragen over", "www.", ".nl", ".com",
]

NOISE_CHARS_RE = re.compile(r"[{}\[\]~^_<>]")
ALPHA_RE = re.compile(r"[A-Za-zÀ-ÿ]")


@dataclass(frozen=True)
class ClassifiedLine:
    line_no: int
    raw_line: str
    normalized_line: str
    line_type: str
    reason: str


def normalize_line(line: str) -> str:
    return " ".join(line.strip().split())


def contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def amount_count(line: str) -> int:
    return len(AMOUNT_RE.findall(line))


def classify_line(raw_line: str) -> tuple[str, str]:
    line = normalize_line(raw_line)
    lowered = line.lower()
    amounts = amount_count(line)

    if not line:
        return "unknown_line", "empty"

    if len(line) > 80 and amounts == 0:
        return "noise_line", "very_long_no_amount"

    if not ALPHA_RE.search(line) and amounts == 0:
        return "noise_line", "no_alpha_no_amount"

    if len(NOISE_CHARS_RE.findall(line)) >= 2 and amounts == 0:
        return "noise_line", "noise_chars_no_amount"

    if TIME_RANGE_RE.search(line) or contains_any(lowered, ["openingstijd", "ma-vr", "ma tm"]):
        return "metadata_line", "opening_hours"

    if contains_any(lowered, DISCOUNT_KEYWORDS):
        return "discount_line", "discount_keyword"

    if contains_any(lowered, VAT_KEYWORDS):
        return "vat_line", "vat_keyword"

    if contains_any(lowered, PAYMENT_KEYWORDS):
        return "payment_line", "payment_keyword"

    if contains_any(lowered, METADATA_KEYWORDS):
        return "metadata_line", "metadata_keyword"

    if contains_any(lowered, TOTAL_KEYWORDS):
        return "total_line", "total_keyword"

    if DATE_RE.search(line) and amounts <= 1:
        return "metadata_line", "date_like"

    if WEIGHT_PRICE_RE.search(line):
        return "quantity_line", "weight_price_pattern"

    if QUANTITY_MULTIPLIER_RE.search(line):
        text_without_numbers = re.sub(r"[\d\sXx\.,€-]", "", line)
        if len(text_without_numbers) <= 3:
            return "quantity_line", "quantity_only_pattern"
        return "product_line", "product_with_quantity_pattern"

    if amounts == 0:
        return "unknown_line", "no_amount"

    if amounts >= 1 and ALPHA_RE.search(line):
        return "product_line", "amount_and_text"

    return "unknown_line", "fallback"


def classify_lines(text: str) -> list[ClassifiedLine]:
    classified = []
    for idx, raw_line in enumerate(text.splitlines(), start=1):
        line_type, reason = classify_line(raw_line)
        classified.append(
            ClassifiedLine(
                line_no=idx,
                raw_line=raw_line,
                normalized_line=normalize_line(raw_line),
                line_type=line_type,
                reason=reason,
            )
        )
    return classified


def summarize_line_types(classified_lines: list[ClassifiedLine]) -> dict[str, int]:
    summary = {line_type: 0 for line_type in sorted(LINE_TYPES)}
    for line in classified_lines:
        summary[line.line_type] = summary.get(line.line_type, 0) + 1
    return summary
