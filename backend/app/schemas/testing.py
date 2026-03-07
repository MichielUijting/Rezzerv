from pydantic import BaseModel
from typing import Optional, List


class TestStartResponse(BaseModel):
    started: bool
    test_type: str
    status: str


class TestStatusResponse(BaseModel):
    test_type: Optional[str] = None
    status: str = "idle"
    last_run_at: Optional[str] = None
    passed_count: int = 0
    failed_count: int = 0
    last_error: Optional[str] = None


class TestScenarioResult(BaseModel):
    name: str
    status: str
    error: Optional[str] = None


class TestReportResponse(BaseModel):
    test_type: Optional[str] = None
    last_run_at: Optional[str] = None
    results: List[TestScenarioResult] = []


class TestCompleteRequest(BaseModel):
    test_type: str
    results: List[TestScenarioResult]
