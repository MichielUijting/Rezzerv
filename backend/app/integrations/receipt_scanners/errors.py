from __future__ import annotations


class ReceiptScannerError(RuntimeError):
    """Provider-neutral scanner failure."""

    code = "PROVIDER_UNAVAILABLE"
    retryable = False

    def __init__(self, message: str, *, code: str | None = None, retryable: bool | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = bool(retryable)


class UnsupportedOperation(ReceiptScannerError):
    code = "UNSUPPORTED_FORMAT"


class ProviderConfigurationError(ReceiptScannerError):
    code = "PROVIDER_UNAVAILABLE"


class ContractValidationError(ReceiptScannerError):
    code = "CONTRACT_VALIDATION_FAILED"


class ProviderTimeoutError(ReceiptScannerError):
    code = "PROVIDER_TIMEOUT"
    retryable = True
