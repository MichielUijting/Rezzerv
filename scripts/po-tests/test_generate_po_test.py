#!/usr/bin/env python3
"""Self-tests: both valid generation and deliberate safety-policy violations."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_po_test as po  # noqa: E402

BRANCH = "codex/lidl-import-date-window"
SHA = "45836836038ad5c7fe985e8a4c81d2de277ebc5b"
TITLE = "PR 575 Lidl datumbereik"
INSTRUCTIONS = "Controleer automatische periode.\nHerhaal import zonder dubbele bon.\n"


class POTestSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = po.TEMPLATE.read_text(encoding="utf-8")

    def test_valid_single_click_script_uses_official_start(self):
        content = po.render(self.template, branch=BRANCH, sha=SHA, title=TITLE, instructions=INSTRUCTIONS)
        self.assertTrue(content.startswith("@echo off\r\nCLS\r\n"))
        self.assertIn('set "EXPECTED_SHA=' + SHA + '"', content)
        self.assertIn('set "BRANCH=' + BRANCH + '"', content)
        self.assertEqual(content.count("call start.bat"), 1)
        self.assertIn("echo Controleer automatische periode.", content)

    def test_final_artifact_has_exactly_one_echo_per_instruction(self):
        artifact = po.render(self.template, branch=BRANCH, sha=SHA, title=TITLE, instructions=INSTRUCTIONS).encode("ascii")
        po.verify_generated_script(
            artifact, source=self.template, branch=BRANCH, sha=SHA,
            title=TITLE, instructions=INSTRUCTIONS,
        )
        self.assertIn(b"echo Controleer automatische periode.\\r\\n", artifact)
        self.assertNotIn(b"echo echo Controleer", artifact)

    def test_final_artifact_rejects_nested_echo(self):
        artifact = po.render(self.template, branch=BRANCH, sha=SHA, title=TITLE, instructions=INSTRUCTIONS).encode("ascii")
        tampered = artifact.replace(b"echo Controleer", b"echo echo Controleer")
        with self.assertRaises(po.ValidationError):
            po.verify_generated_script(
                tampered, source=self.template, branch=BRANCH, sha=SHA,
                title=TITLE, instructions=INSTRUCTIONS,
            )

    def test_final_artifact_rejects_tampered_sha_and_start(self):
        artifact = po.render(self.template, branch=BRANCH, sha=SHA, title=TITLE, instructions=INSTRUCTIONS).encode("ascii")
        for tampered in (
            artifact.replace(SHA.encode(), b"0" * 40),
            artifact.replace(b"call start.bat", b"call unsafe.bat"),
            artifact.replace(b"\\r\\n", b"\\n"),
        ):
            with self.subTest(tampered=tampered[-80:]), self.assertRaises(po.ValidationError):
                po.verify_generated_script(
                    tampered, source=self.template, branch=BRANCH, sha=SHA,
                    title=TITLE, instructions=INSTRUCTIONS,
                )

    def test_final_artifact_rejects_wrong_candidate_metadata(self):
        artifact = po.render(self.template, branch=BRANCH, sha=SHA, title=TITLE, instructions=INSTRUCTIONS).encode("ascii")
        with self.assertRaises(po.ValidationError):
            po.verify_generated_script(
                artifact, source=self.template, branch=BRANCH,
                sha="1" * 40, title=TITLE, instructions=INSTRUCTIONS,
            )

    def test_missing_reference_must_not_fall_back(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse((Path(temp) / "po-test-template.bat").exists())
            # Generator explicitly checks the source before writing anything.
            self.assertTrue("if not TEMPLATE.is_file()" in Path(po.__file__).read_text(encoding="utf-8"))

    def test_malformed_sha_rejected(self):
        with self.assertRaises(po.ValidationError):
            po.render(self.template, branch=BRANCH, sha="012345", title=TITLE, instructions=INSTRUCTIONS)

    def test_branch_injection_rejected(self):
        for invalid in ["main", "codex/x&del", "codex/../../main", "codex/foo | calc"]:
            with self.subTest(invalid=invalid), self.assertRaises(po.ValidationError):
                po.render(self.template, branch=invalid, sha=SHA, title=TITLE, instructions=INSTRUCTIONS)

    def test_instructions_injection_rejected(self):
        for invalid in ["Hello & del files", "echo %PATH%", "print ^ anything", "line | command"]:
            with self.subTest(invalid=invalid), self.assertRaises(po.ValidationError):
                po.render(self.template, branch=BRANCH, sha=SHA, title=TITLE, instructions=invalid)

    def test_forbidden_reset_rejected(self):
        self.assert_rejects(self.template + "\ngit reset --hard HEAD\n")

    def test_forbidden_alternative_compose_rejected(self):
        self.assert_rejects(self.template + "\ndocker compose up -d\n")

    def test_missing_sha_check_rejected(self):
        self.assert_rejects(self.template.replace('if /I not "!LOCAL_SHA!"=="%EXPECTED_SHA%"', "if /I not X==Y"))

    def test_missing_remote_sha_check_rejected(self):
        self.assert_rejects(self.template.replace('if /I not "!REMOTE_SHA!"=="%EXPECTED_SHA%"', "if /I not X==Y"))

    def test_missing_local_dirty_check_rejected(self):
        self.assert_rejects(self.template.replace("git diff --quiet --exit-code", "rem disabled"))

    def test_modified_git_switch_is_rejected(self):
        self.assert_rejects(self.template.replace('git switch "%BRANCH%"', 'git checkout -B "%BRANCH%"'))

    def test_second_start_is_rejected(self):
        self.assert_rejects(self.template + "\ncall start.bat\n")

    def test_missing_start_is_rejected(self):
        self.assert_rejects(self.template.replace("call start.bat", "rem start disabled"))

    def test_personal_absolute_path_rejected(self):
        self.assert_rejects(self.template.replace("%USERPROFILE%", "C:\\Users\\Somebody"))

    def assert_rejects(self, candidate):
        with self.assertRaises(po.ValidationError):
            po.render(candidate, branch=BRANCH, sha=SHA, title=TITLE, instructions=INSTRUCTIONS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
