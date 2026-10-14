"""Static contract for the headless scanner startup integration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_official_startup_keeps_docker_path_and_adds_scanner_only_after_health():
    source = (ROOT / "start.bat").read_text(encoding="utf-8")
    assert source.index("call :VerifyFrontendVersion || exit /b 1") < source.index("start_owned_scanner_background.ps1")
    assert "docker compose %COMPOSE_ENV% %COMPOSE_ARGS% up -d --build --force-recreate" in source
    assert "if errorlevel 1 (" in source[source.index("start_owned_scanner_background.ps1"):]


def test_headless_scanner_fails_closed_without_killing_occupied_port():
    source = (ROOT / "tools/receipt_scanner/start_owned_scanner_background.ps1").read_text(encoding="utf-8")
    assert "Get-NetTCPConnection -LocalPort 8003 -State Listen" in source
    assert "if ($listener)" in source
    assert "if (Test-ScannerHealth)" in source
    assert "Start-Process" in source
    assert "Stop-Process" not in source
    assert "docker compose" not in source
    assert "INHUIS_SCANNER_BACKGROUND" in source


def test_headless_starter_does_not_wait_for_keypress_on_error():
    source = (ROOT / "start-alternatieve-kassabonscanner.bat").read_text(encoding="utf-8")
    assert source.count('if "%INHUIS_SCANNER_BACKGROUND%"=="1" exit /b 1') >= 3
    assert 'if "%INHUIS_SCANNER_BACKGROUND%"=="1" exit /b %RESULT%' in source
