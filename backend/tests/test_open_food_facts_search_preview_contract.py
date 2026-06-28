from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_compose_passes_off_runtime_config_to_backend():
    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "REZZERV_OFF_SEARCH_BASE_URL" in compose_text
    assert "REZZERV_OFF_SEARCH_TIMEOUT_SECONDS" in compose_text
    assert "${REZZERV_OFF_SEARCH_TIMEOUT_SECONDS:-8}" in compose_text
    assert "REZZERV_OFF_SEARCH_MAX_QUERIES" in compose_text
    assert "${REZZERV_OFF_SEARCH_MAX_QUERIES:-3}" in compose_text


if __name__ == "__main__":
    test_compose_passes_off_runtime_config_to_backend()
    print("OFF_SEARCH_PREVIEW_CONTRACT_OK")
