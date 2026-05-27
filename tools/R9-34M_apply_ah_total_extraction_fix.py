from pathlib import Path

path = Path("backend/app/receipt_ingestion/header_parser.py")
text = path.read_text(encoding="utf-8-sig")

old = """def _total_amount_from_lines(lines: list[str], filename: str) -> tuple[Decimal | None, bool]:
    amount_pattern = re.compile(r'(-?\\d{1,6}(?:[\\.,]\\d{2}))')
    explicit_total_pattern = re.compile(r'(?i)\\b(totaal|te betalen|te voldoen|eindtotaal|total due|amount due)\\b')
    subtotal_pattern = re.compile(r'(?i)\\b(subtotaal|subtotal)\\b')
    payment_pattern = re.compile(r'(?i)\\b(bankpas|pinnen|pin|betaald|betaling)\\b')
    vat_pattern = re.compile(r'(?i)\\b(btw|bedr\\.excl|bedr\\.incl|bedrag excl|bedrag incl)\\b')
    refund_pattern = re.compile(r'(?i)\\b(retour|refund|credit)\\b')
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
"""

new = """def _total_amount_from_lines(lines: list[str], filename: str) -> tuple[Decimal | None, bool]:
    amount_pattern = re.compile(r'(-?\\d{1,6}(?:[\\.,]\\d{2}))')
    explicit_total_pattern = re.compile(r'(?i)\\b(totaal|te betalen|te voldoen|eindtotaal|total due|amount due)\\b')
    subtotal_pattern = re.compile(r'(?i)\\b(subtotaal|subtotal)\\b')
    payment_pattern = re.compile(r'(?i)\\b(bankpas|pinnen|pin|betaald|betaling)\\b')
    vat_pattern = re.compile(r'(?i)\\b(btw|bedr\\.excl|bedr\\.incl|bedrag excl|bedrag incl)\\b')
    refund_pattern = re.compile(r'(?i)\\b(retour|refund|credit)\\b')
    ah_context = (
        'ah ' in str(filename or '').lower()
        or 'ah_' in str(filename or '').lower()
        or 'albert heijn' in ' '.join(str(line or '') for line in lines[:20]).lower()
        or 'ah to go' in ' '.join(str(line or '') for line in lines[:20]).lower()
    )
    candidates: list[tuple[int, int, Decimal, bool]] = []
    in_vat_block = False

    def _amounts(value: str) -> list[Decimal]:
        parsed = [_parse_decimal(item) for item in amount_pattern.findall(str(value or ''))]
        return [item for item in parsed if item is not None and _is_plausible_total_amount(item)]

    for index, line in enumerate(lines):
        lowered = str(line or '').lower()
        if vat_pattern.search(lowered) or lowered.startswith('%'):
            in_vat_block = True
        parsed_matches = _amounts(str(line or ''))

        if subtotal_pattern.search(lowered):
            continue
        if any(token in lowered for token in ('voordeel', 'korting', 'waarvan', 'bonus box', 'app deals')):
            continue

        explicit = bool(explicit_total_pattern.search(lowered))
        payment = bool(payment_pattern.search(lowered))
        if not explicit and not payment:
            continue

        if parsed_matches:
            amount = parsed_matches[-1]
            score = 0
            if explicit:
                score += 40
            if payment:
                score += 25
            if 'te betalen' in lowered:
                score += 35
            if 'eur' in lowered:
                score += 10
            if in_vat_block or vat_pattern.search(lowered):
                score -= 100
            if refund_pattern.search(lowered):
                score -= 60
            if len(parsed_matches) > 1:
                score -= 10 * (len(parsed_matches) - 1)
            candidates.append((score, index, amount, explicit))
            continue

        # R9-34M: AH-photo receipts can have the total context on one line
        # and the amount on the next OCR line, e.g. \"TE BETALEN\" followed by \"5,40\".
        if ah_context and (explicit or payment):
            for offset, next_line in enumerate(lines[index + 1:index + 5], start=1):
                next_lowered = str(next_line or '').lower()
                if subtotal_pattern.search(next_lowered):
                    break
                if any(token in next_lowered for token in ('voordeel', 'korting', 'waarvan', 'bonus box', 'app deals')):
                    break
                if vat_pattern.search(next_lowered) or next_lowered.startswith('%'):
                    break
                next_amounts = _amounts(str(next_line or ''))
                if not next_amounts:
                    if offset >= 2 and re.search(r'[A-Za-z]', str(next_line or '')):
                        break
                    continue
                amount = next_amounts[-1]
                score = 0
                if explicit:
                    score += 55
                if payment:
                    score += 30
                if 'te betalen' in lowered:
                    score += 45
                score -= offset * 5
                candidates.append((score, index, amount, explicit))
                break

    if not candidates:
        return None, False
    valid_candidates = [candidate for candidate in candidates if candidate[0] > 0]
    chosen = sorted(valid_candidates or candidates, key=lambda item: (item[0], item[1]))[-1]
    return chosen[2], chosen[3]
"""

if old not in text:
    raise SystemExit("R9-34M patch failed: expected _total_amount_from_lines block not found")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("R9-34M patch applied to backend/app/receipt_ingestion/header_parser.py")
