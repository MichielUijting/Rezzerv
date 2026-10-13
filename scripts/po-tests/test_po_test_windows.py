#!/usr/bin/env python3
"""Windows-only integration tests with a disposable local Git repository.

No real Inhuis clone, database, Docker instance or ports are touched.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_po_test as generator  # noqa: E402

BRANCH = "codex/po-test-fixture"


@unittest.skipUnless(os.name == "nt", "Batch integration tests require Windows")
class WindowsBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.profile = self.base / "fake-profile"
        self.work = self.profile / "Rezzerv_CODEX_WORK"
        self.work.mkdir(parents=True)
        (self.profile / "Downloads").mkdir()
        self.marker = self.base / "start-was-called.txt"
        self.remote = self.base / "origin" / "MichielUijting" / "Rezzerv.git"
        self.remote.parent.mkdir(parents=True)
        self.git("init", "--bare", str(self.remote), cwd=self.base)
        self.git("init", "-b", "main", cwd=self.work)
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Inhuis Safety Test")
        (self.work / "start.bat").write_bytes(
            b'@echo off\r\n> "%INHUIS_TEST_MARKER%" echo CALLED\r\nexit /b 0\r\n'
        )
        (self.work / "baseline.txt").write_text("baseline\n", encoding="utf-8")
        self.git("add", "start.bat", "baseline.txt")
        self.git("commit", "-m", "fixture baseline")
        self.git("remote", "add", "origin", self.remote.as_posix())
        self.git("push", "-u", "origin", "main")
        self.git("switch", "-c", BRANCH)
        (self.work / "feature.txt").write_text("candidate\n", encoding="utf-8")
        self.git("add", "feature.txt")
        self.git("commit", "-m", "fixture candidate")
        self.sha = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("push", "-u", "origin", BRANCH)
        self.git("switch", "main")

    def git(self, *args, cwd=None):
        result = subprocess.run(
            ["git", *args], cwd=cwd or self.work, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
        )
        if result.returncode:
            self.fail(f"Fixture git failed: {' '.join(args)}: {result.stderr}")
        return result

    def batch(self, sha=None):
        source = generator.TEMPLATE.read_text(encoding="utf-8")
        content = generator.render(
            source, branch=BRANCH, sha=sha or self.sha, title="Fixture",
            instructions="Controleer correcte opstart.",
        )
        path = self.base / "testscript.bat"
        path.write_bytes(content.encode("ascii"))
        env = os.environ.copy()
        env["USERPROFILE"] = str(self.profile)
        env["INHUIS_TEST_MARKER"] = str(self.marker)
        return subprocess.run(
            ["cmd.exe", "/d", "/c", str(path)], input="\r\n\r\n",
            text=True, env=env, cwd=self.base,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=45, check=False,
        )

    def test_valid_branch_starts_only_official_start(self):
        output = self.batch()
        self.assertEqual(output.returncode, 0, output.stdout)
        self.assertTrue(self.marker.exists(), output.stdout)
        self.assertEqual(self.git("rev-parse", "HEAD").stdout.strip(), self.sha)

    def test_wrong_remote_sha_must_not_switch_or_start(self):
        output = self.batch(sha="0" * 40)
        self.assertNotEqual(output.returncode, 0, output.stdout)
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.git("branch", "--show-current").stdout.strip(), "main")

    def test_tracked_dirty_worktree_protected(self):
        (self.work / "baseline.txt").write_text("my existing work\n", encoding="utf-8")
        output = self.batch()
        self.assertNotEqual(output.returncode, 0, output.stdout)
        self.assertFalse(self.marker.exists())
        self.assertEqual((self.work / "baseline.txt").read_text(), "my existing work\n")

    def test_untracked_conflicting_file_protected(self):
        (self.work / "feature.txt").write_text("MY LOCAL UNTRACKED DATA\n", encoding="utf-8")
        output = self.batch()
        self.assertNotEqual(output.returncode, 0, output.stdout)
        self.assertFalse(self.marker.exists())
        self.assertEqual((self.work / "feature.txt").read_text(), "MY LOCAL UNTRACKED DATA\n")

    def test_untracked_nonconflicting_file_preserved(self):
        (self.work / "standalone-generated.txt").write_text("PRESERVE\n", encoding="utf-8")
        output = self.batch()
        self.assertEqual(output.returncode, 0, output.stdout)
        self.assertTrue(self.marker.exists())
        self.assertEqual((self.work / "standalone-generated.txt").read_text(), "PRESERVE\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
