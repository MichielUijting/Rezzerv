#!/usr/bin/env python3
"""Generate a single-click Inhuis PO test from the PR544-derived canonical template.

No Git, Docker, database or application mutation occurs in this generator.
The generated Windows batch file invokes only the repository's start.bat.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "scripts" / "po-tests" / "po-test-template.bat"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
BRANCH_RE = re.compile(r"codex/[a-z0-9][a-z0-9_./-]*\Z")
TEXT_RE = re.compile(r"[A-Za-z0-9 .,:/\-]+\Z")
PLACEHOLDERS = ("@@BRANCH@@", "@@SHA@@", "@@TITLE@@", "@@TEST_INSTRUCTIONS@@")
MANDATORY = (
    "CLS",
    "git status --porcelain --untracked-files=no",
    "git diff --quiet --exit-code",
    "git diff --cached --quiet --exit-code",
    "git fetch --no-tags origin \"refs/heads/%BRANCH%:refs/remotes/origin/%BRANCH%\"",
    "git switch --track -c \"%BRANCH%\" \"origin/%BRANCH%\"",
    "git switch \"%BRANCH%\"",
    "git merge --ff-only \"origin/%BRANCH%\"",
    "if /I not \"!REMOTE_SHA!\"==\"%EXPECTED_SHA%\"",
    "if /I not \"!LOCAL_SHA!\"==\"%EXPECTED_SHA%\"",
    "call start.bat",
)
FORBIDDEN_COMMAND_RE = re.compile(
    r"(?im)^\s*(?:git\s+(?:reset|clean|checkout|pull|restore)\b|"
    r"docker(?:\.exe)?\s+|docker-compose\b|"
    r"powershell\b|pwsh\b|"
    r"del\s+/|rmdir\b|rd\s+/)"
)


class ValidationError(ValueError):
    pass


def validate_template(source: str) -> None:
    if not source.lstrip().startswith("@echo off\nCLS\n"):
        raise ValidationError("Template moet beginnen met @echo off en CLS.")
    for token in PLACEHOLDERS:
        if source.count(token) != 1:
            raise ValidationError(f"Verplichte unieke placeholder ontbreekt: {token}")
    for command in MANDATORY:
        if command not in source:
            raise ValidationError(f"Verplichte veiligheidscontrole ontbreekt: {command}")
    if source.count("call start.bat") != 1:
        raise ValidationError("start.bat moet precies een keer worden aangeroepen.")
    forbidden = FORBIDDEN_COMMAND_RE.search(source)
    if forbidden:
        raise ValidationError(f"Verboden opdracht in template: {forbidden.group(0).strip()}")
    if "C:\\Users\\" in source or "C:/Users/" in source:
        raise ValidationError("Geen persoonsgebonden absoluut pad in publieke repository.")
    if re.search(r"(?im)^.*\b(?:reset --hard|checkout -B|docker compose up|docker compose down)\b", source):
        raise ValidationError("Verboden reset- of Compose-orchestratie.")


def safe_text(value: str, label: str, max_len: int = 120) -> str:
    if not value or len(value) > max_len or not TEXT_RE.fullmatch(value):
        raise ValidationError(f"Ongeldige {label}; alleen veilige ASCII-tekst toegestaan.")
    return value


def render(source: str, *, branch: str, sha: str, title: str, instructions: str) -> str:
    validate_template(source)
    if not BRANCH_RE.fullmatch(branch) or ".." in branch or branch.endswith("/"):
        raise ValidationError("Ongeldige taakbranch.")
    if not SHA_RE.fullmatch(sha):
        raise ValidationError("Ongeldige exacte commit-SHA.")
    safe_text(title, "titel", max_len=75)
    raw_lines = [line.strip() for line in instructions.splitlines()]
    lines = [line for line in raw_lines if line]
    if not lines or len(lines) > 35:
        raise ValidationError("Geef 1 tot 35 functionele testinstructies op.")
    for line in lines:
        safe_text(line, "testinstructie")
    script = source
    for token, value in (
        ("@@BRANCH@@", branch),
        ("@@SHA@@", sha),
        ("@@TITLE@@", title),
        ("@@TEST_INSTRUCTIONS@@", "\n".join(f"echo {line}" for line in lines)),
    ):
        script = script.replace(token, value)
    if any(token in script for token in PLACEHOLDERS):
        raise ValidationError("Niet alle placeholders zijn vervangen.")
    return script.replace("\n", "\r\n")

def verify_generated_script(
    artifact: bytes, *, source: str, branch: str, sha: str,
    title: str, instructions: str,
) -> None:
    """Fail closed on the actual bytes to be delivered to the PO."""
    expected = render(source, branch=branch, sha=sha, title=title, instructions=instructions)
    try:
        decoded = artifact.decode("ascii")
    except UnicodeError as exc:
        raise ValidationError("Eindbestand is geen geldig ASCII-batchbestand.") from exc
    if artifact != expected.encode("ascii"):
        raise ValidationError("Eindbestand wijkt af van canonieke generatoruitvoer.")
    if b"\\r\\n" not in artifact or b"\\n" in artifact.replace(b"\\r\\n", b""):
        raise ValidationError("Eindbestand mist consequente Windows-regelafbrekingen.")
    if re.search(r"(?im)^echo\\s+echo(?:\\s|$)", decoded):
        raise ValidationError("Dubbele echo gevonden in eindbestand.")
    if decoded.count("call start.bat") != 1 or "@@" in decoded:
        raise ValidationError("Eindbestand heeft ongeldige start of placeholders.")



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--instructions-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify-only", action="store_true",
                        help="Verify existing output byte-for-byte; never overwrite it.")
    args = parser.parse_args()
    if not TEMPLATE.is_file():
        raise SystemExit("STOP: verplichte referentiesjabloon niet gevonden. Geen script aangemaakt.")
    try:
        result = render(
            TEMPLATE.read_text(encoding="utf-8"),
            branch=args.branch,
            sha=args.sha,
            title=args.title,
            instructions=args.instructions_file.read_text(encoding="utf-8"),
        )
        if args.output.suffix.lower() != ".bat":
            raise ValidationError("Uitvoer moet een .bat-bestand zijn.")
        if args.verify_only:
            if not args.output.is_file():
                raise ValidationError("Eindbestand ontbreekt; verificatie geweigerd.")
            verify_generated_script(
                args.output.read_bytes(), source=TEMPLATE.read_text(encoding="utf-8"),
                branch=args.branch, sha=args.sha, title=args.title,
                instructions=args.instructions_file.read_text(encoding="utf-8"),
            )
            print("PO_TEST_EXACT_ARTIFACT_VERIFIED_GREEN")
            return
        artifact = result.encode("ascii")
        verify_generated_script(
            artifact, source=TEMPLATE.read_text(encoding="utf-8"),
            branch=args.branch, sha=args.sha, title=args.title,
            instructions=args.instructions_file.read_text(encoding="utf-8"),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(artifact)
    except (OSError, UnicodeError, ValidationError) as exc:
        raise SystemExit(f"STOP: PO-testscriptaanmaak geweigerd: {exc}") from exc
    print(f"PO_TEST_ARTIFACT_GENERATED={args.output}")


if __name__ == "__main__":
    main()
