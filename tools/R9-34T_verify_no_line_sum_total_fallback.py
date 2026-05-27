from pathlib import Path

text = Path("backend/app/services/receipt_service.py").read_text(encoding="utf-8-sig")

for forbidden in [
    "candidate_total = line_sum +",
    "total_amount = candidate_total.quantize",
    "total_amount = line_sum.quantize",
]:
    if forbidden in text:
        raise SystemExit(f"R9-34T verification failed: forbidden fallback remains: {forbidden}")

print("R9-34T verification passed: line-sum total_amount fallback removed")
