"""Generic parse orchestration skeleton.

R9-35A introduces the package boundary only. Runtime parsing remains unchanged
until a dedicated migration step moves existing code into this module.
"""

from __future__ import annotations


def orchestration_boundary() -> str:
    return 'receipt_ingestion.pipeline'