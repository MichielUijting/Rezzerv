"""Read-only contract tests for Inhuis Docker Windows restart verification.

These static checks do not simulate Windows, Docker Desktop, or a reboot.
"""
from pathlib import Path
import re
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "Inhuis_Docker_Windows_Herstartcontrole.cmd"
)


class WindowsDockerRestartContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_one_click_windows_script(self):
        self.assertTrue(self.source.startswith("@echo off\nCLS\n"))
        self.assertGreaterEqual(self.source.count("\nCLS\n"), 2)
        self.assertIn("pause", self.source.lower())
        self.assertIn("# INHUIS_RESTART_POWERSHELL", self.source)

    def test_no_hardcoded_host_version_port_or_project(self):
        for forbidden in (
            "inhuis-1296-hersteltest",
            "15174",
            "Rezzerv-MVP-v01.12.296",
            "C:\\Users\\",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_only_read_only_docker_commands(self):
        for forbidden in (
            "docker compose up", "docker compose down",
            "docker start", "docker stop", "docker restart",
            "docker run", "docker rm", "docker volume rm",
            "docker network rm", "docker system prune",
            "Start-ScheduledTask", "Stop-ScheduledTask",
            "Restart-Computer", "Stop-Computer", "Set-ItemProperty",
            "git reset",
        ):
            self.assertNotIn(forbidden.lower(), self.source.lower())
        self.assertIn("@('ps','-q')", self.source)
        self.assertIn("@('inspect',$Id)", self.source)
        self.assertIn("app.maintenance.server_maintenance_host_probe", self.source)

    def test_live_runtime_selection(self):
        self.assertIn("com.docker.compose.service=frontend", self.source)
        self.assertIn("/version.json", self.source)
        self.assertIn("/api/health", self.source)
        self.assertIn("INHUIS_FRONTEND_NIET_UNIEK", self.source)
        self.assertIn("INHUIS_BACKEND_NIET_UNIEK", self.source)
        self.assertIn("POSTGRES_CONTAINER_NIET_UNIEK", self.source)
        self.assertIn("POSTGRES_ADRES_NIET_LEESBAAR", self.source)

    def test_restart_policy_and_after_boot(self):
        self.assertIn("'unless-stopped'", self.source)
        self.assertIn("'always'", self.source)
        self.assertIn("LastBootUpTime", self.source)
        self.assertIn("SnapshotEquals", self.source)
        self.assertIn("BESTAANDE_CONTAINERS_NIET_TERUG", self.source)
        for key in ("frontend_id", "frontend_image", "backend_id",
                    "backend_image", "postgres_id", "postgres_image"):
            self.assertIn(key, self.source)

    def test_reports_and_baseline_not_repo_files(self):
        self.assertIn("Inhuis_Docker_Windows_Herstartcontrole_Resultaat.txt", self.source)
        self.assertIn("Inhuis_Docker_Windows_Herstart_Baseline.json", self.source)
        self.assertIn("Downloads", self.source)
        self.assertNotRegex(self.source, r"Say\s*\(?[^\n]*(Config\.Env|PrivateKey|Password)")

    def test_failure_cannot_be_reported_as_success(self):
        self.assertRegex(
            self.source,
            r"if\(-not \$same\)\{throw 'BESTAANDE_CONTAINERS_NIET_TERUG'\}",
        )
        self.assertIn("if($completed){exit 0}else{exit 1}", self.source)


if __name__ == "__main__":
    unittest.main()
