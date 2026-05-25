# R9-SYNC-REVIEW-CLEANUP decision manifest — 2026-05-25

## Branches

- Source review/provenance branch: `review/local-r9-patches-before-final-sync-20260525`
- Clean integration branch: `cleanup/r9-sync-review-safe-diagnostics-20260525`
- Base branch: `sync/local-rezzerv-receipt-basis-v2` at `0203496`

## Purpose

This cleanup branch deliberately does **not** merge the full review branch. The review branch is a safety/provenance snapshot of local R9 patches. This cleanup branch is for selective, low-risk integration only.

## SSOT guardrails

- No receipt status determination is added.
- `receipt_status_baseline_service_v4.py` remains the only source for PO-normalized receipt status.
- No parser status is promoted to truth.
- No UI status logic is changed.
- Runtime receipt parsing behavior is not broadened by this cleanup branch.

## Review findings

### Do not merge the full review branch

The review branch contains a mixed set of changes:

- runtime preprocessing behavior;
- diagnostics;
- one-off root-level patch scripts;
- debug/export tools;
- historical local patch provenance.

The branch is valuable as an audit/provenance snapshot, but too broad for direct merge into the working branch.

### `receipt_image_preprocessing.py`

The review branch changes preprocessing behavior. The PCA/rembg route is gated to AH foto 3, but the fallback route still re-encodes image bytes as PNG. Because `parse_receipt_content(...)` feeds preprocessing output into Paddle and Tesseract, this is functional OCR-input behavior, not pure diagnostics. It is intentionally not included in this cleanup branch.

### `main.py` R9-29A4 middleware

The review branch adds middleware that augments existing JSON debug/explainability responses with preprocessing diagnostics by consuming and rebuilding responses. That is diagnostically useful but not acceptable as final architecture in `main.py`. It should be replaced later by a dedicated diagnostics helper/router.

### `receipt_service.py` sparse-line bug

Review found an existing runtime bug in `_extract_sparse_receipt_lines(...)`: the `qty_x_amount` branch passes `amount1_raw=str(unit_price)` while `unit_price` is not defined in that block.

Required fix before merge to working branch:

```python
unit_price = (amount / quantity).quantize(Decimal('0.01')) if quantity else amount
```

inserted after `quantity` and `amount` are validated and before `append_product_candidate(...)`.

This fix is required before the parser path is considered safe. It should be applied as a small dedicated commit if not already present.

### `testing_receipt_line_diagnosis_routes.py`

The cleanup branch safely enhances the existing testing diagnosis route to use `diagnose_article_line_classification(...)` and expose rule/stage/matched/reason fields. It remains read-only/testing-only and does not determine receipt status.

## What is intentionally not included

- Root-level `r9_*.py` patch scripts from the review branch.
- R9-29A4 middleware in `main.py`.
- R9-27C rembg/PCA preprocessing changes.
- Runtime/debug data such as `backend/data/receipts`, `tools/debug_output`, `response_*.json`.
- Local backups and `.bak` files.

## Required validation before merging cleanup branch

1. Python import/syntax smoke test.
2. Verify `/api/testing/receipt-line-diagnosis` still returns read-only diagnostics.
3. Apply or verify the sparse-line `unit_price` bugfix.
4. Run full 14-receipt baseline regression before any runtime preprocessing changes are reintroduced.
5. Re-run R9-29B with the Swagger status report and verify `expected_line_count` and `failed_criteria` are populated.

## Recommended next branch after this cleanup

Create a separate branch for preprocessing behavior only:

`feature/r9-27c-gated-preprocessing-regression-tested`

That branch must contain only the rembg/PCA preprocessing changes, with explicit regression output for all 14 receipts.
