from __future__ import annotations

from collections.abc import Iterable

from .contracts import ReceiptScannerProvider
from .errors import ProviderConfigurationError


class ProviderRegistry:
    def __init__(self, providers: Iterable[ReceiptScannerProvider], *, active_provider_code: str) -> None:
        self._providers = {provider.provider_code: provider for provider in providers}
        self.active_provider_code = str(active_provider_code or "").strip()
        if not self.active_provider_code:
            raise ProviderConfigurationError("No active receipt scanner provider is configured")
        if self.active_provider_code not in self._providers:
            raise ProviderConfigurationError(
                f"Unknown receipt scanner provider {self.active_provider_code!r}; "
                f"available={sorted(self._providers)}"
            )

    def get(self, provider_code: str | None = None) -> ReceiptScannerProvider:
        code = str(provider_code or self.active_provider_code).strip()
        try:
            return self._providers[code]
        except KeyError as exc:
            raise ProviderConfigurationError(
                f"Unknown receipt scanner provider {code!r}; available={sorted(self._providers)}"
            ) from exc

    def available_provider_codes(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))
