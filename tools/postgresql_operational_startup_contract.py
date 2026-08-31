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
        line
        for line in compose_lines
        if "%COMPOSE_ENV% %COMPOSE_ARGS%" not in line
    ]
    if bad_compose_lines:
        raise AssertionError(
            "Every start.bat docker compose call must use the locked base+PostgreSQL overlay/profile: "
            + repr(bad_compose_lines)
        )

    for legacy in (
        "./backend/data:/app/data",
        "/app/data/rezzerv.db",
        'mkdir "backend\\data"',
        'if not exist "backend\\data"',
    ):
        _forbid(start, legacy, "SQLite runtime authority")

    _require(start, "$datastore = [string]$r.datastore;", "health datastore read")
    _require(start, "$db = [string]$r.database;", "health database identity read")
    _require(
        start,
        "$datastore -ne 'postgresql'",
        "fail-closed PostgreSQL datastore assertion",
    )
    _require(start, "if (-not $db)", "non-empty database identity assertion")

    _require(
        start,
        'if not defined REZZERV_FRONTEND_PORT set "REZZERV_FRONTEND_PORT=5174"',
        "frontend port rehearsal override",
    )
    _require(
        start,
        'if not defined REZZERV_BACKEND_PORT set "REZZERV_BACKEND_PORT=8011"',
        "backend port rehearsal override",
    )
    _require(
        start,
        'if not defined REZZERV_STARTUP_WAIT_SECONDS set "REZZERV_STARTUP_WAIT_SECONDS=90"',
        "startup wait rehearsal override",
    )
    _require(
        start,
        'if /I "%REZZERV_STARTUP_NO_BROWSER%"=="1"',
        "non-interactive browser suppression",
    )

    _forbid(base_compose, "./backend/data:/app/data", "SQLite data mount in base compose")
    _require(
        base_compose,
        '"${REZZERV_BACKEND_PORT:-8011}:8000"',
        "backend host-port isolation boundary",
    )
    _require(
        base_compose,
        '"${REZZERV_FRONTEND_PORT:-5174}:80"',
        "frontend host-port isolation boundary",
    )

    _require(postgres_compose, "postgres:", "PostgreSQL service")
    _require(postgres_compose, "image: postgres:17-alpine", "pinned PostgreSQL runtime image")
    _require(postgres_compose, "- postgresql", "PostgreSQL compose profile")
    _require(
        postgres_compose,
        '"127.0.0.1:${REZZERV_POSTGRES_PORT:-5432}:5432"',
        "loopback-only PostgreSQL host binding",
    )
    _require(
        postgres_compose,
        "POSTGRES_USER: ${REZZERV_POSTGRES_BOOTSTRAP_USER:-rezzerv_bootstrap}",
        "bootstrap role boundary",
    )
    _require(
        postgres_compose,
        "REZZERV_POSTGRES_MIGRATION_USER: ${REZZERV_POSTGRES_MIGRATION_USER:-rezzerv_migrator}",
        "migration role boundary",
    )
    _require(
        postgres_compose,
        "REZZERV_POSTGRES_RUNTIME_USER: ${REZZERV_POSTGRES_RUNTIME_USER:-rezzerv_app}",
        "runtime role boundary",
    )
    _require(
        postgres_compose,
        "DATABASE_URL: postgresql://${REZZERV_POSTGRES_RUNTIME_USER:-rezzerv_app}",
        "runtime DATABASE_URL role",
    )
    _require(
        postgres_compose,
        "MIGRATION_DATABASE_URL: postgresql://${REZZERV_POSTGRES_MIGRATION_USER:-rezzerv_migrator}",
        "migration DATABASE_URL role",
    )
    _require(
        postgres_compose,
        "./docker/postgresql/init-roles.sh:/docker-entrypoint-initdb.d/10-rezzerv-roles.sh:ro",
        "PostgreSQL role initialization mount",
    )
    _require(
        postgres_compose,
        "REZZERV_DATASTORE_POLICY: postgresql-only",
        "PostgreSQL-only backend policy",
    )
    _forbid(
        postgres_compose,
        "REZZERV_POSTGRES_PASSWORD:",
        "single shared PostgreSQL credential",
    )

    _require(postgres_init, "REVOKE CREATE ON SCHEMA public FROM PUBLIC;", "public schema CREATE revoke")
    _require(
        postgres_init,
        'GRANT USAGE, CREATE ON SCHEMA public TO :"migration_user";',
        "migration schema authority",
    )
    _require(
        postgres_init,
        'GRANT USAGE ON SCHEMA public TO :"runtime_user";',
        "runtime schema usage only",
    )
    _require(
        postgres_init,
        'ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_user" IN SCHEMA public',
        "runtime DML default grants",
    )
    _require(
        postgres_init,
        "PostgreSQL bootstrap, migration and runtime roles must be distinct",
        "distinct role fail-closed guard",
    )

    for workflow_path in (
        "      - 'start.bat'",
        "      - 'docker-compose.yml'",
        "      - 'docker-compose.postgresql.yml'",
        "      - 'docker/postgresql/init-roles.sh'",
        "      - 'tools/postgresql_operational_startup_contract.py'",
        "      - '.github/workflows/postgresql-operational-startup-validation.yml'",
    ):
        _require(workflow, workflow_path, "operational-startup workflow path trigger")
    _require(
        workflow,
        "python tools/postgresql_operational_startup_contract.py",
        "operational startup contract CI execution",
    )
    _require(
        workflow,
        "POSTGRESQL_OPERATIONAL_STARTUP_CONTRACT_GREEN",
        "operational startup contract CI marker",
    )
    _require(
        workflow,
        "docker compose -f docker-compose.yml -f docker-compose.postgresql.yml --profile postgresql config",
        "merged PostgreSQL compose-model validation",
    )
    _require(
        workflow,
        "POSTGRESQL_OPERATIONAL_RUNTIME_CREATE_DENIED_GREEN",
        "runtime CREATE denial execution marker",
    )
    _require(
        workflow,
        "POSTGRESQL_OPERATIONAL_RUNTIME_DML_ONLY_GREEN",
        "runtime DML execution marker",
    )
    _require(
        workflow,
        "POSTGRESQL_OPERATIONAL_ROLE_SPLIT_GREEN",
        "split-role execution marker",
    )

    print("POSTGRESQL_OPERATIONAL_STARTUP_COMPOSE_GREEN")
    print("POSTGRESQL_OPERATIONAL_STARTUP_HEALTH_GREEN")
    print("POSTGRESQL_OPERATIONAL_STARTUP_ISOLATION_GREEN")
    print("POSTGRESQL_OPERATIONAL_STARTUP_ROLE_SPLIT_GREEN")
    print("POSTGRESQL_OPERATIONAL_STARTUP_CI_GREEN")
    print("POSTGRESQL_OPERATIONAL_STARTUP_CONTRACT_GREEN")


if __name__ == "__main__":
    main()
