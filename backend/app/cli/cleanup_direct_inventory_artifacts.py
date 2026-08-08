"""CLI for controlled cleanup of invalid Direct / Direct inventory rows."""

from __future__ import annotations

import argparse
import json

from app.db import engine, get_runtime_datastore_info
from app.services.direct_inventory_cleanup_service import cleanup_direct_inventory_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Report or remove inventory rows incorrectly stored at Direct / Direct. "
            "Purchase and spend history are preserved."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete matching Direct / Direct inventory rows. Without this flag only a dry-run is performed.",
    )
    parser.add_argument(
        "--household-id",
        default=None,
        help="Optional household scope. Default scans all households in the runtime database.",
    )
    args = parser.parse_args()

    report = cleanup_direct_inventory_artifacts(
        engine,
        dry_run=not args.apply,
        household_id=args.household_id,
    )
    payload = {
        "runtime_datastore": get_runtime_datastore_info(),
        "result": report.to_dict(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
