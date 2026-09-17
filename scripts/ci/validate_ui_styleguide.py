#!/usr/bin/env python3
"""Fail-closed governance check for the canonical Inhuis UI styleguide."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STYLEGUIDE_PATH = "docs/project/UI-STYLEGUIDE-SUMMARY.md"
TOKENS_PATH = "frontend/src/ui/tokens.css"

HARD_STYLE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^frontend/src/ui/",
        r"^frontend/src/.*\.(?:css|scss|sass|less)$",
        r"^frontend/public/inhuis-.*\.(?:svg|png|jpe?g|webp)$",
    )
)

UI_REVIEW_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^frontend/src/.*\.(?:jsx?|tsx?)$",
        r"^frontend/index\.html$",
        r"^frontend/public/.*\.(?:svg|png|jpe?g|webp)$",
    )
)

REQUIRED_TOKENS = (
    "--color-brand-primary",
    "--color-brand-light",
    "--color-text-primary",
    "--color-text-inverse",
    "--color-border-default",
    "--color-table-grid",
    "--font-family-base",
    "--font-size-ui-body",
    "--font-size-ui-title",
    "--radius-sm",
    "--radius-md",
    "--radius-lg",
    "--space-xs",
    "--space-sm",
    "--space-md",
    "--space-lg",
    "--space-xl",
)

IMPACT_RE = re.compile(
    r"(?im)^\s*[-*]?\s*STYLEGUIDE_IMPACT:\s*"
    r"(updated|reviewed-no-change|not-applicable)\s*$"
)
REASON_RE = re.compile(r"(?im)^\s*[-*]?\s*STYLEGUIDE_REASON:\s*(.+?)\s*$")


def fail(message: str) -> None:
    raise SystemExit(f"[ERROR] {message}")


def read_text(path: str) -> str:
    full = ROOT / path
    if not full.is_file():
        fail(f"Verplicht bestand ontbreekt: {path}")
    return full.read_text(encoding="utf-8")


def git(*args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        fail(f"git {' '.join(args)} faalde: {process.stderr.strip()}")
    return process.stdout.strip()


def matches_any(path: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(path) for pattern in patterns)


def classify_paths(changed_paths: list[str]) -> tuple[list[str], list[str]]:
    hard = sorted({p for p in changed_paths if matches_any(p, HARD_STYLE_PATTERNS)})
    ui_review = sorted(
        {
            p
            for p in changed_paths
            if matches_any(p, UI_REVIEW_PATTERNS) and p not in hard
        }
    )
    return hard, ui_review


def parse_declaration(pr_body: str) -> tuple[str | None, str | None]:
    impact_match = IMPACT_RE.search(pr_body or "")
    reason_match = REASON_RE.search(pr_body or "")
    impact = impact_match.group(1).lower() if impact_match else None
    reason = reason_match.group(1).strip() if reason_match else None
    return impact, reason


def evaluate_change_policy(changed_paths: list[str], pr_body: str) -> list[str]:
    errors: list[str] = []
    hard, ui_review = classify_paths(changed_paths)
    guide_changed = STYLEGUIDE_PATH in changed_paths
    impact, reason = parse_declaration(pr_body)

    if hard:
        if not guide_changed:
            errors.append(
                "Styling-, token-, shared-UI- of Inhuis-visual-assetwijziging vereist "
                f"een gelijktijdige update van {STYLEGUIDE_PATH}."
            )
        if impact != "updated":
            errors.append(
                "Voor styleguide-dragende UI-wijzigingen moet de PR-body exact "
                "'STYLEGUIDE_IMPACT: updated' bevatten."
            )
        if not reason or len(reason) < 10:
            errors.append(
                "Voeg een concrete STYLEGUIDE_REASON toe (minimaal 10 tekens)."
            )
        return errors

    if ui_review:
        if guide_changed:
            if impact != "updated":
                errors.append(
                    "De styleguide is gewijzigd; gebruik daarom "
                    "'STYLEGUIDE_IMPACT: updated'."
                )
        else:
            if impact != "reviewed-no-change":
                errors.append(
                    "UI-wijziging zonder styleguidewijziging vereist "
                    "'STYLEGUIDE_IMPACT: reviewed-no-change'."
                )
        if not reason or len(reason) < 10:
            errors.append(
                "Voeg een concrete STYLEGUIDE_REASON toe (minimaal 10 tekens)."
            )
        return errors

    return errors


def parse_css_tokens(css: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for name, value in re.findall(r"(?m)^\s*(--[\w-]+)\s*:\s*([^;]+);", css):
        tokens[name] = value.strip()
    return tokens


def validate_canonical_styleguide() -> None:
    guide = read_text(STYLEGUIDE_PATH)
    tokens = parse_css_tokens(read_text(TOKENS_PATH))

    required_phrases = (
        "# Inhuis UI-styleguide",
        "Status: **canonieke UI-bron**",
        "## Typografie",
        "## Kleuren",
        "## Spacing, radius en elevation",
        "## Wijzigings- en governance-regel",
        "STYLEGUIDE_IMPACT: updated",
        "STYLEGUIDE_IMPACT: reviewed-no-change",
    )
    missing_phrases = [phrase for phrase in required_phrases if phrase not in guide]
    if missing_phrases:
        fail(
            "Canonieke styleguide mist verplichte onderdelen: "
            + ", ".join(missing_phrases)
        )

    for name in REQUIRED_TOKENS:
        if name not in tokens:
            fail(f"Verplicht design token ontbreekt in {TOKENS_PATH}: {name}")
        value = tokens[name]
        if name not in guide or value not in guide:
            fail(
                f"Styleguide is niet synchroon met design token {name}: {value}. "
                "Werk de styleguide en tokenbeslissing samen bij."
            )

    print("[OK] Canonieke Inhuis-styleguide bevat de verplichte structuur en actuele design tokens.")
    print("UI_STYLEGUIDE_DOCUMENT_GREEN")


def run_self_test() -> None:
    cases = [
        (
            "hard_requires_doc",
            ["frontend/src/pages/mobile.css"],
            "STYLEGUIDE_IMPACT: updated\nSTYLEGUIDE_REASON: Nieuwe kaartstijl.",
            True,
        ),
        (
            "hard_with_doc",
            ["frontend/src/pages/mobile.css", STYLEGUIDE_PATH],
            "STYLEGUIDE_IMPACT: updated\nSTYLEGUIDE_REASON: Nieuwe kaartstijl.",
            False,
        ),
        (
            "soft_requires_review",
            ["frontend/src/pages/Foo.jsx"],
            "",
            True,
        ),
        (
            "soft_reviewed_no_change",
            ["frontend/src/pages/Foo.jsx"],
            "STYLEGUIDE_IMPACT: reviewed-no-change\nSTYLEGUIDE_REASON: Alleen dataloading aangepast.",
            False,
        ),
        (
            "soft_doc_requires_updated_marker",
            ["frontend/src/pages/Foo.jsx", STYLEGUIDE_PATH],
            "STYLEGUIDE_IMPACT: reviewed-no-change\nSTYLEGUIDE_REASON: Document is wel aangepast.",
            True,
        ),
        (
            "backend_only",
            ["backend/app/main.py"],
            "",
            False,
        ),
    ]
    for name, paths, body, should_fail in cases:
        failed = bool(evaluate_change_policy(paths, body))
        if failed != should_fail:
            raise AssertionError(
                f"Self-test {name} verwacht fail={should_fail}, kreeg fail={failed}"
            )
    print("[OK] UI-styleguide policy self-tests geslaagd.")
    print("UI_STYLEGUIDE_POLICY_SELFTEST_GREEN")


def validate_pr_delta(base_sha: str, pr_body: str) -> None:
    git("cat-file", "-e", f"{base_sha}^{{commit}}")
    changed_paths = [
        line.strip()
        for line in git("diff", "--name-only", base_sha, "HEAD").splitlines()
        if line.strip()
    ]
    errors = evaluate_change_policy(changed_paths, pr_body)
    hard, ui_review = classify_paths(changed_paths)

    if hard:
        print("[INFO] Styleguide-dragende UI-paden:")
        for path in hard:
            print(f" - {path}")
    if ui_review:
        print("[INFO] Overige UI-paden met verplichte styleguide-review:")
        for path in ui_review:
            print(f" - {path}")

    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        fail("UI-styleguide governance is niet voldaan.")

    if not hard and not ui_review:
        print("[OK] Geen UI-bronwijzigingen die een styleguidebeslissing vereisen.")
    else:
        print("[OK] UI-styleguide impact is expliciet en consistent vastgelegd.")
    print("UI_STYLEGUIDE_CHANGE_POLICY_GREEN")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", choices=("pull_request", "push"), default="pull_request")
    parser.add_argument("--base-sha")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return

    validate_canonical_styleguide()

    if args.event == "pull_request":
        if not args.base_sha:
            fail("--base-sha is verplicht voor pull_request-validatie.")
        validate_pr_delta(args.base_sha, os.environ.get("PR_BODY", ""))
    else:
        print("[OK] Push naar main: canonieke styleguide/token-sync gevalideerd.")
        print("UI_STYLEGUIDE_CHANGE_POLICY_GREEN")


if __name__ == "__main__":
    main()
