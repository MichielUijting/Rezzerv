from __future__ import annotations

import json
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app import main

HOUSEHOLD_ID = "0"


def _with_household_zero_overrides(action):
    original_require_platform_admin_user = main.require_platform_admin_user
    original_ensure_household = main.ensure_household
    try:
        main.require_platform_admin_user = lambda _authorization=None: {
            "email": "supergebruiker@rezzerv.local"
        }
        main.ensure_household = lambda _email: {
            "id": HOUSEHOLD_ID,
            "naam": "Regressietest huishouden 0",
        }
        return action()
    finally:
        main.require_platform_admin_user = original_require_platform_admin_user
        main.ensure_household = original_ensure_household


def prepare() -> dict:
    def action():
        reset = main.reset_regression_fixture_state()
        receipts = main.seed_regression_kassa_receipts(authorization=None)
        return {
            "status": "ok",
            "mode": "prepare",
            "household_id": HOUSEHOLD_ID,
            "reset": reset,
            "receipts": receipts,
        }

    result = _with_household_zero_overrides(action)
    if str(result.get("reset", {}).get("household_id")) != HOUSEHOLD_ID:
        raise RuntimeError(f"Reset gebruikte niet huishouden {HOUSEHOLD_ID}: {result}")
    if str(result.get("receipts", {}).get("household_id")) != HOUSEHOLD_ID:
        raise RuntimeError(f"Kassabonseed gebruikte niet huishouden {HOUSEHOLD_ID}: {result}")
    return result


def cleanup() -> dict:
    result = main.cleanup_regression_fixture_state(HOUSEHOLD_ID)
    return {
        "status": "ok",
        "mode": "cleanup",
        "household_id": HOUSEHOLD_ID,
        **result,
    }


def main_entry() -> int:
    mode = str(sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode == "prepare":
        result = prepare()
    elif mode == "cleanup":
        result = cleanup()
    else:
        raise RuntimeError("Gebruik: household_zero_regression_fixture.py prepare|cleanup")

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    print(f"HOUSEHOLD_ZERO_FIXTURE_{mode.upper()}=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
