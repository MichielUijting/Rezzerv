@echo off
CLS
setlocal
set "INHUIS_DIAG_SELF=%~f0"
powershell.exe -NoProfile -Command "$raw=[IO.File]::ReadAllText($env:INHUIS_DIAG_SELF,[Text.Encoding]::GetEncoding(1252)); $mark=[char]35+'POWERSHELL_DIAGNOSTIC_BEGIN'; $separator=[Environment]::NewLine+$mark+[Environment]::NewLine; $idx=$raw.LastIndexOf($separator,[StringComparison]::Ordinal); if($idx -lt 0){ Write-Host 'FOUT: Diagnosedeel ontbreekt'; exit 2 }; $code=$raw.Substring($idx+$separator.Length); & ([ScriptBlock]::Create($code))"
set "RC=%ERRORLEVEL%"
CLS
if "%RC%"=="0" (
  echo INHUIS WINKELPRODUCT-BRONPROEF VOLTOOID.
  echo Het rapport staat in Downloads: Inhuis_Winkelproduct_Bronproef_Resultaat.txt
) else (
  echo INHUIS WINKELPRODUCT-BRONPROEF VEILIG GESTOPT.
  echo Het rapport heet Inhuis_Winkelproduct_Bronproef_Resultaat.txt.
  echo Als dat ontbreekt, stuur dan de foutmelding BOVEN dit scherm door.
)
echo.
echo Niets verwijderd, gestart, gestopt of gemigreerd.
pause
exit /b %RC%
#POWERSHELL_DIAGNOSTIC_BEGIN
$ErrorActionPreference = 'Stop'
$report = Join-Path (Join-Path $env:USERPROFILE 'Downloads') 'Inhuis_Winkelproduct_Bronproef_Resultaat.txt'
if (-not (Test-Path -LiteralPath (Split-Path -Parent $report))) { $report = Join-Path $env:TEMP 'Inhuis_Winkelproduct_Bronproef_Resultaat.txt' }
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('INHUIS WINKELPRODUCT-BRONPROEF - ALLEEN LEZEN')
$lines.Add(('Datum: {0:yyyy-MM-dd HH:mm:ss zzz}' -f [DateTimeOffset]::Now))
$lines.Add('Wijzigingen aan database, Docker en Git: GEEN')
# Rapporteer ook wanneer de controles vroegtijdig fail-closed stoppen.
$lines | Set-Content -LiteralPath $report -Encoding UTF8
function Note([string] $message) { $lines.Add($message) }
function SaveReport { $lines | Set-Content -LiteralPath $report -Encoding UTF8 }
try {
  $repo = Join-Path $env:USERPROFILE 'Rezzerv_CODEX_WORK'
  $scriptRoot = Split-Path -Parent $env:INHUIS_DIAG_SELF
  $candidate = Split-Path -Parent (Split-Path -Parent $scriptRoot)
  if (Test-Path -LiteralPath (Join-Path $candidate '.git')) { $repo = $candidate }
  if (Test-Path -LiteralPath (Join-Path (Get-Location).Path '.git')) { $repo = (Get-Location).Path }
  if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) { throw 'Officiele Git-werkmap ontbreekt.' }
  if (-not (Test-Path -LiteralPath (Join-Path $repo 'docker-compose.yml'))) { throw 'Officiele Compose-configuratie ontbreekt.' }
  if (-not (Test-Path -LiteralPath (Join-Path $repo 'docker-compose.postgresql.yml'))) { throw 'PostgreSQL Compose-configuratie ontbreekt.' }
  if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) { throw 'Docker CLI niet gevonden.' }
  if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) { throw 'Git CLI niet gevonden.' }
  $branch = (& git.exe -C $repo branch --show-current 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE -ne 0) { throw 'Git-branch niet uitleesbaar.' }
  $head = (& git.exe -C $repo rev-parse HEAD 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE -ne 0) { throw 'Git-status kon niet worden gelezen.' }
  Note ('Lokale Git-branch: ' + $branch)
  Note ('Lokale Git-SHA: ' + $head)
  $envPath = Join-Path $repo '.env'
  if (-not (Test-Path -LiteralPath $envPath)) { throw 'Officiele .env ontbreekt; runtime niet geraden.' }
  Push-Location $repo
  try {
    $composeArgs = @('compose','--env-file','.env','-f','docker-compose.yml','-f','docker-compose.postgresql.yml','--profile','postgresql')
    $backendIds = @(& docker.exe @composeArgs ps -q backend 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'Bestaande backend via officiele Compose-route niet uitleesbaar.' }
    $backendIds = @($backendIds | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ -match '^[a-f0-9]{12,64}$' })
    if ($backendIds.Count -ne 1) { throw ('Niet precies een bestaande backend gevonden via deze Compose-route (aantal: ' + $backendIds.Count + '). Geen database gekozen.') }
    $backendId = $backendIds[0]
    Note ('Compose-backend-ID: ' + $backendId.Substring(0,12))
    # Inspect Docker JSON rather than passing Go-template quotes through Windows PowerShell.
    $backendInspectRaw = & docker.exe inspect $backendId 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Docker-backend inspectie mislukt.' }
    $backendInspect = @($backendInspectRaw | Out-String | ConvertFrom-Json)
    if ($backendInspect.Count -ne 1) { throw 'Docker-backend inspectie niet eenduidig.' }
    $backendState = [string]$backendInspect[0].State.Status
    $backendProject = [string]$backendInspect[0].Config.Labels.'com.docker.compose.project'
    Note ('Backend status en Compose-project: ' + $backendState + ' / ' + $backendProject)
    if ($backendState -ne 'running') { throw 'De bestaande backend draait niet; diagnose start niets.' }
    if ([string]$backendInspect[0].Config.Labels.'com.docker.compose.service' -ne 'backend') { throw 'Onverwachte backendservice.' }
    if ([string]::IsNullOrWhiteSpace($backendProject)) { throw 'Backend mist Compose-projectidentiteit; gestopt.' }
    $postgresIds = @(& docker.exe @composeArgs ps -q postgres 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL status via Compose-route niet uitleesbaar.' }
    $postgresIds = @($postgresIds | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ -match '^[a-f0-9]{12,64}$' })
    Note ('PostgreSQL containers via dezelfde Compose-route: ' + $postgresIds.Count)
    if ($postgresIds.Count -ne 1) { throw 'Database-identiteit is niet eenduidig binnen deze Compose-route; gestopt.' }
    $postgresInspectRaw = & docker.exe inspect $postgresIds[0] 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Docker-PostgreSQL-inspectie mislukt.' }
    $postgresInspect = @($postgresInspectRaw | Out-String | ConvertFrom-Json)
    if ($postgresInspect.Count -ne 1) { throw 'Docker-PostgreSQL-inspectie niet eenduidig.' }
    $postgresProject = [string]$postgresInspect[0].Config.Labels.'com.docker.compose.project'
    if ([string]$postgresInspect[0].Config.Labels.'com.docker.compose.service' -ne 'postgres') { throw 'Onverwachte databaseservice.' }
    if ($postgresProject -ne $backendProject) { throw 'Backend en database hebben verschillende Compose-projecten; niets uitgelezen.' }
    # Python runs in the ALREADY RUNNING backend. No application imports, migrations or writes.
    function Invoke-ProbePython([string] $Code) {
      # Redirect through .NET: Windows PowerShell must not turn the first stderr
      # line into a terminating NativeCommandError and discard the traceback.
      $startInfo = [Diagnostics.ProcessStartInfo]::new()
      $startInfo.FileName = (Get-Command docker.exe -ErrorAction Stop).Source
      $arguments = 'exec -i -e PYTHONIOENCODING=utf-8 '
      $startInfo.Arguments = $arguments + $backendId + ' python -B -'
      $startInfo.UseShellExecute = $false
      $startInfo.CreateNoWindow = $true
      $startInfo.RedirectStandardInput = $true
      $startInfo.RedirectStandardOutput = $true
      $startInfo.RedirectStandardError = $true
      $startInfo.StandardOutputEncoding = [Text.Encoding]::UTF8
      $startInfo.StandardErrorEncoding = [Text.Encoding]::UTF8
      $process = [Diagnostics.Process]::new()
      $process.StartInfo = $startInfo
      try {
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.StandardInput.Write($Code)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(180000)) {
          try { $process.Kill() } catch {}
          throw 'Bronproef duurde langer dan drie minuten; veilig gestopt.'
        }
        return [pscustomobject]@{ ExitCode=$process.ExitCode; Stdout=$stdoutTask.GetAwaiter().GetResult(); Stderr=$stderrTask.GetAwaiter().GetResult() }
      } finally { $process.Dispose() }
    }
    $pythonCode = @'
