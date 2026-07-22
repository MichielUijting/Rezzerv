from __future__ import annotations

import json
from pathlib import Path

from app.testing.household_fallback_audit import audit


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    payload = audit(root)
    summary = payload["summary"]
    categories = summary["by_category"]

    assert summary["runtime_occurrences"] == 94, summary
    assert summary["unclassified_runtime_occurrences"] == 0, payload["unclassified_runtime_occurrences"]
    assert categories.get("deferred-share-target") == 2, categories
    assert categories.get("frontend-server-authority") == 6, categories
    assert categories.get("auth-bootstrap") == 8, categories
    assert categories.get("non-household-boolean-or-value") == 1, categories
    assert categories.get("signed-state-or-server-source") == 8, categories
    assert categories.get("authenticated-route-or-helper") == 20, categories
    assert categories.get("authenticated-internal-helper") == 12, categories
    assert categories.get("platform-admin-diagnostic-or-test") == 35, categories
    assert categories.get("test-dev-fixture") == 2, categories

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print("M2C2N_HOUSEHOLD_FALLBACK_CONTRACT_GREEN")


if __name__ == "__main__":
    main()
