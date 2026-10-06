from __future__ import annotations

import uuid
from urllib.parse import quote

import httpx

from ..contracts import ScannerCapabilities, ScannerHealth
from ..errors import ContractValidationError, ProviderConfigurationError, ReceiptScannerError
from ..schemas.canonical_receipt_v1 import CanonicalReceiptV1
from ..schemas.scan_request_v1 import ScanRequestV1
from ..schemas.scan_result_v1 import ScanResultV1, ScanSubmissionV1


class InHuisDemoScannerAdapter:
    """HTTP adapter for the external CanonicalReceiptV1 scanner contract.

    Contract source: Rezzerv External Receipt Scanner Testkit v1.0 supplied by
    the PO. The external scanner is deliberately kept outside household/product
    persistence: it receives document bytes plus scanner hints and returns only
    CanonicalReceiptV1 observations.
    """

    provider_code = "in-huis-demo"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        api_key_header: str = "X-API-Key",
        submit_path: str = "/scan",
        poll_path: str = "/scan/{job_id}",
        request_timeout_seconds: float = 30.0,
        max_file_bytes: int = 15_000_000,
        client: httpx.Client | None = None,
    ) -> None:
        normalized_base = str(base_url or "").strip().rstrip("/")
        if not normalized_base:
            raise ProviderConfigurationError(
                "De alternatieve kassabonscanner is gekozen maar REZZERV_IN_HUIS_DEMO_SCANNER_BASE_URL ontbreekt."
            )
        if not normalized_base.startswith(("http://", "https://")):
            raise ProviderConfigurationError("Alternatieve kassabonscanner vereist een http(s)-base-URL.")
        self._base_url = normalized_base
        self._api_key = str(api_key or "").strip() or None
        self._api_key_header = str(api_key_header or "X-API-Key").strip() or "X-API-Key"
        self._submit_path = self._normalize_path(submit_path, "/scan")
        self._poll_path = self._normalize_path(poll_path, "/scan/{job_id}")
        if "{job_id}" not in self._poll_path:
            raise ProviderConfigurationError("Poll-pad van alternatieve kassabonscanner moet {job_id} bevatten.")
        self._request_timeout_seconds = float(request_timeout_seconds)
        if self._request_timeout_seconds <= 0:
            raise ProviderConfigurationError("Request-timeout van alternatieve kassabonscanner moet positief zijn.")
        self._max_file_bytes = int(max_file_bytes)
        self._client = client

    @staticmethod
    def _normalize_path(value: str, fallback: str) -> str:
        path = str(value or fallback).strip() or fallback
        return path if path.startswith("/") else f"/{path}"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers[self._api_key_header] = self._api_key
        return headers

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            if self._client is not None:
                return self._client.request(method, url, timeout=self._request_timeout_seconds, **kwargs)
            with httpx.Client(timeout=self._request_timeout_seconds, follow_redirects=False) as client:
                return client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise ReceiptScannerError(
                "Alternatieve kassabonscanner reageerde niet op tijd.",
                code="PROVIDER_TIMEOUT",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise ReceiptScannerError(
                "Alternatieve kassabonscanner is niet bereikbaar.",
                code="PROVIDER_UNAVAILABLE",
                retryable=True,
            ) from exc

    @staticmethod
    def _canonical(payload: object) -> CanonicalReceiptV1:
        if not isinstance(payload, dict):
            raise ContractValidationError("Alternatieve kassabonscanner gaf geen JSON-object terug.")
        try:
            return CanonicalReceiptV1.model_validate(payload)
        except Exception as exc:
            raise ContractValidationError(
                f"Alternatieve kassabonscanner gaf geen geldig CanonicalReceiptV1-resultaat: {exc}"
            ) from exc

    @staticmethod
    def _job_id(payload: dict, canonical: CanonicalReceiptV1 | None = None) -> str | None:
        provider_payload = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
        candidates = (
            provider_payload.get("job_id"),
            payload.get("provider_job_id"),
            payload.get("job_id"),
            canonical.provider.job_id if canonical and canonical.provider else None,
        )
        for candidate in candidates:
            value = str(candidate or "").strip()
            if value:
                return value
        return None

    def capabilities(self) -> ScannerCapabilities:
        return ScannerCapabilities(
            mime_types=("application/pdf", "image/png", "image/jpeg", "image/webp", "text/plain"),
            max_file_bytes=self._max_file_bytes,
            asynchronous=True,
            supports_cancel=False,
            features=("canonical_receipt_v1", "http_provider", "sync_or_async"),
        )

    def submit(self, request: ScanRequestV1) -> ScanSubmissionV1:
        response = self._request(
            "POST",
            f"{self._base_url}{self._submit_path}",
            headers=self._headers(),
            data={
                "scan_id": request.scan_id,
                "schema_version": request.schema_version,
                "locale": request.hints.locale or "nl-NL",
                "currency": request.hints.currency or "EUR",
                "document_sha256": request.document.sha256,
            },
            files={
                "file": (
                    request.document.original_filename,
                    request.runtime_document_bytes(),
                    request.document.mime_type,
                )
            },
        )
        if response.status_code not in {200, 202}:
            raise ReceiptScannerError(
                f"Alternatieve kassabonscanner weigerde de scan (HTTP {response.status_code}).",
                code="PROVIDER_UNAVAILABLE",
                retryable=response.status_code >= 500,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ContractValidationError("Alternatieve kassabonscanner gaf geen geldige JSON terug.") from exc
        if not isinstance(payload, dict):
            raise ContractValidationError("Alternatieve kassabonscanner gaf geen JSON-object terug.")

        status = str(payload.get("status") or "").strip().lower()
        if response.status_code == 202 or status in {"queued", "processing"}:
            job_id = self._job_id(payload)
            if not job_id:
                raise ContractValidationError("Asynchrone scannerrespons bevat geen job_id.")
            return ScanSubmissionV1(
                scan_id=request.scan_id,
                provider_job_id=job_id,
                status="processing" if status == "processing" else "queued",
                result=None,
            )

        canonical = self._canonical(payload)
        job_id = self._job_id(payload, canonical) or f"sync-{uuid.uuid4().hex}"
        return ScanSubmissionV1(
            scan_id=request.scan_id,
            provider_job_id=job_id,
            status="failed" if canonical.status == "failed" else "completed",
            result=canonical,
        )

    def get_result(self, provider_job_id: str) -> ScanResultV1:
        job_id = str(provider_job_id or "").strip()
        if not job_id:
            raise ContractValidationError("Scanner job_id ontbreekt.")
        path = self._poll_path.replace("{job_id}", quote(job_id, safe=""))
        response = self._request(
            "GET",
            f"{self._base_url}{path}",
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise ReceiptScannerError(
                f"Alternatieve kassabonscanner kon scanstatus niet ophalen (HTTP {response.status_code}).",
                code="PROVIDER_UNAVAILABLE",
                retryable=response.status_code >= 500,
            )
        try:
            return self._canonical(response.json())
        except ValueError as exc:
            raise ContractValidationError("Alternatieve kassabonscanner gaf bij polling geen geldige JSON terug.") from exc

    def cancel(self, provider_job_id: str) -> None:
        # Canonical testkit v1.0 defines no HTTP cancellation endpoint.
        return None

    def health(self) -> ScannerHealth:
        return ScannerHealth(
            available=True,
            provider_code=self.provider_code,
            contract_version="1.0",
            model_version=None,
            message=f"HTTP-provider geconfigureerd op {self._base_url}.",
        )
