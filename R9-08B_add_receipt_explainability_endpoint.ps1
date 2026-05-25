$ErrorActionPreference = 'Stop'

$path = 'backend\app\main.py'
if (!(Test-Path $path)) {
  throw "main.py niet gevonden: $path"
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupPath = "$path.R9-08B_backup_$timestamp"
Copy-Item $path $backupPath -Force
Write-Host "Backup gemaakt: $backupPath"

$content = Get-Content $path -Raw -Encoding UTF8

if ($content.Contains('@app.get("/api/receipts/{receipt_table_id}/explainability")')) {
  Write-Host 'R9-08B endpoint bestaat al; geen wijziging nodig.'
} else {
  $endpoint = @'


@app.get("/api/receipts/{receipt_table_id}/explainability")
def get_receipt_explainability(receipt_table_id: str, authorization: Optional[str] = Header(None)):
    """Read-only parser explainability for one receipt.

    This endpoint does not reparse, does not mutate receipt data and does not
    decide status. It explains the persisted result currently visible in Kassa.
    """
    from types import SimpleNamespace
    from app.receipt_ingestion.explainability import build_receipt_explainability
    from app.services.receipt_ssot_status import apply_po_norm_status

    with engine.begin() as conn:
        require_entity_household_access(conn, "receipt_tables", receipt_table_id, authorization, admin_only=False)
        header = conn.execute(
            text(
                """
                SELECT
                    rt.id AS receipt_table_id,
                    rt.raw_receipt_id,
                    rt.household_id,
                    rt.store_name,
                    rt.store_branch,
                    rt.purchase_at,
                    rt.total_amount,
                    rt.discount_total,
                    rt.currency,
                    rt.parse_status,
                    rt.confidence_score,
                    rt.line_count,
                    rt.created_at,
                    rt.updated_at,
                    COALESCE(rs.label, 'Manual upload') AS source_label,
                    rs.type AS source_type,
                    rr.original_filename,
                    rr.mime_type,
                    rr.imported_at
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                LEFT JOIN receipt_sources rs ON rs.id = rr.source_id
                WHERE rt.id = :receipt_table_id
                  AND rt.deleted_at IS NULL
                  AND rr.deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"receipt_table_id": receipt_table_id},
        ).mappings().first()
        if not header:
            raise HTTPException(status_code=404, detail="Receipt table niet gevonden")

        line_rows = conn.execute(
            text(
                """
                SELECT
                    id,
                    line_index,
                    raw_label,
                    corrected_raw_label,
                    COALESCE(corrected_raw_label, raw_label) AS display_label,
                    quantity,
                    corrected_quantity,
                    COALESCE(corrected_quantity, quantity) AS display_quantity,
                    unit,
                    corrected_unit,
                    COALESCE(corrected_unit, unit) AS display_unit,
                    unit_price,
                    corrected_unit_price,
                    COALESCE(corrected_unit_price, unit_price) AS display_unit_price,
                    line_total,
                    corrected_line_total,
                    COALESCE(corrected_line_total, line_total) AS display_line_total,
                    discount_amount,
                    article_match_status,
                    confidence_score,
                    COALESCE(is_deleted, 0) AS is_deleted,
                    COALESCE(is_validated, 0) AS is_validated
                FROM receipt_table_lines
                WHERE receipt_table_id = :receipt_table_id
                ORDER BY line_index ASC, created_at ASC
                """
            ),
            {"receipt_table_id": receipt_table_id},
        ).mappings().all()

    header_dict = dict(header)
    active_lines = []
    ignored_lines = []
    for row in line_rows:
        line = serialize_receipt_row(dict(row))
        if int(line.get("is_deleted") or 0):
            ignored_lines.append(line)
            continue
        active_lines.append({
            **line,
            "line_total": line.get("display_line_total"),
            "quantity": line.get("display_quantity"),
            "unit": line.get("display_unit"),
            "unit_price": line.get("display_unit_price"),
            "raw_label": line.get("display_label"),
        })

    parser_summary = {
        "total_candidates": len(line_rows),
        "appended_candidates": len(active_lines),
        "blocked_candidates": len(ignored_lines),
        "by_classification": {},
        "by_blocked_reason": {"deleted_or_ignored_line": len(ignored_lines)} if ignored_lines else {},
    }

    result = SimpleNamespace(
        is_receipt=True,
        parse_status=header_dict.get("parse_status"),
        confidence_score=header_dict.get("confidence_score"),
        store_name=header_dict.get("store_name"),
        purchase_at=header_dict.get("purchase_at"),
        total_amount=header_dict.get("total_amount"),
        discount_total=header_dict.get("discount_total"),
        currency=header_dict.get("currency") or "EUR",
        lines=active_lines,
        store_branch=header_dict.get("store_branch"),
        parser_diagnostics=parser_summary,
    )

    source_context = {
        "route": str(header_dict.get("source_type") or "manual_upload"),
        "source_label": header_dict.get("source_label"),
        "original_filename": header_dict.get("original_filename"),
        "mime_type": header_dict.get("mime_type"),
        "imported_at": normalize_datetime(header_dict.get("imported_at")),
    }

    explainability = build_receipt_explainability(result, source_context=source_context)
    status_payload = apply_po_norm_status(serialize_receipt_row(dict(header_dict)))

    return {
        "receipt_table_id": receipt_table_id,
        "read_only": True,
        "po_norm_status_label": status_payload.get("po_norm_status_label"),
        "explainability": explainability,
        "line_count": len(active_lines),
        "ignored_line_count": len(ignored_lines),
    }
'@

  $patchAnchor = '@app.patch("/api/receipts/{receipt_table_id}")'
  $anchorIndex = $content.IndexOf($patchAnchor)
  if ($anchorIndex -lt 0) {
    throw 'Anchor @app.patch("/api/receipts/{receipt_table_id}") niet gevonden.'
  }

  $content = $content.Insert($anchorIndex, $endpoint + "`r`n`r`n")
  [System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))
  Write-Host 'R9-08B endpoint toegevoegd.'
}

$checkPath = 'tools\R9-08_receipt_explainability_endpoint_check.py'
$check = @'
from __future__ import annotations

import json
import sys
from urllib.request import Request, urlopen


def fail(message: str) -> None:
    print(f"R9-08 FAIL: {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"R9-08 OK: {message}")


def fetch_json(url: str, token: str) -> dict:
    request = Request(url)
    request.add_header("Authorization", f"Bearer {token}")
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8011"
    token = sys.argv[2] if len(sys.argv) > 2 else "rezzerv-dev-token::admin@rezzerv.local"
    receipts = fetch_json(f"{base_url}/api/receipts?householdId=1", token)
    items = receipts.get("items") or []
    if not items:
        fail("Geen bonnen beschikbaar voor endpointcheck")
    receipt_id = items[0].get("receipt_table_id")
    if not receipt_id:
        fail("Eerste bon mist receipt_table_id")

    payload = fetch_json(f"{base_url}/api/receipts/{receipt_id}/explainability", token)
    explainability = payload.get("explainability") or {}
    required = [
        "source_route",
        "ocr_route",
        "preprocessing",
        "header_decisions",
        "total_decision",
        "article_decisions",
        "status_explanation",
    ]
    for marker in required:
        if marker not in explainability:
            fail(f"Explainability mist marker: {marker}")
    if payload.get("read_only") is not True or explainability.get("read_only") is not True:
        fail("Explainability endpoint is niet expliciet read_only")
    ok(f"endpoint bereikbaar voor receipt_table_id={receipt_id}")
    ok("generic runtime explainability payload bevat verplichte secties")
    ok("R9-08 receipt explainability endpoint is geborgd")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@
[System.IO.File]::WriteAllText($checkPath, $check, [System.Text.UTF8Encoding]::new($false))
Write-Host "Aangemaakt/bijgewerkt: $checkPath"

python -m py_compile backend\app\main.py $checkPath
Write-Host 'R9-08B py_compile OK.'

Write-Host ''
Write-Host 'Volgende commando''s:'
Write-Host 'docker compose up -d --build backend'
Write-Host 'python .\tools\R9-08_receipt_explainability_endpoint_check.py http://localhost:8011 rezzerv-dev-token::admin@rezzerv.local'
Write-Host 'git add backend\app\main.py tools\R9-08_receipt_explainability_endpoint_check.py'
Write-Host 'git commit -m "R9-08 Expose receipt parser explainability endpoint"'
Write-Host 'git push'
