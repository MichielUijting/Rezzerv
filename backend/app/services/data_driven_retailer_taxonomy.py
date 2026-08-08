from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parents[1] / 'data' / 'product_taxonomy_seed.json'


def load_seed() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding='utf-8')) if DATA_PATH.exists() else {}


def taxonomy_rows() -> list[dict[str, Any]]:
    return list(load_seed().get('taxonomy') or [])


def retailer_rows(retailer_code: str) -> list[dict[str, Any]]:
    return [row for row in (load_seed().get('retailer_receipt_terms') or []) if str(row.get('retailer_code') or '').lower() == str(retailer_code or '').lower()]
