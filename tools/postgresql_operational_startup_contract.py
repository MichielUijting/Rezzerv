from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START_BAT = ROOT / "start.bat"
BASE_COMPOSE = ROOT / "docker-compose.yml"
POSTGRES_COMPOSE = ROOT / "docker-compose.postgresql.yml"
POSTGRES_INIT = ROOT / "docker" / "postgresql" / "init-roles.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "postgresql-operational-startup-validation.yml"


def _read(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"Required startup contract file missing: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"Missing {label}: {needle!r}")


def _forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise AssertionError(f"Forbidden {label}: {needle!r}")


def main() -> None:
    start = _read(START_BAT)
    base_compose = _read(BASE_COMPOSE)
    postgres_compose = _read(POSTGRES_COMPOSE)
    postgres_init = _read(POSTGRES_INIT)
    workflow = _read(WORKFLOW)

    compose_args = (
        'set "COMPOSE_ARGS=-f docker-compose.yml -f docker-compose.postgresql.yml '
        '--profile postgresql"'
    )
    _require(start, compose_args, "PostgreSQL compose overlay/profile authority")
    _require(
        start,
        'if not exist "docker-compose.postgresql.yml" goto :project_error',
        "PostgreSQL compose overlay project preflight",
    )

    compose_lines = [
        line.strip()
        for line in start.splitlines()
        if line.strip().lower().startswith("docker compose ")
    ]
    if not compose_lines:
        raise AssertionError("start.bat contains no docker compose commands")
    bad_compose_lines = [
        line for line in compose_lines if "%COMPOSE_ENV% %COMPOSE_ARGS%" not in line
    ]
    if bad_compose_lines:
        raise AssertionError(
            "Every start.bat docker compose call must use the locked base+PostgreSQL "
            f"overlay/profile: {bad_compose_lines!r}"
        )

    # Windows service validation must not depend on cmd pipes/findstr encoding behavior.
    _forbid(start, "config --services | findstr", "Windows cmd pipe service validation")
    _forbid(
        start,
        'findstr /I /X /C:"postgres" "%COMPOSE_SERVICES_FILE%"',
        "encoding-sensitive findstr service validation",
    )
    for needle, label in (
        (
            'set "COMPOSE_SERVICES_FILE=%TEMP%\\rezzerv-compose-services-%RANDOM%-%RANDOM%.txt"',
            "Compose service temp file",
        ),
        (
            'config --services > "%COMPOSE_SERVICES_FILE%" 2>nul',
            "Compose service capture",
        ),
        (
            'set "REZZERV_COMPOSE_SERVICES_FILE=%COMPOSE_SERVICES_FILE%"',
            "Compose service environment handoff",
        ),
        (
            "Get-Content -LiteralPath $env:REZZERV_COMPOSE_SERVICES_FILE",
            "encoding-aware Compose service read",
        ),
        ("$services -contains 'postgres'", "exact PostgreSQL service membership"),
        ("Actieve services:", "diagnostic active services output"),
    ):
        _require(start, needle, label)

    _forbid(
        start,
        "up -d --force-recreate frontend",
        "redundant frontend-only force recreate",
    )
    _require(
        start,
        "[4/6] Application containers started from freshly built images.",
        "single-stack startup completion marker",
    )

    for legacy in (
        "./backend/data:/app/data",
        "/app/data/rezzerv.db",
        'mkdir "backend\\data"',
        'if not exist "backend\\data"',
    ):
        _forbid(start, legacy, "SQLite runtime authority")

    for needle, label in (
        ("$datastore = [string]$r.datastore;", "health datastore read"),
        ("$db = [string]$r.database;", "health database identity read"),
        ("$datastore -ne 'postgresql'", "fail-closed PostgreSQL datastore assertion"),
        ("if (-not $db)", "non-empty database identity assertion"),
        (
            'if not defined REZZERV_FRONTEND_PORT set "REZZERV_FRONTEND_PORT=5174"',
            "frontend port rehearsal override",
        ),
        (
            'if not defined REZZERV_BACKEND_PORT set "REZZERV_BACKEND_PORT=8011"',
            "backend port rehearsal override",
        ),
        (
            'if not defined REZZERV_STARTUP_WAIT_SECONDS set "REZZERV_STARTUP_WAIT_SECONDS=90"',
            "startup wait rehearsal override",
        ),
        ('if /I "%REZZERV_STARTUP_NO_BROWSER%"=="1"', "browser suppression"),
    ):
        _require(start, needle, label)

    _forbid(base_compose, "./backend/data:/app/data", "SQLite data mount")
    _require(
        base_compose,
        '"${REZZERV_BACKEND_PORT:-8011}:8000"',
        "backend host-port isolation",
    )
    _require(
        base_compose,
        '"${REZZERV_FRONTEND_PORT:-5174}:80"',
        "frontend host-port isolation",
    )

    for needle, label in (
        ("postgres:", "PostgreSQL service"),
        ("image: postgres:17-alpine", "pinned PostgreSQL image"),
        ("- postgresql", "PostgreSQL compose profile"),
        (
            '"127.0.0.1:${REZZERV_POSTGRES_PORT:-5432}:5432"',
            "loopback-only PostgreSQL host binding",
        ),
        (
            "POSTGRES_USER: ${REZZERV_POSTGRES_BOOTSTRAP_USER:-rezzerv_bootstrap}",
            "bootstrap role boundary",
        ),
        (
            "REZZERV_POSTGRES_MIGRATION_USER: ${REZZERV_POSTGRES_MIGRATION_USER:-rezzerv_migrator}",
            "migration role boundary",
        ),
        (
            "REZZERV_POSTGRES_RUNTIME_USER: ${REZZERV_POSTGRES_RUNTIME_USER:-rezzerv_app}",
            "runtime role boundary",
        ),
        (
            "DATABASE_URL: postgresql://${REZZERV_POSTGRES_RUNTIME_USER:-rezzerv_app}",
            "runtime DATABASE_URL role",
        ),
        (
            "MIGRATION_DATABASE_URL: postgresql://${REZZERV_POSTGRES_MIGRATION_USER:-rezzerv_migrator}",
            "migration DATABASE_URL role",
        ),
        (
            "./docker/postgresql/init-roles.sh:/docker-entrypoint-initdb.d/10-rezzerv-roles.sh:ro",
            "PostgreSQL split-role initializer",
        ),
        ("REZZERV_DATASTORE_POLICY: postgresql-only", "PostgreSQL-only backend policy"),
    ):
        _require(postgres_compose, needle, label)
    _forbid(postgres_compose, "REZZERV_POSTGRES_PASSWORD:", "shared PostgreSQL credential")

    # Health must use the same Compose-network TCP route as backend connections. Loopback
    # can follow different pg_hba rules and can hide credential drift in a persisted volume.
    _forbid(postgres_compose, "pg_isready", "bootstrap-only PostgreSQL readiness")
    _forbid(
        postgres_compose,
        "psql -h 127.0.0.1",
        "loopback-only split-role health authentication",
    )
    for needle, label in (
        (
            'PGPASSWORD="$${REZZERV_POSTGRES_MIGRATION_PASSWORD}"',
            "migration-role health password",
        ),
        (
            'psql -h postgres -U "$${REZZERV_POSTGRES_MIGRATION_USER}"',
            "migration-role Compose-network readiness",
        ),
        (
            'PGPASSWORD="$${REZZERV_POSTGRES_RUNTIME_PASSWORD}"',
            "runtime-role health password",
        ),
        (
            'psql -h postgres -U "$${REZZERV_POSTGRES_RUNTIME_USER}"',
            "runtime-role Compose-network readiness",
        ),
    ):
        _require(postgres_compose, needle, label)

    for needle, label in (
        ("REVOKE CREATE ON SCHEMA public FROM PUBLIC;", "public CREATE revoke"),
        (
            'GRANT USAGE, CREATE ON SCHEMA public TO :"migration_user";',
            "migration schema authority",
        ),
        (
            'GRANT USAGE ON SCHEMA public TO :"runtime_user";',
            "runtime schema usage only",
        ),
        (
            'ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_user" IN SCHEMA public',
            "runtime DML default grants",
        ),
        (
            "PostgreSQL bootstrap, migration and runtime roles must be distinct",
            "distinct role fail-closed guard",
        ),
    ):
        _require(postgres_init, needle, label)

    for workflow_path in (
        "      - 'start.bat'",
        "      - 'docker-compose.yml'",
        "      - 'docker-compose.postgresql.yml'",
        "      - 'docker/postgresql/init-roles.sh'",
        "      - 'tools/postgresql_operational_startup_contract.py'",
        "      - '.github/workflows/postgresql-operational-startup-validation.yml'",
    ):
        _require(workflow, workflow_path, "operational workflow path trigger")

    for needle, label in (
        (
            "python tools/postgresql_operational_startup_contract.py",
            "operational contract CI execution",
        ),
        (
            "docker compose -f docker-compose.yml -f docker-compose.postgresql.yml --profile postgresql config",
            "merged PostgreSQL Compose validation",
        ),
        (
            "docker inspect --format '{{.State.Health.Status}}'",
            "Docker health-status readiness proof",
        ),
        ("psql -h postgres", "Compose-network PostgreSQL auth proof"),
        (
            "POSTGRESQL_OPERATIONAL_ROLE_READY_HEALTH_GREEN",
            "split-role-ready health marker",
        ),
        (
            "POSTGRESQL_OPERATIONAL_RUNTIME_DML_ONLY_GREEN",
            "runtime DML marker",
        ),
        (
            "POSTGRESQL_OPERATIONAL_RUNTIME_CREATE_DENIED_GREEN",
            "runtime CREATE denial marker",
        ),
        (
            "POSTGRESQL_OPERATIONAL_CREDENTIAL_DRIFT_DETECTED_GREEN",
            "credential drift detection marker",
        ),
        (
            "POSTGRESQL_OPERATIONAL_CREDENTIAL_DRIFT_RECOVERY_GREEN",
            "credential drift recovery marker",
        ),
        ("POSTGRESQL_OPERATIONAL_ROLE_SPLIT_GREEN", "split-role marker"),
    ):
        _require(workflow, needle, label)

    print("POSTGRESQL_OPERATIONAL_STARTUP_COMPOSE_GREEN")
    print("POSTGRESQL_OPERATIONAL_STARTUP_WINDOWS_ENCODING_SAFE_GREEN")
    print("POSTGRESQL_OPERATIONAL_STARTUP_ROLE_READY_HEALTH_GREEN")
    print("POSTGRESQL_OPERATIONAL_STARTUP_HEALTH_GREEN")
    print("POSTGRESQL_OPERATIONAL_STARTUP_ISOLATION_GREEN")
    print("POSTGRESQL_OPERATIONAL_STARTUP_ROLE_SPLIT_GREEN")
    print("POSTGRESQL_OPERATIONAL_STARTUP_CREDENTIAL_DRIFT_GUARD_GREEN")
    print("POSTGRESQL_OPERATIONAL_STARTUP_CI_GREEN")
    print("POSTGRESQL_OPERATIONAL_STARTUP_CONTRACT_GREEN")


if __name__ == "__main__":
    main()