"""Read-only source identity audit; never imported by application startup.

This is the first retailer-product proof, not a catalog importer. It separates
explicit GTIN evidence, ambiguous scanner codes and retailer SKU namespaces.
No account login, network call, name-based product identity or database write.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import secrets


PROVIDERS = ("ah", "jumbo", "lidl", "picnic", "aldi")
EXPLICIT_GTIN_KEYS = ("gtin", "ean", "barcode")
SCANNER_KEYS = ("codeInput", "productCode")
SKU_KEYS = ("retailer_sku", "retailerSku", "sku", "articleNumber", "articleId")
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_RECEIPTS = 2000
MAX_LINES = 2000


def valid_gtin(value):
    """Exact ASCII digits, valid length/check digit; no digit stripping/padding."""
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9]{8}|[0-9]{12,14})", value):
        return False
    if set(value) == {"0"}:
        return False
    total = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(value[:-1])))
    return (10 - total % 10) % 10 == int(value[-1])


def code_value(value):
    # JSON numbers have already lost possible leading zeroes: do not reconstruct.
    return value.strip() if isinstance(value, str) and len(value) <= 180 else ""


def line_evidence(provider, item):
    """Return allowlisted identifiers only. Never expose arbitrary source keys."""
    if provider not in PROVIDERS or not isinstance(item, dict):
        raise ValueError("Unsupported source")
    nested = next((item[k] for k in ("product", "article", "item") if isinstance(item.get(k), dict)), {})
    explicit = []
    ambiguous = []
    skus = []
    numeric_fields = 0
    for prefix, obj in (("line", item), ("product", nested)):
        for key in EXPLICIT_GTIN_KEYS + SCANNER_KEYS:
            if key not in obj or obj[key] in (None, ""):
                continue
            value = code_value(obj[key])
            numeric_fields += int(isinstance(obj[key], (int, float)) and not isinstance(obj[key], bool))
            entry = {"field": prefix + "." + key, "value": value,
                     "check_digit_valid": valid_gtin(value)}
            (explicit if key in EXPLICIT_GTIN_KEYS else ambiguous).append(entry)
        for key in SKU_KEYS + (("id",) if prefix == "product" or provider in {"ah", "picnic"} else ()):
            value = code_value(obj.get(key))
            if value:
                skus.append({"field": prefix + "." + key, "value": value})
    gtins = {e["value"] for e in explicit if e["check_digit_valid"]}
    invalid_explicit = any(not e["check_digit_valid"] for e in explicit)
    # Different string lengths can be legitimate GTIN zero-padding aliases.
    # Preserve observations, but never choose between conflicting identities.
    normalized = {v.zfill(14) for v in gtins}
    conflict = len(normalized) > 1
    status = ("conflicting_gtins" if conflict else "invalid_explicit_gtin" if invalid_explicit
              else "explicit_gtin_observed" if gtins else "scanner_code_needs_confirmation" if ambiguous
              else "retailer_sku_only" if skus else "no_identifier")
    return {"provider": provider, "status": status, "explicit_gtins": explicit,
            "scanner_codes": ambiguous, "retailer_skus": skus,
            "numeric_identifier_fields": numeric_fields,
            "retailer_product_verified": False, "barcode_link_verified": False}


def source_lines(envelope):
    """Read only the bounded, known retailer-envelope layout we actually store."""
    if not isinstance(envelope, dict) or envelope.get("schema_version") != "1.0":
        raise ValueError("Unknown envelope version")
    provider = envelope.get("provider")
    if provider not in PROVIDERS:
        raise ValueError("Unknown provider")
    root = envelope.get("receipt")
    if not isinstance(root, dict):
        raise ValueError("Missing receipt")
    for wrapper in ("receipt", "ticket", "data", "order"):
        if isinstance(root.get(wrapper), dict):
            root = root[wrapper]
    lines = next((root[k] for k in ("items", "products", "lines", "articles", "itemsLine")
                  if isinstance(root.get(k), list)), None)
    if lines is None or len(lines) > MAX_LINES or any(not isinstance(x, dict) for x in lines):
        raise ValueError("Unknown or excessive source lines")
    return provider, lines


def read_envelope(path, root, expected_hash):
    """Constrain path, size and content hash before opening private source data."""
    source = Path(path).resolve()
    source.relative_to(Path(root).resolve())
    if not source.is_file() or source.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Source missing or excessive")
    with source.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES or hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError("Source hash differs")
    return json.loads(data)


def audit(conn, storage_root):
    """Requires an already read-only PostgreSQL snapshot. All output is aggregate.

    No names, IDs, codes, prices, source paths, account details or raw JSON leave
    the source reader. Household references are salted for this execution only.
    """
    from sqlalchemy import text
    if conn.dialect.name != "postgresql" or conn.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
        raise ValueError("Read-only PostgreSQL transaction required")
    rows = conn.execute(text("""
        SELECT rr.id, rr.household_id, rr.storage_path, rr.sha256_hash,
               rs.source_path AS provider
        FROM raw_receipts rr
        JOIN receipt_sources rs ON rs.id=rr.source_id AND rs.household_id=rr.household_id
        WHERE rs.type='retailer_api'
          AND rs.source_path IN ('ah','jumbo','lidl','picnic','aldi')
          AND rr.mime_type='application/vnd.inhuis.retailer-receipt+json'
        ORDER BY rr.household_id, rs.source_path, rr.id
        LIMIT :limit
    """), {"limit": MAX_RECEIPTS + 1}).mappings().all()
    if len(rows) > MAX_RECEIPTS:
        raise ValueError("More than 2000 source receipts; narrow audit required")
    salt = secrets.token_bytes(32)
    groups = {}
    for row in rows:
        household = hashlib.sha256(salt + str(row["household_id"]).encode()).hexdigest()[:12]
        key = household, row["provider"]
        group = groups.setdefault(key, {"household_ref": household, "provider": row["provider"],
            "source_receipts": 0, "source_errors": 0, "source_lines": 0,
            "explicit_nonproduct_lines_skipped": 0, "statuses": Counter(), "numeric_identifier_fields": 0,
            "persisted_product_lines": 0, "persisted_valid_gtin_shape": 0,
            "persisted_sku_present": 0, "barcode_also_sku": 0})
        group["source_receipts"] += 1
        try:
            provider, lines = source_lines(read_envelope(row["storage_path"], storage_root, row["sha256_hash"]))
            if provider != row["provider"]:
                raise ValueError("Provider mismatch")
        except (ValueError, OSError, TypeError, UnicodeError):
            group["source_errors"] += 1
            continue
        for item in lines:
            role = next((item[k] for k in ("line_type", "lineType", "type") if item.get(k)), "product")
            if role not in {"product", "article", "item"}:
                group["explicit_nonproduct_lines_skipped"] += 1
                continue
            observation = line_evidence(provider, item)
            group["source_lines"] += 1
            group["statuses"][observation["status"]] += 1
            group["numeric_identifier_fields"] += observation["numeric_identifier_fields"]
        # Aggregate separately: raw rows may be folded during import (weights),
        # so there is deliberately NO positional/name-based raw-to-saved join.
        saved = conn.execute(text("""
            SELECT rtl.barcode, rtl.external_article_code
            FROM receipt_table_lines rtl JOIN receipt_tables rt ON rt.id=rtl.receipt_table_id
            WHERE rt.raw_receipt_id=:raw_id AND rt.household_id=:household
              AND rtl.line_role='product' AND rtl.inventory_eligible=1
              AND COALESCE(rtl.is_deleted,FALSE)=FALSE
        """), {"raw_id": row["id"], "household": row["household_id"]}).mappings().all()
        for item in saved:
            barcode = code_value(item["barcode"])
            sku = code_value(item["external_article_code"])
            group["persisted_product_lines"] += 1
            group["persisted_valid_gtin_shape"] += int(valid_gtin(barcode))
            group["persisted_sku_present"] += int(bool(sku))
            group["barcode_also_sku"] += int(bool(sku) and sku == barcode)
    return {"schema_version": "1.0", "read_only": True, "network_requests": 0,
        "retailer_product_verified": False, "barcode_link_verified": False,
        "scope": "Stored retailer API source envelopes, including historical receipts; no new fetch/import",
        "groups": list(groups.values()),
        "providers_without_sources": [p for p in PROVIDERS if not any(g["provider"] == p for g in groups.values())],
        "interpretation": "A valid check digit proves code structure only, never product identity. Source and saved counts have different denominators. No automatic links."}


def main():
    # No app.db/main imports: never trigger schema preflight, startup or writes.
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    url = make_url(os.environ.get("DATABASE_URL") or "")
    if url.get_backend_name() != "postgresql" or url.host != "postgres" or (url.port or 5432) != 5432:
        raise ValueError("Expected existing Compose PostgreSQL route")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    engine = create_engine(url, connect_args={"connect_timeout": 8}, isolation_level="REPEATABLE READ")
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            conn.exec_driver_sql("SET LOCAL statement_timeout='25s'")
            conn.exec_driver_sql("SET LOCAL lock_timeout='3s'")
            result = audit(conn, Path(os.environ.get("RECEIPT_STORAGE_ROOT", "/app/data/receipts/raw")))
        print(json.dumps(result, ensure_ascii=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Driver/file/JSON exceptions can contain credentials or raw source data.
        print('VEILIG GESTOPT: broncontrole niet voltooid; geen gegevens gewijzigd.')
        raise SystemExit(1) from None
'@
    Write-Host 'Bestaande bronbonnen en productcodes alleen-lezen controleren...'
    $output = Invoke-ProbePython -Code $pythonCode
    if ($output.ExitCode -ne 0) { throw 'Broncontrole niet voltooid. Geen gegevens gewijzigd; technische bronuitvoer wordt niet gedeeld.' }
    $result = $output.Stdout.Trim() | ConvertFrom-Json
    if ($result.schema_version -ne '1.0' -or $result.read_only -ne $true -or $result.network_requests -ne 0) { throw 'Onverwacht diagnoseantwoord.' }
    Note 'BRONPROEF VOLTOOID - geen databasewijzigingen of externe verzoeken.'
    Note 'Dit bewijst beschikbare broncodes; nog geen koppeling naar een websiteproduct.'
    foreach ($group in $result.groups) {
      Note (('Winkel: {0}; huishoudenreferentie: {1}' -f $group.provider, $group.household_ref))
      Note (('Bronbonnen: {0}; niet uitleesbaar: {1}; bronregels onderzocht: {2}; expliciete niet-productregels overgeslagen: {3}' -f $group.source_receipts, $group.source_errors, $group.source_lines, $group.explicit_nonproduct_lines_skipped))
      Note ('Broncodebevindingen: ' + ($group.statuses | ConvertTo-Json -Compress))
      Note (('Opgeslagen productregels: {0}; barcode met geldig controlecijfer: {1}; winkelcode aanwezig: {2}; barcode gelijk aan winkelcode: {3}' -f $group.persisted_product_lines, $group.persisted_valid_gtin_shape, $group.persisted_sku_present, $group.barcode_also_sku))
      if ([int]$group.source_errors -gt 0) { Note 'LET OP: niet alle bronbonnen onderzocht; geen volledige dekking bewezen.' }
    }
    Note ('Geen digitale bronbonnen voor: ' + ($result.providers_without_sources -join ', '))
    Note 'explicit_gtin_observed = expliciet barcodeveld met geldig controlecijfer; productidentiteit nog niet bevestigd.'
    Note 'scanner_code_needs_confirmation = scancode die nog onafhankelijk bevestigd moet worden.'
    Note 'retailer_sku_only = alleen winkelartikelnummer; dit is geen bewezen barcode.'
    Note 'conflicting_gtins / invalid_explicit_gtin = tegenstrijdige of ongeldige barcodegegevens.'
    Note 'no_identifier = geen bruikbare broncode beschikbaar.'
    Note 'Aantallen bronregels en opgeslagen productregels zijn afzonderlijke metingen; geen naam- of positiegebaseerde koppeling.'
    Note 'Historische opgeslagen digitale bonnen inbegrepen. Geen nieuwe bonnen opgehaald. Foto-, PDF- en e-mailbonnen vallen buiten deze proef.'
    Note 'VOLGENDE STAP: upload dit TXT-rapport in de chat. Geen bronbonnen, accounts of tokens meesturen.'
  } finally { Pop-Location }
} catch {
  Note ('VEILIG GESTOPT: ' + $_.Exception.Message)
  try { SaveReport } catch { Write-Host 'Rapport kon niet worden opgeslagen.' }
  Write-Host ('Rapport: ' + $report)
  exit 1
}
SaveReport
exit 0
