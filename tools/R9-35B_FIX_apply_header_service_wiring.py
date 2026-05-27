from pathlib import Path
import re

root = Path(".")
header_path = root / "backend/app/receipt_ingestion/header_parser.py"
service_path = root / "backend/app/services/receipt_service.py"

header = header_path.read_text(encoding="utf-8-sig")
service = service_path.read_text(encoding="utf-8-sig")

# ------------------------------------------------------------
# 1. header_parser.py: verwijder AH-specifieke total-logica.
#    Alles vanaf de eerste AH-helper of _total_amount_from_lines
#    wordt vervangen door een generieke non-profile extractor.
# ------------------------------------------------------------

markers = [
    "def _looks_like_ah_context",
    "def _total_amount_from_lines(lines: list[str], filename: str) -> tuple[Decimal | None, bool]:",
]
positions = [header.find(marker) for marker in markers if header.find(marker) >= 0]
if not positions:
    raise SystemExit("R9-35B-FIX failed: total extraction area not found in header_parser.py")

cut = min(positions)
prefix = header[:cut]

# Zorg dat _is_plausible_total_amount beschikbaar blijft voor de generieke extractor.
if "_is_plausible_total_amount" not in prefix:
    single_import = "from app.receipt_ingestion.fingerprints import _is_plausible_purchase_at"
    multi_import = (
        "from app.receipt_ingestion.fingerprints import (\n"
        "    _is_plausible_purchase_at,\n"
        "    _is_plausible_total_amount,\n"
        ")\n"
    )
    if single_import in prefix:
        prefix = prefix.replace(single_import + "\n", multi_import)
    else:
        raise SystemExit("R9-35B-FIX failed: fingerprints import not found in header_parser.py")

generic_total = r'''
def _total_amount_from_lines(lines: list[str], filename: str) -> tuple[Decimal | None, bool]:
    """Generic non-profile total extraction.

    Store-specific total semantics must live in store profiles.
    AH total semantics are implemented in profiles/ah/totals.py.
    """
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

header_path.write_text(prefix.rstrip() + "\n\n" + generic_total.lstrip(), encoding="utf-8")

# ------------------------------------------------------------
# 2. receipt_service.py: importeer AH-total profile robuust.
# ------------------------------------------------------------

ah_total_import = (
    "from app.receipt_ingestion.profiles.ah.totals import "
    "extract_ah_total_amount, looks_like_ah_context"
)

if ah_total_import not in service:
    lines = service.splitlines()
    insert_at = None

    for i, line in enumerate(lines):
        if "app.receipt_ingestion.profiles.ah_runtime import" in line:
            insert_at = i + 1
            break

    if insert_at is None:
        for i, line in enumerate(lines):
            if "apply_receipt_image_preprocessing import" in line:
                insert_at = i + 1
                break

    if insert_at is None:
        raise SystemExit("R9-35B-FIX failed: no safe import insertion point found in receipt_service.py")

    lines.insert(insert_at, ah_total_import)
    service = "\n".join(lines) + "\n"

# ------------------------------------------------------------
# 3. receipt_service.py: route total_amount voor AH via profiel.
# ------------------------------------------------------------

old = "    total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)"
new = """    if looks_like_ah_context(text_lines, filename, store_name=store_name):
        ah_total_result = extract_ah_total_amount(text_lines, filename, store_name=store_name)
        total_amount = ah_total_result.amount
        explicit_total_found = ah_total_result.explicit_total_found
    else:
        total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)"""

if old in service:
    service = service.replace(old, new, 1)
elif "extract_ah_total_amount(text_lines, filename, store_name=store_name)" in service:
    pass
else:
    raise SystemExit("R9-35B-FIX failed: total_amount assignment not found in receipt_service.py")

service_path.write_text(service, encoding="utf-8")

# ------------------------------------------------------------
# 4. Verificaties.
# ------------------------------------------------------------

header_after = header_path.read_text(encoding="utf-8-sig")
service_after = service_path.read_text(encoding="utf-8-sig")

for forbidden in [
    "_ah_strict_total_amount_from_lines",
    "_normalize_ah_total_anchor",
    "TE BETALEN wins over TOTAAL",
    "R9-34R rules",
]:
    if forbidden in header_after:
        raise SystemExit(f"R9-35B-FIX verification failed: AH-specific total logic remains in header_parser.py: {forbidden}")

if "candidate_total = line_sum +" in service_after:
    raise SystemExit("R9-35B-FIX verification failed: line-sum total fallback returned")

if ah_total_import not in service_after:
    raise SystemExit("R9-35B-FIX verification failed: AH totals profile import missing")

if "extract_ah_total_amount(text_lines, filename, store_name=store_name)" not in service_after:
    raise SystemExit("R9-35B-FIX verification failed: AH totals profile not wired")

print("R9-35B-FIX applied: AH totals profile wired and generic header_parser cleaned")
