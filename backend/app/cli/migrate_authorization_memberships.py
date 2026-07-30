from app.db import engine
from app.services.authorization_membership_service import migrate_legacy_household_memberships


def main() -> None:
    with engine.begin() as conn:
        result = migrate_legacy_household_memberships(conn)
    print(
        "AUTHORIZATION_MEMBERSHIPS_MIGRATED "
        f"scanned={result.scanned} "
        f"created={result.created} "
        f"preserved={result.preserved} "
        f"skipped={result.skipped}"
    )


if __name__ == "__main__":
    main()
