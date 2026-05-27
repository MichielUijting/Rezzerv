from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ProfileDetection:
    chain_id: str
    display_name: str
    confidence: str
    score: int
    evidence: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProfileLineClassification:
    index: int
    text: str
    section: str
    line_class: str
    reason: str
    amount: str | None = None
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProfileDiagnostics:
    profile: str
    detection: ProfileDetection
    line_classifications: list[ProfileLineClassification]
    summary: dict[str, Any]
    guardrails: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            'profile': self.profile,
            'detection': self.detection.to_dict(),
            'line_classifications': [item.to_dict() for item in self.line_classifications],
            'summary': self.summary,
            'guardrails': self.guardrails,
        }


@dataclass(frozen=True)
class ProfileParseContext:
    """Read-only context handed from the generic pipeline to a store profile.

    Profiles may interpret text lines according to store semantics, but they may
    not mutate the database, trigger OCR, or determine functional receipt status.
    """

    filename: str
    mime_type: str | None = None
    source_kind: str | None = None
    household_id: str | None = None
    diagnostics_enabled: bool = True


@dataclass(frozen=True)
class ProfileHeaderResult:
    store_name: str | None = None
    store_branch: str | None = None
    purchase_at: str | None = None
    total_amount: Any | None = None
    discount_total: Any | None = None
    currency: str = 'EUR'
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProfileArticleResult:
    lines: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ReceiptStoreProfile(Protocol):
    """Interface for store-specific receipt interpretation.

    Generic orchestration may detect/select a profile and pass normalized text to
    it. All store semantics, such as AH total anchors or Jumbo article formats,
    belong behind this interface instead of in generic service files.
    """

    chain_id: str
    display_name: str

    def detect(self, text_lines: list[str], context: ProfileParseContext) -> ProfileDetection:
        ...

    def parse_header(self, text_lines: list[str], context: ProfileParseContext) -> ProfileHeaderResult:
        ...

    def parse_articles(self, text_lines: list[str], context: ProfileParseContext) -> ProfileArticleResult:
        ...


READ_ONLY_PROFILE_GUARDRAILS = {
    'status_determination': 'not_performed_by_profile',
    'database_mutation': False,
    'parser_mutation': False,
    'ocr_mutation': False,
    'filename_runtime_branching': False,
    'status_service': 'receipt_status_baseline_service_v4.py',
}
