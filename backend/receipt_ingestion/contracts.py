from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


ENGINE_VERSION = "receipt-ingestion-v01"


class QualityStatus(str, Enum):
    CONTROLLED = "controlled"
    REVIEW_NEEDED = "review_needed"
    FAILED = "failed"


@dataclass(frozen=True)
class ParserRow:
    product_name: str
    amount: float
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    line_no: Optional[int] = None
    source: str = "parser"
    confidence: Optional[float] = None
    warning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewSuggestion:
    product_name: str
    amount: float
    reason: str
    risk_level: str = "unknown"
    confidence: Optional[float] = None
    source: str = "diagnostic_suggestion"
    diagnostics_ref: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiagnosticBundle:
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.diagnostics)


@dataclass(frozen=True)
class ReceiptIngestionResult:
    receipt_id: str
    source_file: str
    parser_rows: List[ParserRow] = field(default_factory=list)
    review_suggestions: List[ReviewSuggestion] = field(default_factory=list)
    diagnostics: DiagnosticBundle = field(default_factory=DiagnosticBundle)
    quality_status: QualityStatus = QualityStatus.REVIEW_NEEDED
    engine_version: str = ENGINE_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "source_file": self.source_file,
            "parser_rows": [row.to_dict() for row in self.parser_rows],
            "review_suggestions": [suggestion.to_dict() for suggestion in self.review_suggestions],
            "diagnostics": self.diagnostics.to_dict(),
            "quality_status": self.quality_status.value,
            "engine_version": self.engine_version,
        }
