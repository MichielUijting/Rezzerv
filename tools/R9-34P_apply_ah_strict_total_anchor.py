from pathlib import Path

path = Path("backend/app/receipt_ingestion/header_parser.py")
text = path.read_text(encoding="utf-8-sig")

marker = "def _total_amount_from_lines(lines: list[str], filename: str) -> tuple[Decimal | None, bool]:"
start = text.find(marker)
if start < 0:
    raise SystemExit("R9-34P failed: _total_amount_from_lines niet gevonden")

prefix = text[:start]

replacement = r'''def _looks_like_ah_context(lines: list[str], filename: str) -> bool:
    haystack = ' '.join(str(line or '') for line in lines[:20]).lower()
    lower_filename = str(filename or '').lower()
    return (
        'ah ' in lower_filename
        or 'ah_' in lower_filename
        or 'albert heijn' in haystack
        or 'ah to go' in haystack
        or re.search(r'\bah\b', haystack) is not None
    )


def _normalize_ah_total_anchor(value: str | None) -> str:
    normalized = str(value or '').upper()
    normalized = re.sub(r'[^A-Z\s]+', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def _amounts_from_text(value: str | None) -> list[Decimal]:
    amounts: list[Decimal] = []
    for match in re.finditer(r'(?<!\d)(-?\d{1,6}(?:[\.,]\d{2}))(?!\d)', str(value or '')):
        parsed = _parse_decimal(match.group(1))
        if parsed is not None and _is_plausible_total_amount(parsed):
            amounts.append(parsed)
    return amounts


def _line_without_amounts(value: str | None) -> str:
    cleaned = re.sub(r'(?<!\d)-?\d{1,6}(?:[\.,]\d{2})(?!\d)', ' ', str(value or ''))
    cleaned = re.sub(r'\b(?:EUR|EURO)\b|€', ' ', cleaned, flags=re.IGNORECASE)
    return cleaned


def _ah_strict_total_amount_from_lines(lines: list[str]) -> tuple[Decimal | None, bool]:
    """AH total extraction: only exact TOTAAL / TE BETALEN anchors may carry total_amount.

    SSOT guardrail: article line sums are never used as source for total_amount.
    """
    for index, raw_line in enumerate(lines):
        line = str(raw_line or '').strip()
        if not line:
            continue

        # Same-line form: valid only if removing the amount leaves exactly the anchor.
        same_line_amounts = _amounts_from_text(line)
        if same_line_amounts:
            anchor_after_amount_removal = _normalize_ah_total_anchor(_line_without_amounts(line))
            if anchor_after_amount_removal in {'TOTAAL', 'TE BETALEN'}:
                return same_line_amounts[-1], True
            continue

        # Separate-line form: context line must be exactly TOTAAL or TE BETALEN.
        anchor = _normalize_ah_total_anchor(line)
        if anchor not in {'TOTAAL', 'TE BETALEN'}:
            continue

        # Strict: only the direct next OCR line may carry the amount.
        if index + 1 >= len(lines):
            continue
        next_line = str(lines[index + 1] or '').strip()
        next_amounts = _amounts_from_text(next_line)
        if not next_amounts:
            continue

        return next_amounts[-1], True

    return None, False


def _total_amount_from_lines(lines: list[str], filename: str) -> tuple[Decimal | None, bool]:
    # R9-34P-CORRECTED-STRICT:
    # AH uses only exact total anchors:
    # - TOTAAL
    # - TE BETALEN
    # No article line sum fallback. No generic "contains totaal" matching for AH.
    if _looks_like_ah_context(lines, filename):
        return _ah_strict_total_amount_from_lines(lines)

    amount_pattern = re.compile(r'(-?\d{1,6}(?:[\.,]\d{2}))')
    explicit_total_pattern = re.compile(r'(?i)\b(totaal|te betalen|te voldoen|eindtotaal|total due|amount due)\b')
    subtotal_pattern = re.compile(r'(?i)\b(subtotaal|subtotal)\b')
    payment_pattern = re.compile(r'(?i)\b(bankpas|pinnen|pin|betaald|betaling)\b')
    vat_pattern = re.compile(r'(?i)\b(btw|bedr\.excl|bedr\.incl|bedrag excl|bedrag incl)\b')
    refund_pattern = re.compile(r'(?i)\b(retour|refund|credit)\b')
    candidates: list[tuple[int, int, Decimal, bool]] = []
    in_vat_block = False

    for index, line in enumerate(lines):
        lowered = str(line or '').lower()
        if vat_pattern.search(lowered) or lowered.startswith('%'):
            in_vat_block = True

        matches = amount_pattern.findall(str(line or ''))
        parsed_matches = [_parse_decimal(item) for item in matches]
        parsed_matches = [item for item in parsed_matches if item is not None]

        if not parsed_matches:
            continue
        if subtotal_pattern.search(lowered):
            continue
        if any(token in lowered for token in ('voordeel', 'korting', 'waarvan', 'bonus box')):
            continue

        explicit = bool(explicit_total_pattern.search(lowered))
        payment = bool(payment_pattern.search(lowered))
        if not explicit and not payment:
            continue

        amount = parsed_matches[-1]
        score = 0
        if explicit:
            score += 40
        if payment:
            score += 25
        if 'eur' in lowered:
            score += 10
        if in_vat_block or vat_pattern.search(lowered):
            score -= 100
        if refund_pattern.search(lowered):
            score -= 60
        if len(parsed_matches) > 1:
            score -= 10 * (len(parsed_matches) - 1)

        if _is_plausible_total_amount(amount):
            candidates.append((score, index, amount, explicit))

    if not candidates:
        return None, False

    valid_candidates = [candidate for candidate in candidates if candidate[0] > 0]
    chosen = sorted(valid_candidates or candidates, key=lambda item: (item[0], item[1]))[-1]
    return chosen[2], chosen[3]
'''

path.write_text(prefix + replacement, encoding="utf-8")
print("R9-34P-CORRECTED-STRICT applied to backend/app/receipt_ingestion/header_parser.py")
