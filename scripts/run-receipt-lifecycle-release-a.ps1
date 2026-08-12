CLS
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Stop-ReleaseA([string]$Message) {
    Write-Host "" 
    Write-Host "==================================================" -ForegroundColor Red
    Write-Host " RELEASE A - CONTROLE ROOD" -ForegroundColor Red
    Write-Host " $Message" -ForegroundColor Red
    Write-Host "==================================================" -ForegroundColor Red
    exit 1
}

try {
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host " REZZERV RELEASE A - LOKALE RUNTIME/DB CONTROLE" -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan

    $Branch = (git branch --show-current).Trim()
    if ($Branch -ne "feature/receipt-lifecycle-release-a") {
        throw "Verkeerde branch: $Branch"
    }

    git fetch origin
    if ($LASTEXITCODE -ne 0) { throw "git fetch origin mislukt" }
    git pull --ff-only origin feature/receipt-lifecycle-release-a
    if ($LASTEXITCODE -ne 0) { throw "git pull mislukt" }

    $Commit = (git rev-parse HEAD).Trim()
    $Dirty = git status --porcelain
    if ($Dirty) { throw "Git-werkmap is niet schoon: $Dirty" }

    Write-Host "[PASS] Branch: $Branch" -ForegroundColor Green
    Write-Host "[PASS] Commit: $Commit" -ForegroundColor Green

    $Db = Join-Path $ProjectRoot "backend\data\rezzerv.db"
    if (-not (Test-Path $Db)) { throw "Lokale database ontbreekt: $Db" }
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $Backup = Join-Path $ProjectRoot "backend\data\rezzerv-before-release-a-$Timestamp.db"
    Copy-Item $Db $Backup
    Write-Host "[PASS] Databasebackup: $Backup" -ForegroundColor Green

    Write-Host "" 
    Write-Host "=== VOLLEDIGE REBUILD ===" -ForegroundColor Cyan
    docker compose down
    if ($LASTEXITCODE -ne 0) { throw "docker compose down mislukt" }
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw "docker compose up -d --build mislukt" }

    Write-Host "" 
    Write-Host "=== BACKEND HEALTH ===" -ForegroundColor Cyan
    $Health = $null
    for ($Attempt = 1; $Attempt -le 18; $Attempt++) {
        try {
            $Health = Invoke-RestMethod -Uri "http://localhost:8011/api/health" -TimeoutSec 5
            if ($Health.status -eq "ok") { break }
        }
        catch {
            $Health = $null
        }
        Start-Sleep -Seconds 5
    }
    if ($null -eq $Health -or $Health.status -ne "ok") {
        docker compose ps
        docker compose logs --tail=100 backend
        throw "Backend health werd niet groen"
    }
    if ($Health.database -ne "/app/data/rezzerv.db") {
        throw "Onverwachte runtime database: $($Health.database)"
    }
    Write-Host "[PASS] Backend health op 8011; database /app/data/rezzerv.db" -ForegroundColor Green

    Write-Host "" 
    Write-Host "=== RELEASE-A DATABASECONTRACT ===" -ForegroundColor Cyan
    $DatabaseCheck = @'
import sqlite3
import sys

DB = "/app/data/rezzerv.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()
errors = []

def columns(table):
    return {str(row[1]) for row in cur.execute(f"PRAGMA table_info({table})")}

def fail(message):
    print(f"[FAIL] {message}")
    errors.append(message)

def passed(message):
    print(f"[PASS] {message}")

