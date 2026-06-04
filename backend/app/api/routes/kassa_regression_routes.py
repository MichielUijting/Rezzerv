from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter

from app.services.receipt_baseline_service import load_receipt_baseline, run_receipt_parsing_baseline_suite

router = APIRouter()

REQUIRED_CHAINS = {
    "Albert Heijn": {"Albert Heijn", "AH"},
    "ALDI": {"ALDI", "Aldi"},
    "Jumbo": {"Jumbo"},
    "PLUS": {"PLUS", "Plus"},
    "Lidl": {"Lidl"},
}


def _canonical_chain(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    for canonical, aliases in REQUIRED_CHAINS.items():
        if normalized in {alias.lower() for alias in aliases}:
            return canonical
    if "albert heijn" in normalized or normalized == "ah":
        return "Albert Heijn"
    if "aldi" in normalized:
        return "ALDI"
    if "jumbo" in normalized:
        return "Jumbo"
    if "plus" in normalized:
        return "PLUS"
    if "lidl" in normalized:
        return "Lidl"
    return None


def _baseline_chain_by_receipt_id() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for case in load_receipt_baseline():
        receipt_id = str(case.get("receipt_id") or "")
        chain = _canonical_chain(str(case.get("store_chain") or case.get("store_name") or ""))
        if receipt_id and chain:
            mapping[receipt_id] = chain
    return mapping


def _result_receipt_id(result: dict[str, Any]) -> str:
    details = result.get("details") if isinstance(result.get("details"), dict) else {}
    return str(details.get("receipt_id") or result.get("name") or "")


@router.post("/api/admin/kassa-regression/run")
def run_kassa_receipt_regression() -> dict[str, Any]:
    baseline_chain_by_id = _baseline_chain_by_receipt_id()
    raw_results = run_receipt_parsing_baseline_suite("raw")

    results_by_chain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in raw_results:
        receipt_id = _result_receipt_id(result)
        chain = baseline_chain_by_id.get(receipt_id)
        if not chain:
            continue
        if chain not in REQUIRED_CHAINS:
            continue
        results_by_chain[chain].append(result)

    chains: list[dict[str, Any]] = []
    all_passed = True

    for chain in REQUIRED_CHAINS.keys():
        chain_results = results_by_chain.get(chain, [])
        passed_count = sum(1 for result in chain_results if result.get("status") == "passed")
        failed_results = [result for result in chain_results if result.get("status") != "passed"]
        missing = not chain_results
        status = "missing" if missing else ("failed" if failed_results else "passed")
        if status != "passed":
            all_passed = False
        chains.append({
            "chain": chain,
            "status": status,
            "receipt_count": len(chain_results),
            "passed_count": passed_count,
            "failed_count": len(failed_results),
            "failures": [
                {
                    "receipt_id": _result_receipt_id(result),
                    "error": result.get("error"),
                    "details": result.get("details"),
                }
                for result in failed_results
            ],
        })

    return {
        "test_type": "kassa_receipt_regression",
        "status": "passed" if all_passed else "failed",
        "ran_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "required_chains": list(REQUIRED_CHAINS.keys()),
        "chains": chains,
        "summary": {
            "chain_count": len(chains),
            "passed_chain_count": sum(1 for item in chains if item["status"] == "passed"),
            "failed_chain_count": sum(1 for item in chains if item["status"] == "failed"),
            "missing_chain_count": sum(1 for item in chains if item["status"] == "missing"),
        },
    }
