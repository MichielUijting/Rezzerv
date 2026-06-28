from __future__ import annotations

import os


def test_backend_container_has_off_runtime_config():
    assert os.getenv("REZZERV_OFF_SEARCH_BASE_URL", "").strip()
    assert os.getenv("REZZERV_OFF_SEARCH_TIMEOUT_SECONDS") == "8"
    assert os.getenv("REZZERV_OFF_SEARCH_MAX_QUERIES") == "3"


if __name__ == "__main__":
    test_backend_container_has_off_runtime_config()
    print("OFF_SEARCH_PREVIEW_CONTRACT_OK")
