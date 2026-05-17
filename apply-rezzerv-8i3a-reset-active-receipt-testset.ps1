$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8I-3A veilige testset-reset endpoint toevoegen...' -ForegroundColor Cyan

$path = Join-Path $root 'backend/app/main.py'
if (-not (Test-Path $path)) { throw "Bestand niet gevonden: $path" }

$content = Get-Content $path -Raw -Encoding UTF8
$original = $content

if ($content -notmatch 'reset-active-receipt-testset') {
$endpoint = @'


@app.post("/api/testing/reset-active-receipt-testset")
def reset_active_receipt_testset():
    """Soft-reset alleen de bekende 14 kassabon-testbestanden.

    Geen hard delete: records worden alleen uit de actieve set gehaald als de tabel
    daarvoor een is_deleted/deleted_at/archived_at kolom heeft. Baseline/SSOT blijven ongemoeid.
    """
    test_filenames = [
        "plus foto 1.jpg",
        "Plus foto 2.jpeg",
        "Lidl App 1.png",
        "Lidl App 2.png",
        "Lidl App 4.pdf",
        "Jumbo foto 1.jpeg",
        "Jumbo foto 3.jpg",
        "Jumbo App 1.png",
        "Aldi foto 1.jpg",
        "Aldi foto 2.jpg",
        "AH foto 1.pdf",
        "AH foto 2.jpeg",
        "AH foto 3.jpg",
        "AH App 1.pdf",
    ]
    lower_names = [name.lower() for name in test_filenames]

    with engine.begin() as conn:
        table_columns = [
            str(row["name"])
            for row in conn.execute(text("PRAGMA table_info(receipt_tables)")).mappings().all()
        ]
        line_columns = [
            str(row["name"])
            for row in conn.execute(text("PRAGMA table_info(receipt_table_lines)")).mappings().all()
        ]

        receipt_rows = conn.execute(
            text("""
                SELECT id, filename
                FROM receipt_tables
                WHERE lower(filename) IN :filenames
            """).bindparams(bindparam("filenames", expanding=True)),
            {"filenames": lower_names},
        ).mappings().all()
        receipt_ids = [str(row["id"]) for row in receipt_rows]

        if not receipt_ids:
            return {
                "success": True,
                "mode": "soft_reset",
                "matched_receipts": 0,
                "updated_receipt_tables": 0,
                "updated_receipt_table_lines": 0,
                "message": "Geen actieve testbonnen gevonden om te resetten.",
                "receipt_table_columns": table_columns,
                "receipt_table_line_columns": line_columns,
            }

        table_sets = []
        if "is_deleted" in table_columns:
            table_sets.append("is_deleted = 1")
        if "deleted_at" in table_columns:
            table_sets.append("deleted_at = CURRENT_TIMESTAMP")
        if "archived_at" in table_columns:
            table_sets.append("archived_at = CURRENT_TIMESTAMP")
        if "updated_at" in table_columns:
            table_sets.append("updated_at = CURRENT_TIMESTAMP")

        line_sets = []
        if "is_deleted" in line_columns:
            line_sets.append("is_deleted = 1")
        if "deleted_at" in line_columns:
            line_sets.append("deleted_at = CURRENT_TIMESTAMP")
        if "archived_at" in line_columns:
            line_sets.append("archived_at = CURRENT_TIMESTAMP")
        if "updated_at" in line_columns:
            line_sets.append("updated_at = CURRENT_TIMESTAMP")

        if not table_sets and not line_sets:
            return {
                "success": False,
                "mode": "soft_reset",
                "matched_receipts": len(receipt_ids),
                "message": "Geen soft-reset kolommen gevonden; geen wijziging uitgevoerd.",
                "receipt_table_columns": table_columns,
                "receipt_table_line_columns": line_columns,
                "filenames": [row["filename"] for row in receipt_rows],
            }

        updated_tables = 0
        updated_lines = 0
        if table_sets:
            updated_tables = conn.execute(
                text("UPDATE receipt_tables SET " + ", ".join(table_sets) + " WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": receipt_ids},
            ).rowcount or 0
        if line_sets:
            updated_lines = conn.execute(
                text("UPDATE receipt_table_lines SET " + ", ".join(line_sets) + " WHERE receipt_table_id IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": receipt_ids},
            ).rowcount or 0

    return {
        "success": True,
        "mode": "soft_reset",
        "matched_receipts": len(receipt_ids),
        "updated_receipt_tables": updated_tables,
        "updated_receipt_table_lines": updated_lines,
        "filenames": [row["filename"] for row in receipt_rows],
        "scope": "Alleen bekende 14 kassabon-testbestanden; baseline/SSOT ongemoeid.",
    }
'@
$content += $endpoint
}

if ($content -ne $original) {
    Copy-Item $path "$path.8i3a-reset-testset-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host 'Veilig testset-reset endpoint toegevoegd.' -ForegroundColor Green
} else {
    Write-Host 'Geen wijziging toegepast; endpoint lijkt al aanwezig.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host 'Daarna POST /api/testing/reset-active-receipt-testset uitvoeren.' -ForegroundColor Yellow
