#!/usr/bin/env python3
"""Pure fail-closed self-tests for incremental CI carry-forward planning."""
from __future__ import annotations

from frontend_regression_plan import classify_incremental_files
from shared_fullstack_plan import select_authority_plan


def main() -> int:
    workflow_patterns = ["frontend/src/**", "frontend/tests/e2e/**", "frontend/tests/*.contract.mjs", "frontend/package.json"]
    assert classify_incremental_files(
        ["frontend/tests/mobile-ui-conformity.contract.mjs"],
        workflow_patterns,
    )[0] == "contracts"
    assert classify_incremental_files(["docs/readme.md"], workflow_patterns)[0] == "reuse"
    assert classify_incremental_files(["frontend/src/App.jsx"], workflow_patterns)[0] == "full"
    assert classify_incremental_files(["frontend/tests/not-a-contract.txt"], workflow_patterns)[0] == "full"

    authorities = {
        "alpha": {"paths": ["frontend/src/alpha/**", "scripts/ci/shared_fullstack_plan.py"]},
        "beta": {"paths": ["backend/beta/**", "scripts/ci/shared_fullstack_plan.py"]},
    }
    complete = ["frontend/src/alpha/a.jsx", "backend/beta/service.py"]
    plan, carried, unmapped = select_authority_plan(
        authorities,
        complete,
        ["frontend/src/alpha/a.jsx"],
        prior_green=True,
    )
    assert plan == {"alpha": True, "beta": False}
    assert carried == ["beta"]
    assert unmapped == []

    plan, carried, unmapped = select_authority_plan(
        authorities,
        complete,
        ["docs/note.md"],
        prior_green=True,
    )
    assert plan == {"alpha": False, "beta": False}
    assert set(carried) == {"alpha", "beta"}
    assert unmapped == []

    plan, carried, unmapped = select_authority_plan(
        authorities,
        complete,
        ["frontend/src/unmapped/file.jsx"],
        prior_green=True,
    )
    assert plan == {"alpha": True, "beta": True}
    assert carried == []
    assert unmapped == ["frontend/src/unmapped/file.jsx"]

    plan, carried, unmapped = select_authority_plan(
        authorities,
        complete,
        ["docs/note.md"],
        prior_green=False,
    )
    assert plan == {"alpha": True, "beta": True}
    assert carried == []
    assert unmapped == []

    plan, carried, unmapped = select_authority_plan(
        authorities,
        ["frontend/src/unmapped/file.jsx"],
        ["frontend/src/unmapped/file.jsx"],
        prior_green=True,
    )
    assert plan == {"alpha": True, "beta": True}
    assert carried == []
    assert unmapped == ["frontend/src/unmapped/file.jsx"]

    print("INCREMENTAL_CI_CARRY_FORWARD_SELF_TEST_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
