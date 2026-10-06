from __future__ import annotations

import pytest

from app.integrations.receipt_scanners.errors import ProviderConfigurationError
from app.integrations.receipt_scanners.runtime import _gateway_for_provider


def test_household_provider_defaults_to_inhuis_gateway():
    gateway = _gateway_for_provider("inhuis")
    assert gateway.registry.active_provider_code == "rezzerv-legacy"


def test_alternative_provider_is_explicit_and_fail_closed_until_contract_is_verified():
    gateway = _gateway_for_provider("in-huis-demo")
    assert gateway.registry.active_provider_code == "in-huis-demo"
    provider = gateway.registry.get()
    health = provider.health()
    assert health.available is False
    with pytest.raises(ProviderConfigurationError):
        provider.submit(None)  # type: ignore[arg-type]
