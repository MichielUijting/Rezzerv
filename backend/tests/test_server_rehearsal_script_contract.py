"""Static safety baseline for the standalone Windows isolated reboot rehearsal.

This does not replace running the script against disposable Windows/Docker state.
"""

from pathlib import Path
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts/server-maintenance/Inhuis_Server_Geisoleerde_Herstartproef.cmd"
)


class ServerRehearsalScriptContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = SCRIPT.read_text(encoding="utf-8")

    def test_single_click_report_and_open_console(self):
        content = self.content
        self.assertTrue(content.startswith("@echo off\nCLS\n"))
        self.assertIn("# INHUIS_POWERSHELL_START", content)
        self.assertIn("Inhuis_Server_Geisoleerde_Herstartproef_Resultaat.txt", content)
        self.assertIn("\nCLS\n", content)
        self.assertIn("\npause\n", content)

    def test_exact_existing_runtime_preflight_before_mutation(self):
        content = self.content
        before = content.index("$liveVolumes =")
        create = content.index("[void](Invoke-TestCompose -Arguments @('up'")
        self.assertLess(before, create)
        self.assertIn("LIVE_BACKEND_IMAGE_GEWIJZIGD", content)
        self.assertIn("LIVE_DATABASE_IMAGE_GEWIJZIGD", content)
        self.assertIn("LIVE_DATABASE_VOLUME_GEWIJZIGD", content)

    def test_isolated_synthetic_data_and_no_broad_cleanup(self):
        content = self.content
        self.assertIn("[guid]::NewGuid()", content)
        self.assertIn("network_mode: none", content)
        self.assertIn("pull_policy: never", content)
        self.assertIn("--no-build','--pull','never", content)
        self.assertIn("$testVolumes[0].Name -eq $liveVolumes[0].Name", content)
        self.assertIn("CREATE TABLE inhuis_rehearsal", content)
        self.assertIn("$current.Config.Labels.'com.docker.compose.project' -ceq $project", content)
        self.assertNotIn("docker compose down", content.lower())
        self.assertNotIn("volume rm", content.lower())
        self.assertNotIn("docker.exe rm", content.lower())
        self.assertNotIn("start.bat", content.lower())
        self.assertNotIn("shutdown.exe", content.lower())

    def test_array_arguments_bind_as_one_parameter(self):
        import re

        self.assertNotRegex(self.content, r"Invoke-Test(?:Docker|Compose)\s+@\(")
        self.assertIn("Invoke-TestCompose -Arguments @('stop','postgres')", self.content)


if __name__ == "__main__":
    unittest.main()
