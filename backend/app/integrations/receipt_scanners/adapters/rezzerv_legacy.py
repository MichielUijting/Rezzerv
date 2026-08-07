from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Callable

from app.receipt_ingestion.service_parts.receipt_result_helpers import ReceiptParseResult, determine_final_parse_status

from ..contracts import ScannerCapabilities, ScannerHealth
from ..errors import UnsupportedOperation
from ..schemas.canonical_receipt_v1 import CanonicalDocumentV1, CanonicalReceiptV1, IdentifiersV1, LineConfidenceV1, ProviderInfoV1, QualityV1, ReceiptBodyV1, ReceiptLineV1, ScannerErrorV1, StoreV1, TotalsV1, TransactionV1
from ..schemas.scan_request_v1 import ScanRequestV1
from ..schemas.scan_result_v1 import ScanResultV1, ScanSubmissionV1

LegacyParser = Callable[[bytes, str, str], ReceiptParseResult]


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _split_purchase_at(value: str | None) -> tuple[date | None, time | None]:
    raw = str(value or "").strip()
    if not raw:
        return None, None
    if len(raw) == 10:
        try:
            return date.fromisoformat(raw), None
        except Exception:
            pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.date(), parsed.timetz().replace(tzinfo=None)
    except Exception:
        pass
    try:
        return date.fromisoformat(raw[:10]), None
    except Exception:
        return None, None


def _legacy_line_to_canonical(index: int, line: dict[str, Any]) -> ReceiptLineV1:
    raw_text = str(line.get("raw_label") or line.get("normalized_label") or "").strip()
    if not raw_text:
        raise ValueError(f"Legacy parser line {index + 1} has no raw/normalized label")
    confidence = line.get("confidence_score")
    identifiers = None
    barcode = str(line.get("barcode") or "").strip() or None
    if barcode:
        identifiers = IdentifiersV1(
            gtin=barcode if barcode.isdigit() and len(barcode) in {8, 12, 13, 14} else None,
            barcode=barcode,
            retailer_sku=None,
        )
    return ReceiptLineV1(
        line_number=index + 1,
        line_type="product",
        raw_text=raw_text,
        description=str(line.get("normalized_label") or "").strip() or None,
        quantity=_decimal(line.get("quantity")),
        unit=str(line.get("unit") or "").strip() or None,
        unit_price=_decimal(line.get("unit_price")),
        gross_amount=_decimal(line.get("line_total")),
        discount_amount=_decimal(line.get("discount_amount")),
        line_total=_decimal(line.get("line_total")),
        identifiers=identifiers,
        confidence=LineConfidenceV1(
            description=confidence,
            quantity=confidence,
            unit_price=confidence,
            line_total=confidence,
            identifier=confidence if barcode else None,
        ) if confidence is not None else None,
    )


class RezzervLegacyScannerAdapter:
    provider_code = "rezzerv-legacy"

    def __init__(self, *, parser: LegacyParser | None = None, max_file_bytes: int = 15_000_000, model_version: str = "legacy-parser-current") -> None:
        self._parser = parser
        self._max_file_bytes = int(max_file_bytes)
        self._model_version = model_version
        self._results: dict[str, CanonicalReceiptV1] = {}

    def capabilities(self) -> ScannerCapabilities:
        return ScannerCapabilities(
            mime_types=("application/pdf", "image/png", "image/jpeg", "image/webp", "message/rfc822", "text/html", "text/plain"),
            max_file_bytes=self._max_file_bytes,
            asynchronous=False,
            supports_cancel=False,
            features=("raw_text", "legacy_parser_equivalence"),
        )

    def _resolve_parser(self) -> LegacyParser:
        if self._parser is not None:
            return self._parser
        from app.services.receipt_service import parse_receipt_content
        return parse_receipt_content

    def submit(self, request: ScanRequestV1) -> ScanSubmissionV1:
        job_id = f"legacy-local-{uuid.uuid4().hex}"
        result_id = f"legacy-result-{uuid.uuid4().hex}"
        parse_result = self._resolve_parser()(
            request.runtime_document_bytes(), request.document.original_filename, request.document.mime_type
        )
        canonical = self._to_canonical(request=request, parse_result=parse_result, job_id=job_id, result_id=result_id)
        self._results[job_id] = canonical
        return ScanSubmissionV1(
            scan_id=request.scan_id,
            provider_job_id=job_id,
            status="completed" if canonical.status == "completed" else "failed",
            result=canonical,
        )

    def _to_canonical(self, *, request: ScanRequestV1, parse_result: ReceiptParseResult, job_id: str, result_id: str) -> CanonicalReceiptV1:
        provider = ProviderInfoV1(code=self.provider_code, job_id=job_id, result_id=result_id, model_version=self._model_version)
        if not parse_result.is_receipt:
            value = CanonicalReceiptV1(
                scan_id=request.scan_id,
                provider=provider,
                status="failed",
                error=ScannerErrorV1(
                    code="NO_RECEIPT_DETECTED",
                    message="De inhoud is door de Rezzerv legacy scanner niet als kassabon herkend.",
                    retryable=False,
                    provider_reference=result_id,
                ),
                processed_at=datetime.now(timezone.utc),
            )
            value._legacy_parse_status = parse_result.parse_status
            value._legacy_parser_diagnostics = parse_result.parser_diagnostics
            value._legacy_confidence_score = parse_result.confidence_score
            return value

        purchase_date, purchase_time = _split_purchase_at(parse_result.purchase_at)
        lines = [_legacy_line_to_canonical(index, line) for index, line in enumerate(parse_result.lines or [])]
        final_status = determine_final_parse_status(parse_result)
        total = _decimal(parse_result.total_amount)
        value = CanonicalReceiptV1(
            scan_id=request.scan_id,
            provider=provider,
            status="completed",
            document=CanonicalDocumentV1(sha256=request.document.sha256, mime_type=request.document.mime_type, page_count=None),
            receipt=ReceiptBodyV1(
                store=StoreV1(name=parse_result.store_name, branch_name=parse_result.store_branch, confidence=parse_result.confidence_score),
                transaction=TransactionV1(
                    purchase_date=purchase_date,
                    purchase_time=purchase_time,
                    currency=parse_result.currency or request.hints.currency or "EUR",
                    confidence=parse_result.confidence_score,
                ),
                totals=TotalsV1(
                    discount_total=_decimal(parse_result.discount_total),
                    grand_total=total,
                    paid_total=total,
                    confidence=parse_result.confidence_score,
                ),
                lines=lines,
                warnings=[],
            ),
            quality=QualityV1(overall_confidence=parse_result.confidence_score, requires_review=final_status != "approved"),
            processed_at=datetime.now(timezone.utc),
        )
        value._legacy_parse_status = parse_result.parse_status
        value._legacy_parser_diagnostics = parse_result.parser_diagnostics
        value._legacy_confidence_score = parse_result.confidence_score
        return value

    def get_result(self, provider_job_id: str) -> ScanResultV1:
        try:
            return self._results[provider_job_id]
        except KeyError as exc:
            raise KeyError(f"Unknown legacy receipt scanner job {provider_job_id!r}") from exc

    def cancel(self, provider_job_id: str) -> None:
        raise UnsupportedOperation("The synchronous Rezzerv legacy scanner cannot be cancelled")

    def health(self) -> ScannerHealth:
        return ScannerHealth(
            available=True,
            provider_code=self.provider_code,
            contract_version="1.0",
            model_version=self._model_version,
        )
