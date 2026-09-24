from __future__ import annotations

from pathlib import Path

from app.alembic_head_authority import repository_head_revision


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_PATHS = (
    "backend/app/maintenance/postgresql_data_migration_head.py",
    "backend/app/maintenance/postgresql_legacy_production_rebuild.py",
    "backend/tests/migration_foundation_head_selftest.py",
    ".github/workflows/postgresql-data-migration-validation.yml",
    ".github/workflows/postgresql-migration-foundation-validation.yml",
    ".github/workflows/postgresql-runtime-startup-schema-authority.yml",
)


def main() -> None:
    head = repository_head_revision()
    migration_matches = list(
        (REPO_ROOT / "backend" / "alembic" / "versions").glob(f"{head}_*.py")
    )
    if len(migration_matches) != 1:
        raise AssertionError(
            f"Alembic head must map to exactly one migration file: {head!r} "
            f"matches={migration_matches!r}"
        )

    for relative_path in AUTHORITY_PATHS:
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        if head in content:
            raise AssertionError(
                "Current Alembic head must not be hardcoded in authority files: "
                f"{relative_path} contains {head}"
            )

    requirements = (REPO_ROOT / "backend" / "requirements.txt").read_text(
        encoding="utf-8"
    )
    if "httpx==0.28.1" not in requirements.splitlines():
        raise AssertionError(
            "backend/requirements.txt must pin httpx for FastAPI/Starlette TestClient CI"
        )

    print(f"ALEMBIC_HEAD_AUTHORITY_GREEN revision={head}")
    print("BACKEND_TESTCLIENT_DEPENDENCY_GREEN httpx=0.28.1")


if __name__ == "__main__":
    main()
