"""Static fail-closed guard for the optional split PostgreSQL host-agent mode."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "scripts/server-maintenance/Windows-Host-Agent.ps1"


def test_split_container_mode_is_explicit_and_paired():
    source = AGENT.read_text(encoding="utf-8")
    assert "[string]$BackendContainerName = ''" in source
    assert "[string]$PostgresContainerName = ''" in source
    assert "[bool]$BackendContainerName -ne [bool]$PostgresContainerName" in source
    assert "$BackendContainerName -ceq $PostgresContainerName" in source


def test_backend_compose_identity_and_postgres_storage_remain_checked():
    source = AGENT.read_text(encoding="utf-8")
    assert "'com.docker.compose.project' -cne $ComposeProject" in source
    assert "'com.docker.compose.service' -cne 'backend'" in source
    assert "'/var/lib/postgresql/data'" in source
    assert "Expliciete PostgreSQL-container heeft geen unieke duurzame datamount" in source
    assert "Test-InhuisDatabaseServerAddress" in source
    assert "database_runtime.database_oid" in source
    assert "pg_control_system()" in source
    assert "Assert-DirectDatabaseBinding $postgres $probe" in source
    assert source.index("Assert-DirectDatabaseBinding $postgres $probe") < source.index("$available=[ordered]")


def test_legacy_compose_mode_preserved_and_install_is_opt_in():
    source = AGENT.read_text(encoding="utf-8")
    assert "if ($DirectContainerSelection)" in source
    assert "$ComposeArgs+@('ps','-q',$Service)" in source
    assert "if ($InstallAtLogon)" in source
    assert 'scheduledArguments += " -BackendContainerName' in source
    assert "Register-ScheduledTask" in source


def test_split_install_preflights_real_database_before_persistent_mutation():
    source = AGENT.read_text(encoding="utf-8")
    preflight = source.index("if ($InstallAtLogon -and $DirectContainerSelection)")
    directory_write = source.index("New-Item -ItemType Directory -Force -Path $DataDirectory")
    task_install = source.index("Register-ScheduledTask")
    assert preflight < directory_write < task_install
    assert "Assert-DirectDatabaseBinding $preflightPostgres $preflightProbe" in source[preflight:directory_write]


def test_host_docker_argument_arrays_use_explicit_named_binding():
    import re

    source = AGENT.read_text(encoding="utf-8")
    assert not re.search(r"Invoke-DockerText\s+@\(", source)
    assert not re.search(r"Copy-DockerBinary\s+@\(", source)
    assert "Invoke-DockerText -Arguments @('inspect',$name)" in source
    assert "Copy-DockerBinary -Arguments @('exec'" in source


def test_users_frontend_port_is_physically_bound_to_exact_compose_frontend():
    source = AGENT.read_text(encoding="utf-8")
    assert "function Assert-FrontendBinding()" in source
    assert "('publish='+$FrontendUrl.Port)" in source
    assert "'com.docker.compose.project' -cne $ComposeProject" in source
    assert "'com.docker.compose.service' -cne 'frontend'" in source
    assert "NetworkSettings.Ports.'80/tcp'" in source
    assert "Assert-FrontendBinding -CheckRoutes" in source
    assert source.index("$checkStage = 'gebruikerspoort-identiteit'") < source.index("$available=[ordered]")


def test_install_never_replaces_a_stale_or_duplicate_windows_agent_task():
    source = AGENT.read_text(encoding="utf-8")
    start = source.index("if ($InstallAtLogon) {")
    registration = source.index("Register-ScheduledTask")
    preflight = source[start:registration]
    assert "Assert-FrontendBinding -CheckRoutes" in preflight
    assert "Get-ScheduledTask -TaskName 'Inhuis-Onderhoud-*'" in preflight
    assert "Andere Inhuis-onderhoudstaak bestaat nog" in preflight
    assert "Onderhoudstaak bestaat al" in preflight
