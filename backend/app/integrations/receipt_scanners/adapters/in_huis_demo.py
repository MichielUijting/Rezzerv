from __future__ import annotations

from ..contracts import ScannerCapabilities, ScannerHealth
from ..errors import ProviderConfigurationError
from ..schemas.scan_request_v1 import ScanRequestV1
from ..schemas.scan_result_v1 import ScanResultV1, ScanSubmissionV1


class InHuisDemoScannerAdapter:
    """Boundary for the alternative Meesdeboer/in-huis-demo scanner.

    The public repository interface could not be retrieved through the available
    GitHub connection while this PR was built. This adapter is therefore
    intentionally fail-closed until its concrete invocation/response contract is
    verified and implemented. It must never silently fall back to the legacy
    scanner, because the household administrator explicitly selected this
    provider.
    """

    provider_code = "in-huis-demo"

    def __init__(self, *, max_file_bytes: int = 15_000_000) -> None:
        self._max_file_bytes = int(max_file_bytes)

    def capabilities(self) -> ScannerCapabilities:
        return ScannerCapabilities(
            mime_types=("application/pdf", "image/png", "image/jpeg", "image/webp"),
            max_file_bytes=self._max_file_bytes,
            asynchronous=False,
            supports_cancel=False,
            features=("external_demo_contract_pending",),
        )

    def submit(self, request: ScanRequestV1) -> ScanSubmissionV1:
        raise ProviderConfigurationError(
            "De alternatieve kassabonscanner is geselecteerd, maar de technische "
            "interface van Meesdeboer/in-huis-demo is nog niet geverifieerd in deze "
            "runtime. Kies tijdelijk de Inhuis-scanner of rond de adapterkoppeling af."
        )

    def get_result(self, provider_job_id: str) -> ScanResultV1:
        raise ProviderConfigurationError("Alternatieve kassabonscanner heeft geen actief resultaat.")

    def cancel(self, provider_job_id: str) -> None:
        raise ProviderConfigurationError("Alternatieve kassabonscanner ondersteunt annuleren nog niet.")

    def health(self) -> ScannerHealth:
        return ScannerHealth(
            available=False,
            provider_code=self.provider_code,
            contract_version="1.0",
            model_version=None,
            message="Externe demo-interface nog niet geverifieerd.",
        )
