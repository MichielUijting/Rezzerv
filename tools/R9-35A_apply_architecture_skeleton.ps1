$ErrorActionPreference = 'Stop'

function Write-Utf8File([string]$Path, [string]$Content) {
  $dir = Split-Path -Parent $Path
  if ($dir -and -not (Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
  }
  [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$root = Join-Path $repoRoot 'backend\app\receipt_ingestion'

$files = @{
  'pipeline\__init__.py' = '"""Generic receipt-ingestion pipeline package."""' + "`n"
  'pipeline\parse_orchestrator.py' = @'
"""Generic parse orchestration skeleton.

R9-35A introduces the package boundary only. Runtime parsing remains unchanged
until a dedicated migration step moves existing code into this module.
"""

from __future__ import annotations


def orchestration_boundary() -> str:
    return 'receipt_ingestion.pipeline'
'@
  'pipeline\source_router.py' = @'
"""Source-kind routing skeleton for receipt ingestion."""

from __future__ import annotations


def routing_boundary() -> str:
    return 'receipt_ingestion.pipeline.source_router'
'@
  'pipeline\result_model.py' = @'
"""Result-model boundary for future ReceiptParseResult migration."""

from __future__ import annotations
'@
  'pipeline\receipt_context.py' = @'
"""Read-only receipt parse context boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReceiptSourceContext:
    filename: str
    mime_type: str | None = None
    source_kind: str | None = None
'@
  'extraction\__init__.py' = '"""Technical extraction package: OCR, PDF, email, html and text."""' + "`n"
  'extraction\image_ocr.py' = @'
"""Image OCR boundary.

No store-specific interpretation belongs here.
"""

from __future__ import annotations
'@
  'extraction\pdf_text.py' = @'
"""PDF text extraction boundary.

No article or total interpretation belongs here.
"""

from __future__ import annotations
'@
  'extraction\email_text.py' = @'
"""Email text extraction boundary."""

from __future__ import annotations
'@
  'extraction\html_text.py' = @'
"""HTML/text extraction boundary."""

from __future__ import annotations
'@
  'core\__init__.py' = '"""Generic receipt parsing primitives."""' + "`n"
  'core\README.md' = @'
# Receipt ingestion core

This package is reserved for generic parsing primitives only:

- amount parsing
- text normalization
- generic candidate builders
- generic diagnostics
- fingerprints

Store-specific rules are not allowed here.
'@
  'profiles\registry.py' = @'
"""Receipt store profile registry.

R9-35A creates the registry boundary. Existing runtime detection remains in place
until the next migration steps move profiles behind this registry.
"""

from __future__ import annotations

from typing import Iterable

from app.receipt_ingestion.profiles.base import ReceiptStoreProfile


_REGISTERED_PROFILES: list[ReceiptStoreProfile] = []


def register_profile(profile: ReceiptStoreProfile) -> None:
    if profile not in _REGISTERED_PROFILES:
        _REGISTERED_PROFILES.append(profile)


def iter_profiles() -> Iterable[ReceiptStoreProfile]:
    return tuple(_REGISTERED_PROFILES)
'@
  'profiles\ah\__init__.py' = '"""Albert Heijn receipt profile package."""' + "`n"
  'profiles\ah\profile.py' = @'
"""Albert Heijn profile skeleton.

Actual AH runtime logic remains in existing modules until R9-35B/R9-35C.
"""

from __future__ import annotations

CHAIN_ID = 'ah'
DISPLAY_NAME = 'Albert Heijn'
'@
  'profiles\ah\detect.py' = @'
"""Albert Heijn detection boundary."""

from __future__ import annotations
'@
  'profiles\ah\header.py' = @'
"""Albert Heijn header and branch extraction boundary."""

from __future__ import annotations
'@
  'profiles\ah\totals.py' = @'
"""Albert Heijn total extraction boundary.

Rules such as exact TE BETALEN/TOTAAL anchors belong here after R9-35B.
"""

from __future__ import annotations
'@
  'profiles\ah\articles.py' = @'
"""Albert Heijn article extraction boundary."""

from __future__ import annotations
'@
  'profiles\ah\filters.py' = @'
"""Albert Heijn non-product filter boundary."""

from __future__ import annotations
'@
  'profiles\ah\diagnostics.py' = @'
"""Albert Heijn profile diagnostics boundary."""

from __future__ import annotations
'@
}

foreach ($relative in $files.Keys) {
  $path = Join-Path $root $relative
  if (-not (Test-Path $path)) {
    Write-Utf8File $path $files[$relative]
  }
}

python -m py_compile (Join-Path $root 'profiles\base.py')
python -m py_compile (Join-Path $root 'profiles\registry.py')
python -m py_compile (Join-Path $root 'pipeline\parse_orchestrator.py')
python -m py_compile (Join-Path $root 'pipeline\source_router.py')
python -m py_compile (Join-Path $root 'pipeline\result_model.py')
python -m py_compile (Join-Path $root 'pipeline\receipt_context.py')
python -m py_compile (Join-Path $root 'profiles\ah\profile.py')

Write-Host 'R9-35A skeleton applied:'
Write-Host '- pipeline package added'
Write-Host '- extraction package added'
Write-Host '- core package added'
Write-Host '- profiles registry added'
Write-Host '- profiles/ah package skeleton added'
Write-Host '- no runtime parser behavior changed'

git --no-pager diff -- backend/app/receipt_ingestion tools/R9-35A_apply_architecture_skeleton.ps1

git add backend/app/receipt_ingestion tools/R9-35A_apply_architecture_skeleton.ps1
git commit -m 'R9-35A add receipt ingestion architecture skeleton'
git push

Write-Host 'R9-35A toegepast en gepusht.'
