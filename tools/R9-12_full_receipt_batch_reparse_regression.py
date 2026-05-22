from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "tools" / "reports"
DEFAULT_BASE_URL = "http://localhost:8011"
DEFAULT_TOKEN = "rezzerv-dev-token::admin@rezzerv.local"
DEFAULT_HOUSEHOLD_ID = "1"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
ZIP_EXTENSION = ".zip"
FINAL_BATCH_STATUSES = {"completed", "completed_with_errors", "failed"}
SUCCESS_BATCH_STATUSES = {"completed", "completed_with_errors"}
DEFAULT_BATCH_TIMEOUT_SECONDS = 900
DEFAULT_BATCH_POLL_SECONDS = 3


def fail(message: str) -> None:
    print(f"R9-12 FAIL: {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"R9-12 OK: {message}")


def http_json(url: str, token: str, *, method: str = "GET", body: bytes | None = None, content_type: str | None = None) -> dict:
    request = Request(url, data=body, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    if content_type:
        request.add_header("Content-Type", content_type)
    with urlopen(request, timeout=90) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def multipart(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----RezzervR912{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode())
    parts.append(f"Content-Type: {mime}\r\n\r\n".encode())
    parts.append(file_path.read_bytes())
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def run_py(args: list[str]) -> None:
    command = [sys.executable, *args]
    print("R9-12 RUN:", " ".join(command))
    completed = subprocess.run(command, cwd=ROOT, text=True)
    if completed.returncode != 0:
        fail(f"subproces faalde: {' '.join(command)}")


def active_receipts(base_url: str, token: str, household_id: str) -> list[dict]:
    payload = http_json(f"{base_url}/api/receipts?householdId={quote(household_id)}", token)
    items = payload.get("items") or []
    if not isinstance(items, list):
        fail("/api/receipts bevat geen items[]")
    return items


def archive_active_receipts(base_url: str, token: str, household_id: str) -> int:
    ids = [str(item.get("receipt_table_id") or "").strip() for item in active_receipts(base_url, token, household_id)]
    ids = [receipt_id for receipt_id in ids if receipt_id]
    if not ids:
        ok("geen actieve bonnen om te archiveren")
        return 0
    body = json.dumps({"receipt_table_ids": ids}).encode("utf-8")
    result = http_json(f"{base_url}/api/receipts/delete", token, method="POST", body=body, content_type="application/json")
    deleted = int(result.get("deleted_count") or 0)
    ok(f"{deleted} actieve bonnen gearchiveerd")
    return deleted


def wait_for_batch_completion(base_url: str, token: str, household_id: str, batch_id: str, *, timeout_seconds: int = DEFAULT_BATCH_TIMEOUT_SECONDS, poll_seconds: int = DEFAULT_BATCH_POLL_SECONDS) -> dict:
    deadline = time.time() + timeout_seconds
    last_snapshot: dict | None = None
    while time.time() < deadline:
        payload = http_json(
            f"{base_url}/api/receipts/import-batches/{quote(batch_id)}?householdId={quote(household_id)}",
            token,
        )
        snapshot = {
            "status": payload.get("status"),
            "processed_files": payload.get("processed_files"),
            "imported_files": payload.get("imported_files"),
            "duplicate_files": payload.get("duplicate_files"),
            "failed_files": payload.get("failed_files"),
            "total_files": payload.get("total_files"),
        }
        if snapshot != last_snapshot:
            print(f"R9-12 batch-status: {snapshot}")
            last_snapshot = snapshot
        status = str(payload.get("status") or "")
        if status in FINAL_BATCH_STATUSES:
            if status not in SUCCESS_BATCH_STATUSES:
                fail(f"batchimport geëindigd met status={status}")
            return payload
        time.sleep(poll_seconds)
    fail(f"timeout wachtend op batchimport completion: {batch_id}")


def import_one(base_url: str, token: str, household_id: str, file_path: Path) -> dict:
    body, content_type = multipart({"household_id": household_id}, "file", file_path)
    result = http_json(f"{base_url}/api/receipts/import", token, method="POST", body=body, content_type=content_type)
    if result.get("batch"):
        batch_id = str(result.get("batch_id") or "")
        ok(f"zipbatch gestart voor {file_path.name}: {batch_id} files={result.get('file_count')}")
        batch_result = wait_for_batch_completion(base_url, token, household_id, batch_id)
        result["final_batch_status"] = batch_result.get("status")
        result["processed_files"] = batch_result.get("processed_files")
        result["imported_files"] = batch_result.get("imported_files")
        result["duplicate_files"] = batch_result.get("duplicate_files")
        result["failed_files"] = batch_result.get("failed_files")
        ok(
            f"zipbatch afgerond status={result.get('final_batch_status')} processed={result.get('processed_files')} imported={result.get('imported_files')} duplicates={result.get('duplicate_files')} failed={result.get('failed_files')}"
        )
    else:
        status = "duplicate" if result.get("duplicate") else "imported"
        ok(f"{file_path.name}: {status} receipt_table_id={result.get('receipt_table_id')}")
    return result


def resolve_input(input_path: Path) -> tuple[str, list[Path]]:
    if not input_path.exists():
        fail(f"input bestaat niet: {input_path}")
    if input_path.is_file():
        if input_path.suffix.lower() == ZIP_EXTENSION:
            return "zip", [input_path]
        if input_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            return "single_file", [input_path]
        fail(f"bestandstype wordt niet ondersteund voor regressie-input: {input_path.name}")
    if input_path.is_dir():
        files = sorted(path for path in input_path.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS)
        if not files:
            fail(f"geen ondersteunde kassabonbestanden gevonden in {input_path}")
        return "directory", files
    fail(f"input is geen bestand of map: {input_path}")


def latest_scorematrix() -> Path | None:
    if not REPORT_DIR.exists():
        return None
    files = sorted(REPORT_DIR.glob("R9-10_receipt_ssot_scorematrix_*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def load_json(path: Path | None) -> dict:
    if not path or not path.exists():
        return {"items": []}
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(payload: dict) -> dict:
    items = payload.get("items") or []
    status_counts: dict[str, int] = {}
    failed_counts: dict[str, int] = {}
    by_file: dict[str, dict] = {}
    for item in items:
        status = str(item.get("status") or "")
        status_counts[status] = status_counts.get(status, 0) + 1
        file_name = str(item.get("bestand") or item.get("receipt_table_id") or "")
        by_file[file_name] = item
        for code in str(item.get("failed_criteria") or "").split(";"):
            code = code.strip()
            if code:
                failed_counts[code] = failed_counts.get(code, 0) + 1
    return {"items": len(items), "status_counts": status_counts, "failed_counts": failed_counts, "by_file": by_file}


def compare(before: dict, after: dict) -> dict:
    before_s = summarize(before)
    after_s = summarize(after)
    regressions: list[dict] = []
    improvements: list[dict] = []
    for name in sorted(set(before_s["by_file"]) | set(after_s["by_file"])):
        old = before_s["by_file"].get(name)
        new = after_s["by_file"].get(name)
        if not old or not new:
            continue
        old_failed = set(str(old.get("failed_criteria") or "").split(";")) - {""}
        new_failed = set(str(new.get("failed_criteria") or "").split(";")) - {""}
        if old.get("status") == "Gecontroleerd" and new.get("status") != "Gecontroleerd":
            regressions.append({"bestand": name, "type": "Gecontroleerd_naar_Controle_nodig"})
        if len(new_failed) > len(old_failed):
            regressions.append({"bestand": name, "type": "meer_failed_criteria", "voor": sorted(old_failed), "na": sorted(new_failed)})
        if old.get("status") != "Gecontroleerd" and new.get("status") == "Gecontroleerd":
            improvements.append({"bestand": name, "type": "Controle_nodig_naar_Gecontroleerd"})
        elif len(new_failed) < len(old_failed):
            improvements.append({"bestand": name, "type": "minder_failed_criteria", "voor": sorted(old_failed), "na": sorted(new_failed)})
    return {
        "before": {k: v for k, v in before_s.items() if k != "by_file"},
        "after": {k: v for k, v in after_s.items() if k != "by_file"},
        "regressions": regressions,
        "improvements": improvements,
    }


def write_report(data: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"R9-12_full_receipt_batch_regression_{time.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="R9-12 full receipt batch regression runner")
    parser.add_argument("input_path", help="Map, los bonbestand of ZIP met alle kassabonnen voor regressietest")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    parser.add_argument("--household-id", default=DEFAULT_HOUSEHOLD_ID)
    parser.add_argument("--fail-on-regression", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input_path).expanduser().resolve()
    input_mode, files = resolve_input(input_path)
    ok(f"input_mode={input_mode} files={len(files)} input={input_path}")

    before_path = latest_scorematrix()
    before = load_json(before_path)
    ok(f"baseline scorematrix: {before_path}" if before_path else "geen baseline scorematrix gevonden")

    archive_active_receipts(args.base_url, args.token, args.household_id)
    import_results = [import_one(args.base_url, args.token, args.household_id, path) for path in files]

    run_py(["tools/R9-06_receipt_status_governance_check.py", f"{args.base_url}/api/receipts?householdId={args.household_id}", args.token])
    run_py(["tools/R9-10_receipt_ssot_scorematrix.py", args.base_url, args.token, args.household_id])

    after_path = latest_scorematrix()
    after = load_json(after_path)
    comparison = compare(before, after)
    report = {
        "policy": "R9-12C full-batch regression via public API + R9-06 + R9-10; waits for async batch completion; no direct DB mutation; no status logic",
        "input_mode": input_mode,
        "input_path": str(input_path),
        "files": [path.name for path in files],
        "import_results": import_results,
        "before_scorematrix": str(before_path) if before_path else None,
        "after_scorematrix": str(after_path) if after_path else None,
        "comparison": comparison,
    }
    report_path = write_report(report)
    ok(f"regressierapport geschreven: {report_path}")
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    if args.fail_on_regression and comparison.get("regressions"):
        fail(f"regressies gevonden: {len(comparison['regressions'])}")
    ok("full receipt batch regression afgerond")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