required_tables = {
    "raw_receipts", "receipt_tables", "receipt_table_lines",
    "purchase_import_batches", "purchase_import_lines", "inventory_events",
}
tables = {str(row[0]) for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
for table in sorted(required_tables):
    passed(f"bestaande tabel aanwezig: {table}") if table in tables else fail(f"tabel ontbreekt: {table}")

required_columns = {
    "receipt_tables": {"logical_receipt_key", "workflow_state"},
    "receipt_table_lines": {"logical_line_key"},
}
columns_ok = True
for table, expected in required_columns.items():
    actual = columns(table) if table in tables else set()
    for column in sorted(expected):
        if column in actual:
            passed(f"{table}.{column}")
        else:
            columns_ok = False
            fail(f"{table}.{column} ontbreekt")

forbidden = {
    "receipt_identities", "receipt_line_identities", "receipt_line_processing",
    "archived_receipts", "receipt_inventory_events",
}
present_forbidden = sorted(forbidden & tables)
if present_forbidden:
    fail("parallelle receipt-tabellen aanwezig: " + ", ".join(present_forbidden))
else:
    passed("geen parallelle receipt identity/processing/archieftabellen")

inventory_ledgers = sorted(t for t in tables if "inventory_event" in t.lower())
if inventory_ledgers == ["inventory_events"]:
    passed("inventory_events blijft de enige voorraadledger")
else:
    fail("onverwachte inventory-eventtabellen: " + repr(inventory_ledgers))

if columns_ok:
    missing_receipt_keys = cur.execute(
        "SELECT COUNT(*) FROM receipt_tables WHERE COALESCE(TRIM(logical_receipt_key), '') = ''"
    ).fetchone()[0]
    missing_line_keys = cur.execute(
        "SELECT COUNT(*) FROM receipt_table_lines WHERE COALESCE(TRIM(logical_line_key), '') = ''"
    ).fetchone()[0]
    duplicate_receipt_rows = cur.execute(
        "SELECT COUNT(*) FROM receipt_tables WHERE COALESCE(TRIM(logical_receipt_key), '') = ''"
    ).fetchone()[0]

    passed("alle bonnen hebben logical_receipt_key") if missing_receipt_keys == 0 else fail(f"{missing_receipt_keys} bonnen zonder logical_receipt_key")
    passed("alle bonregels hebben logical_line_key") if missing_line_keys == 0 else fail(f"{missing_line_keys} bonregels zonder logical_line_key")

    allowed = {"active", "archived", "returned_to_kassa", "removed_reimport_allowed", "legacy_deleted"}
    states = cur.execute(
        "SELECT COALESCE(workflow_state, '<NULL>') state, COUNT(*) n FROM receipt_tables GROUP BY COALESCE(workflow_state, '<NULL>') ORDER BY state"
    ).fetchall()
    print("Workflowstatussen:")
    for row in states:
        print(f"  {row['state']}: {row['n']}")
    invalid = [str(row["state"]) for row in states if row["state"] not in allowed]
    if invalid:
        fail("ongeldige workflowstatussen: " + ", ".join(invalid))
    else:
        passed("uitsluitend toegestane workflowstatussen")

    receipt_columns = columns("receipt_tables")
    if "deleted_at" in receipt_columns:
        wrong_legacy = cur.execute(
            "SELECT COUNT(*) FROM receipt_tables WHERE deleted_at IS NOT NULL AND workflow_state <> 'legacy_deleted'"
        ).fetchone()[0]
        wrong_active = cur.execute(
            "SELECT COUNT(*) FROM receipt_tables WHERE deleted_at IS NULL AND workflow_state = 'legacy_deleted'"
        ).fetchone()[0]
        passed("historische verwijderingen zijn legacy_deleted") if wrong_legacy == 0 else fail(f"{wrong_legacy} historische deletes verkeerd gemapt")
        passed("actieve bonnen zijn niet legacy_deleted") if wrong_active == 0 else fail(f"{wrong_active} actieve bonnen ten onrechte legacy_deleted")

if errors:
    print("RELEASE_A_DATABASE_CHECK_RED")
    sys.exit(1)
print("RELEASE_A_DATABASE_CHECK_GREEN")
'@
    $DatabaseCheck | docker compose exec -T backend python -
    if ($LASTEXITCODE -ne 0) { throw "Release-A databasecontract is rood" }

    Write-Host "" 
    Write-Host "=== IDEMPOTENTIE OP PRODUCTIERUNTIME ===" -ForegroundColor Cyan
    $IdempotencyCheck = @'
from app.main import engine
from app.services.receipt_lifecycle_foundation_service import ensure_receipt_lifecycle_foundation_schema
with engine.begin() as conn:
    result = ensure_receipt_lifecycle_foundation_schema(conn)
assert result["added_columns"] == [], result
assert result["backfilled_receipts"] == 0, result
assert result["backfilled_lines"] == 0, result
print("RELEASE_A_IDEMPOTENCY_GREEN", result)
'@
    $IdempotencyCheck | docker compose exec -T backend python -
    if ($LASTEXITCODE -ne 0) { throw "Release-A idempotentiecontrole is rood" }

    Write-Host "" 
    Write-Host "=== BESTAANDE KASSABONKETEN ===" -ForegroundColor Cyan
    & "$PSScriptRoot\run-receipt-inventory-chain-v2.ps1" -SkipBackendBuild
    if ($LASTEXITCODE -ne 0) { throw "Kassabon -> Voorraad -> Bijna op is rood" }

    $EndCommit = (git rev-parse HEAD).Trim()
    $DirtyAfter = git status --porcelain
    if ($EndCommit -ne $Commit) { throw "Commit wijzigde tijdens de controle" }
    if ($DirtyAfter) { throw "Controle liet Git-wijzigingen achter: $DirtyAfter" }

    Write-Host "" 
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host " RELEASE A - LOKALE RUNTIME/DB CONTROLE GROEN" -ForegroundColor Green
    Write-Host " Commit : $EndCommit" -ForegroundColor Green
    Write-Host " Backup : $Backup" -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green
    exit 0
}
catch {
    Stop-ReleaseA $_.Exception.Message
}
