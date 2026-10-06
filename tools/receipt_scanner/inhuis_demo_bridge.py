from __future__ import annotations

import hashlib
import hmac
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request


REPO_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_ROOT = Path(
    os.getenv("INHUIS_DEMO_ROOT", str(REPO_ROOT / "external" / "in-huis-demo"))
).resolve()

# Keep the Anthropic credential in the external scanner environment; keep the
# bridge credential in Inhuis' local .env. Neither file belongs in Git.
load_dotenv(EXTERNAL_ROOT / ".env", override=False)
load_dotenv(REPO_ROOT / ".env", override=False)

if not EXTERNAL_ROOT.is_dir():
    raise RuntimeError(f"Externe scannerbron ontbreekt: {EXTERNAL_ROOT}")

sys.path.insert(0, str(EXTERNAL_ROOT))
from rezzerv import scan_engine  # noqa: E402


app = Flask("inhuis-external-receipt-scanner")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
PROVIDER_CODE = "in-huis-demo"


def _required_bridge_key() -> str:
    value = str(os.getenv("REZZERV_IN_HUIS_DEMO_SCANNER_API_KEY", "") or "").strip()
    if not value:
        raise RuntimeError(
            "REZZERV_IN_HUIS_DEMO_SCANNER_API_KEY ontbreekt in de lokale Inhuis .env. "
            "Start via start-alternatieve-kassabonscanner.bat zodat dit automatisch wordt ingericht."
        )
    return value


BRIDGE_KEY = _required_bridge_key()
BRIDGE_KEY_HEADER = str(
    os.getenv("REZZERV_IN_HUIS_DEMO_SCANNER_API_KEY_HEADER", "X-API-Key") or "X-API-Key"
).strip() or "X-API-Key"


def _authorized() -> bool:
    supplied = str(request.headers.get(BRIDGE_KEY_HEADER) or "")
    return bool(supplied) and hmac.compare_digest(supplied, BRIDGE_KEY)


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _purchase_parts(value: Any) -> tuple[str | None, str | None]:
    raw = str(value or "").strip()
    if not raw:
        return None, None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date().isoformat(), None
        except ValueError:
            return None, None
    return parsed.date().isoformat(), parsed.time().replace(tzinfo=None).isoformat(timespec="seconds")


def _failed_result(
    *,
    scan_id: str,
    sha256: str,
    mime_type: str,
    message: str,
    code: str,
    retryable: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scan_id": scan_id,
        "provider": {
            "code": PROVIDER_CODE,
            "model_version": str(getattr(scan_engine, "CLAUDE_MODEL", "") or "") or None,
        },
        "status": "failed",
        "document": {"sha256": sha256, "mime_type": mime_type},
        "receipt": None,
        "quality": None,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        },
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


