from dataclasses import asdict, dataclass, field
from typing import Any

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

READ_ONLY_PROFILE_GUARDRAILS = {
    'status_determination': 'not_performed_by_profile',
    'database_mutation': False,
    'parser_mutation': False,
    'ocr_mutation': False,
    'filename_runtime_branching': False,
    'status_service': 'receipt_status_baseline_service_v4.py',
}
