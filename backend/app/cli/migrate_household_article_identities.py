"""CLI for Slice 2B1 household-article identity migration."""

from __future__ import annotations

import argparse
import json

from app.db import engine, get_runtime_datastore_info
from app.services.household_article_identity_migration_service import (
    migrate_household_article_identities,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory or migrate legacy live:: household-article references."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist unambiguous migrations. Without this flag only a dry-run is performed.",
    )
    args = parser.parse_args()

    report = migrate_household_article_identities(engine, dry_run=not args.apply)
    payload = {
        "runtime_datastore": get_runtime_datastore_info(),
        "result": report.to_dict(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    # Unresolved and ambiguous values are a deliberate stop condition.
    return 2 if report.unresolved or report.ambiguous else 0


if __name__ == "__main__":
    raise SystemExit(main())