def _canonical_result(
    *,
    scan_id: str,
    sha256: str,
    mime_type: str,
    parsed: dict[str, Any],
) -> dict[str, Any]:
    receipt = parsed.get("receipt") if isinstance(parsed, dict) else None
    if not isinstance(receipt, dict):
        return _failed_result(
            scan_id=scan_id,
            sha256=sha256,
            mime_type=mime_type,
            message="De alternatieve scanner gaf geen bonobject terug.",
            code="INVALID_PROVIDER_RESULT",
            retryable=False,
        )

    total = _decimal(receipt.get("total_amount"))
    source_lines = receipt.get("lines")
    if total is None or not isinstance(source_lines, list) or not source_lines:
        return _failed_result(
            scan_id=scan_id,
            sha256=sha256,
            mime_type=mime_type,
            message="De alternatieve scanner vond geen bruikbaar totaal en/of geen bonregels.",
            code="NO_RECEIPT_DETECTED",
            retryable=False,
        )

    lines: list[dict[str, Any]] = []
    discount_total = Decimal("0")
    for index, raw_line in enumerate(source_lines, start=1):
        if not isinstance(raw_line, dict):
            continue
        raw_label = str(raw_line.get("raw_label") or "").strip()
        if not raw_label:
            continue
        kind = str(raw_line.get("kind") or "product").strip().lower()
        line_total = _decimal(raw_line.get("line_total"))
        discount = _decimal(raw_line.get("discount_amount"))
        if discount is not None:
            discount_total += abs(discount)
        line_type = "product" if kind == "product" else ("discount" if (line_total or Decimal("0")) < 0 else "fee")
        lines.append(
            {
                "line_number": index,
                "line_type": line_type,
                "raw_text": raw_label,
                "description": raw_label,
                "quantity": raw_line.get("quantity"),
                "unit": raw_line.get("unit"),
                "unit_price": raw_line.get("unit_price"),
                "discount_amount": raw_line.get("discount_amount"),
                "line_total": raw_line.get("line_total"),
            }
        )

    if not any(line["line_type"] == "product" for line in lines):
        return _failed_result(
            scan_id=scan_id,
            sha256=sha256,
            mime_type=mime_type,
            message="De alternatieve scanner vond geen productregels op de bon.",
            code="NO_RECEIPT_DETECTED",
            retryable=False,
        )

    purchase_date, purchase_time = _purchase_parts(receipt.get("purchase_at"))
    totals_match = bool(parsed.get("totals_match"))
    warnings: list[str] = []
    if not totals_match:
        warnings.append("De som van de herkende bonregels sluit niet aantoonbaar aan op het totaalbedrag.")

    return {
        "schema_version": "1.0",
        "scan_id": scan_id,
        "provider": {
            "code": PROVIDER_CODE,
            "model_version": str(getattr(scan_engine, "CLAUDE_MODEL", "") or "") or None,
        },
        "status": "completed",
        "document": {"sha256": sha256, "mime_type": mime_type},
        "receipt": {
            "store": {
                "name": receipt.get("store_name"),
                "branch_name": receipt.get("store_branch"),
            },
            "transaction": {
                "purchase_date": purchase_date,
                "purchase_time": purchase_time,
                "currency": str(receipt.get("currency") or "EUR").upper(),
            },
            "totals": {
                "discount_total": str(discount_total) if discount_total else None,
                "grand_total": str(total),
            },
            "lines": lines,
            "warnings": warnings,
        },
        "quality": {
            "overall_confidence": None,
            "requires_review": (not totals_match) or not receipt.get("store_name") or purchase_date is None,
        },
        "error": None,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "provider": PROVIDER_CODE,
            "model": str(getattr(scan_engine, "CLAUDE_MODEL", "") or "") or None,
            "headless": True,
        }
    )


@app.post("/scan")
def scan():
    if not _authorized():
        return jsonify({"error": "ongeldige scanner-servicekey"}), 401

    upload = request.files.get("file")
    scan_id = str(request.form.get("scan_id") or "").strip()
    expected_sha = str(request.form.get("document_sha256") or "").strip().lower()
    if upload is None or not scan_id or len(expected_sha) != 64:
        return jsonify({"error": "scan_id, document_sha256 en file zijn verplicht"}), 400

    content = upload.read()
    if not content:
        return jsonify({"error": "leeg bestand"}), 400
    if len(content) > MAX_UPLOAD_BYTES:
        return jsonify({"error": "bestand is te groot"}), 413

    actual_sha = hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(actual_sha, expected_sha):
        return jsonify({"error": "document_sha256 komt niet overeen met het ontvangen bestand"}), 400

    mime_type = str(upload.mimetype or "application/octet-stream").lower()
    try:
        if content[:4] == b"%PDF" or mime_type == "application/pdf":
            parsed = scan_engine.parse_receipt_from_pdf(content)
            mime_type = "application/pdf"
        else:
            parsed = scan_engine.parse_receipt_from_image(content, mime_type)
    except scan_engine.ScanError as exc:
        status = int(getattr(exc, "status", 502) or 502)
        if status == 422:
            code, retryable = "DOCUMENT_UNREADABLE", False
        elif status == 503:
            code, retryable = "PROVIDER_UNAVAILABLE", True
        else:
            code, retryable = "PROVIDER_UNAVAILABLE", status >= 500
        return jsonify(
            _failed_result(
                scan_id=scan_id,
                sha256=actual_sha,
                mime_type=mime_type,
                message=str(getattr(exc, "message", "") or exc),
                code=code,
                retryable=retryable,
            )
        )

    return jsonify(
        _canonical_result(
            scan_id=scan_id,
            sha256=actual_sha,
            mime_type=mime_type,
            parsed=parsed,
        )
    )


if __name__ == "__main__":
    port = int(os.getenv("REZZERV_IN_HUIS_DEMO_SCANNER_PORT", "8003"))
    print("Inhuis alternatieve kassabonscanner draait headless.")
    print(f"Luistert op poort {port}; gebruik de scanner uitsluitend via Inhuis.")
    app.run(host="0.0.0.0", port=port, debug=False)
