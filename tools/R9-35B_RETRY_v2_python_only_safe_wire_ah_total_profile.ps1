$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$patchPath = Join-Path $repoRoot 'tools\R9-35B_RETRY_v2_patch.py'

$pythonPatch = @'
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()
SERVICE = ROOT / "backend/app/services/receipt_service.py"
TOTALS = ROOT / "backend/app/receipt_ingestion/profiles/ah/totals.py"
HEADER = ROOT / "backend/app/receipt_ingestion/header_parser.py"
BACKUP = ROOT / "backend/app/services/receipt_service.py.R9-35B-RETRY-v2.bak"

IMPORT_LINE = "from app.receipt_ingestion.profiles.ah.totals import extract_ah_total_amount, looks_like_ah_context"
AH_RUNTIME_IMPORT = "from app.receipt_ingestion.profiles.ah_runtime import build_ah_profile_article_lines, extract_positive_contributors"
OLD_LINE = "    total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)"
NEW_BLOCK = """    if looks_like_ah_context(text_lines, filename, store_name=store_name):
        ah_total_result = extract_ah_total_amount(text_lines, filename, store_name=store_name)
        total_amount = ah_total_result.amount
        explicit_total_found = ah_total_result.explicit_total_found
    else:
        total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)"""
FORBIDDEN_FALLBACKS = [
    "candidate_total = line_sum +",
    "total_amount = candidate_total.quantize",
    "total_amount = line_sum.quantize",
]


def show_context(text: str, needle: str, before: int = 4, after: int = 6) -> None:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if needle in line:
            start = max(0, idx - before)
            end = min(len(lines) - 1, idx + after)
            for line_no in range(start, end + 1):
                marker = ">>" if line_no == idx else "  "
                print(f"{marker} {line_no + 1:5d}: {lines[line_no]}")
            return
    raise SystemExit(f"Context needle not found: {needle}")


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def restore_backup(reason: str) -> None:
    if BACKUP.exists():
        SERVICE.write_text(BACKUP.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"ROLLBACK applied: {reason}")


def main() -> None:
    service = SERVICE.read_text(encoding="utf-8-sig")
    BACKUP.write_text(service, encoding="utf-8")

    print("R9-35B-RETRY-v2 pre-check: current total assignment context")
    show_context(service, OLD_LINE)

    import_count = service.count(IMPORT_LINE)
    if import_count == 0:
        if AH_RUNTIME_IMPORT not in service:
            raise SystemExit("Safe import insertion point not found")
        service = service.replace(AH_RUNTIME_IMPORT, AH_RUNTIME_IMPORT + "\n" + IMPORT_LINE, 1)
    elif import_count > 1:
        raise SystemExit(f"AH totals import occurs {import_count} times")

    old_count = service.count(OLD_LINE)
    if old_count != 1:
        raise SystemExit(f"Expected exactly one generic total assignment, found {old_count}")

    service = service.replace(OLD_LINE, NEW_BLOCK, 1)
    SERVICE.write_text(service, encoding="utf-8")

    service_after = SERVICE.read_text(encoding="utf-8")
    print("R9-35B-RETRY-v2 post-change: AH dispatch context")
    show_context(service_after, "if looks_like_ah_context(text_lines, filename, store_name=store_name):")

    try:
        run([sys.executable, "-m", "py_compile", str(SERVICE)])
        run([sys.executable, "-m", "py_compile", str(TOTALS)])
        run([sys.executable, "-m", "py_compile", str(HEADER)])
    except BaseException as exc:
        restore_backup(f"py_compile failed: {exc}")
        raise

    verified = SERVICE.read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_FALLBACKS:
        if forbidden in verified:
            restore_backup(f"forbidden fallback returned: {forbidden}")
            raise SystemExit(f"Forbidden fallback returned: {forbidden}")
    if verified.count(IMPORT_LINE) != 1:
        restore_backup("AH totals import count is not exactly 1")
        raise SystemExit("AH totals import count is not exactly 1")
    if "extract_ah_total_amount(text_lines, filename, store_name=store_name)" not in verified:
        restore_backup("AH dispatch missing")
        raise SystemExit("AH dispatch missing")

    print("R9-35B-RETRY-v2 static checks passed.")


if __name__ == "__main__":
    main()
'@

[System.IO.File]::WriteAllText($patchPath, $pythonPatch, [System.Text.UTF8Encoding]::new($false))
python $patchPath

Write-Host 'Rebuilding containers...'
docker compose up --build -d
Start-Sleep -Seconds 5
$logs = docker compose logs backend --tail=100
Write-Host $logs
if ($logs -notmatch 'Application startup complete') {
  Write-Error 'Backend startup check failed. Inspect docker compose logs backend --tail=200. No commit made.'
  exit 1
}

try {
  $response = Invoke-WebRequest http://localhost:8011/docs -UseBasicParsing
  if ($response.StatusCode -ne 200) {
    Write-Error "/docs returned unexpected status $($response.StatusCode). No commit made."
    exit 1
  }
  Write-Host '/docs status: 200 OK'
} catch {
  Write-Error "/docs check failed: $($_.Exception.Message). No commit made."
  exit 1
}

git --no-pager diff -- backend/app/services/receipt_service.py

git add backend/app/services/receipt_service.py tools/R9-35B_RETRY_v2_python_only_safe_wire_ah_total_profile.ps1 tools/R9-35B_RETRY_v2_patch.py
git commit -m 'R9-35B wire AH total profile safely v2'
git push

Write-Host 'R9-35B-RETRY-v2 toegepast, getest en gepusht.'
