# R9-02D - Mojibake inventory receipt_service.py

Status: inventory only
Scope: backend/app/services/receipt_service.py
Runtime impact: none
Parser impact: none in this step
Database impact: none

## Context

During the R9-02 smokecheck, receipt import failed with a Python regex error. The runtime traceback showed a corrupted character range in a regular expression used by receipt parsing.

After checking the running container, the first reported regex had already been corrected in both GitHub and the container. A broader search then showed that receipt_service.py still contains multiple mojibake sequences in parsing strings and regexes.

This means the root cause is not a single failed extraction in R9-02. The file contains older encoding corruption that was activated again by the import path.

## Inventory summary

The following corruption categories were found.

| Category | Observed context | Intended meaning | Risk |
|---|---|---|---|
| Mojibake euro symbol | price and total regexes in Action, Gamma, Bol, Picnic and generic store text normalization | euro symbol | High |
| Mojibake accented characters | comments and at least one letter-range regex | Dutch accented letters | Medium to high |
| Mojibake middle dot | store-specific text normalization | middle dot separator | Low to medium |
| Mojibake zero-width characters | Picnic email cleanup | zero-width cleanup characters | Medium |
| Mojibake bullet | Picnic email cleanup | bullet character | Low |
| Mojibake Latin letter range | Picnic flattened block parser | Latin accented letter range | High |

## Affected parser areas

### 1. Generic store-specific text normalization

Area:

- _normalize_store_specific_text

Observed impact:

- euro symbol normalization is encoded as mojibake;
- middle dot normalization is encoded as mojibake.

Risk:

- email and PDF parsers may fail to match expected price patterns;
- text normalization may become inconsistent between stores.

### 2. Action PDF parser

Area:

- _parse_action_pdf_result

Observed impact:

- total amount regex uses mojibake euro;
- line amount regex uses mojibake euro.

Risk:

- Action receipt total or item lines may not parse.

### 3. Gamma PDF parser

Area:

- _parse_gamma_pdf_result

Observed impact:

- total including VAT regex contains mojibake euro;
- VAT detail line regex contains mojibake euro.

Risk:

- Gamma receipt totals and structured lines may fail.

### 4. Bol email parser

Area:

- _parse_bol_email_result

Observed impact:

- total regex and item price regex contain mojibake euro.

Risk:

- Bol email receipts may not parse totals and item prices.

### 5. Picnic email parser

Area:

- _parse_picnic_email_result
- _parse_picnic_flattened_blocks

Observed impact:

- zero-width cleanup chars are mojibake;
- bullet marker is mojibake;
- euro price regex is mojibake;
- Latin accented letter range is mojibake.

Risk:

- High, because one corrupted regex range can crash receipt import entirely.

## Root cause assessment

This is structural source-file encoding corruption, not a Docker-only runtime issue.

Evidence:

1. Git and runtime were in sync for the current branch.
2. The running container showed a corrected regex on the first reported line.
3. A broader grep in the running container still showed another corrupted regex range later in the file.
4. The local source file also showed multiple mojibake sequences in comments, strings and regexes.

## Recommended cleanup approach

Do not patch one regex at a time.

R9-02E should apply one controlled canonicalization pass over receipt_service.py with a fixed replacement table, then compile and smoke-test.

Suggested canonical replacement table:

| Mojibake meaning | Replacement |
|---|---|
| mojibake euro token | euro symbol |
| mojibake e-diaeresis token | e-diaeresis |
| mojibake middle-dot token | middle dot |
| mojibake zero-width token sequence | explicit Unicode escapes or empty cleanup target |
| mojibake bullet token | bullet |
| mojibake Latin range token | Latin-1 letter range or safer isalpha-based helper |

## Safer design recommendation

For character class checks, avoid fragile Unicode ranges in regexes where possible.

Instead of using a regex range for letters, prefer a helper such as:

```python
def _contains_letter(value: str) -> bool:
    return any(ch.isalpha() for ch in str(value or ''))
```

This avoids future mojibake crashes from malformed regex ranges.

## R9-02D conclusion

R9-02D is complete as an inventory step.

The next step should be R9-02E: controlled mojibake cleanup with compile, runtime verification and ALDI/Jumbo/Lidl smokecheck.

## Acceptance criteria for R9-02E

- No mojibake tokens remain in executable regexes.
- python -m py_compile succeeds.
- Backend starts.
- POST /api/receipts/import no longer crashes on ALDI image import.
- Route governance remains clean.
- No parser behavior is intentionally changed beyond restoring intended Unicode tokens.
