$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8I-3A schema-inspectie endpoint toevoegen...' -ForegroundColor Cyan

$path = Join-Path $root 'backend/app/main.py'
if (-not (Test-Path $path)) { throw "Bestand niet gevonden: $path" }

$content = Get-Content $path -Raw -Encoding UTF8
$original = $content

if ($content -notmatch 'receipt-table-schema') {
$endpoint = @'


@app.get("/api/testing/receipt-table-schema")
def receipt_table_schema():
    """Read-only inspectie van kassabon-tabellen voor veilige testset-reset."""
    table_names = [
        "receipt_tables",
        "receipt_table_lines",
        "receipts",
        "receipt_sources",
    ]
    result = {"success": True, "tables": {}}

    with engine.connect() as conn:
        existing_tables = [
            str(row["name"])
            for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")).mappings().all()
        ]
        result["existing_tables"] = existing_tables

        for table_name in table_names:
            if table_name not in existing_tables:
                result["tables"][table_name] = {
                    "exists": False,
                    "columns": [],
                    "sample_rows": [],
                }
                continue

            columns = [dict(row) for row in conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()]
            column_names = [str(row.get("name")) for row in columns]
            sample_rows = []
            try:
                sample_rows = [
                    dict(row)
                    for row in conn.execute(text(f"SELECT * FROM {table_name} LIMIT 5")).mappings().all()
                ]
            except Exception as exc:
                sample_rows = [{"sample_error": str(exc)}]

            result["tables"][table_name] = {
                "exists": True,
                "columns": columns,
                "column_names": column_names,
                "sample_rows": sample_rows,
            }

    return result
'@
$content += $endpoint
}

if ($content -ne $original) {
    Copy-Item $path "$path.8i3a-schema-inspection-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host 'Schema-inspectie endpoint toegevoegd.' -ForegroundColor Green
} else {
    Write-Host 'Geen wijziging toegepast; endpoint lijkt al aanwezig.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host 'Daarna GET /api/testing/receipt-table-schema uitvoeren.' -ForegroundColor Yellow
