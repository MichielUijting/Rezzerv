"""Canonical data catalog shared by Rezzerv L2/L3/L4 acceptance tests.

Test infrastructure only. The catalog gives stable product-recognizable fixture
identifiers and contract values without creating another database/schema authority.
Existing receipt acceptance data is referenced in place; synthetic fixtures contain
no personal or production household data.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO_ROOT / "quality" / "acceptance" / "canonical_scenario_catalog.json"

_REQUIRED_HOUSEHOLDS = {
    "locations_on": "acceptance-locations-on",
    "locations_off": "acceptance-locations-off",
    "isolation": "acceptance-isolation",
    "system_household": "0",
}
_REQUIRED_QUANTITIES = ("0.404", "1.224", "1.234567")
_REQUIRED_LAYERS = ("L2", "L3", "L4")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise AssertionError(f"Canonical fixture ontbreekt: {path.relative_to(REPO_ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_canonical_scenario_catalog() -> dict[str, Any]:
    data = _read_json(CATALOG_PATH)
    _require(isinstance(data, dict), "Canonical scenario catalog moet een JSON-object zijn")
    return data


def get_catalog_fixture(section: str, fixture_name: str) -> dict[str, Any]:
    catalog = load_canonical_scenario_catalog()
    fixtures = catalog.get(section)
    _require(isinstance(fixtures, dict), f"Catalogsectie ontbreekt: {section}")
    fixture = fixtures.get(fixture_name)
    _require(isinstance(fixture, dict), f"Catalogfixture ontbreekt: {section}.{fixture_name}")
    return fixture


def _as_decimal(value: Any, label: str) -> Decimal:
    text_value = str(value)
    try:
        return Decimal(text_value)
    except InvalidOperation as exc:
        raise AssertionError(f"{label} is geen geldige Decimal: {text_value}") from exc


def _receipt_by_id(baseline: list[dict[str, Any]], receipt_id: str) -> dict[str, Any]:
    matches = [row for row in baseline if str(row.get("receipt_id")) == receipt_id]
    _require(len(matches) == 1, f"Receipt selector {receipt_id} moet exact één match hebben")
    return matches[0]


def _receipt_lines(receipt: dict[str, Any], product_name: str) -> list[dict[str, Any]]:
    matches = [
        line for line in receipt.get("lines", [])
        if str(line.get("product_name") or "").strip() == product_name
    ]
    _require(matches, f"Receiptregel ontbreekt: {receipt.get('receipt_id')} / {product_name}")
    return matches


def _validate_receipts(catalog: dict[str, Any]) -> None:
    fixtures = catalog.get("receipt_fixtures")
    _require(isinstance(fixtures, dict) and len(fixtures) == 4, "Er moeten vier canonical receipt-fixtures zijn")

    sources = {str(item.get("source")) for item in fixtures.values()}
    _require(len(sources) == 1, "Canonical receipt-fixtures moeten dezelfde acceptance baseline hergebruiken")
    source_path = REPO_ROOT / sources.pop()
    baseline = _read_json(source_path)
    _require(isinstance(baseline, list), "Receipt acceptance baseline moet een JSON-lijst zijn")

    normal = fixtures["normal_physical"]
    normal_receipt = _receipt_by_id(baseline, str(normal["selector"]["receipt_id"]))
    _require(str(normal_receipt.get("currency")) == "EUR", "Normale receipt moet EUR gebruiken")
    _require(int(normal_receipt.get("article_count") or 0) == 4, "Normale receipt moet vier artikelen bevatten")
    _require(
        not any("koopzegel" in str(line.get("product_name") or "").lower() for line in normal_receipt.get("lines", [])),
        "Normale fysieke receipt mag geen koopzegelregel bevatten",
    )

    loyalty = fixtures["non_physical_loyalty"]
    loyalty_receipt = _receipt_by_id(baseline, str(loyalty["selector"]["receipt_id"]))
    loyalty_lines = _receipt_lines(loyalty_receipt, str(loyalty["selector"]["product_name"]))
    _require(
        any(_as_decimal(line.get("quantity"), "Koopzegels quantity") == Decimal("8") for line in loyalty_lines),
        "Koopzegels fixture moet de bestaande quantity 8 terugvinden",
    )
    _require(loyalty["contract"]["inventory_effect"] == "none", "Niet-fysieke fixture mag geen voorraadmutatie verwachten")

    weighted = fixtures["weighted_quantity"]
    weighted_receipt = _receipt_by_id(baseline, str(weighted["selector"]["receipt_id"]))
    weighted_lines = _receipt_lines(weighted_receipt, str(weighted["selector"]["product_name"]))
    expected_quantity = _as_decimal(weighted["contract"]["quantity"], "Weighted quantity contract")
    _require(
        any(_as_decimal(line.get("quantity"), "Weighted receipt quantity") == expected_quantity for line in weighted_lines),
        "Weighted fixture moet quantity 0.404 exact in de receipt baseline terugvinden",
    )
    _require(weighted["contract"]["must_remain_exact"] is True, "Weighted quantity moet exact blijven")

    uncertain = fixtures["uncertain_match"]
    uncertain_receipt = _receipt_by_id(baseline, str(uncertain["selector"]["receipt_id"]))
    uncertain_lines = _receipt_lines(uncertain_receipt, str(uncertain["selector"]["product_name"]))
    _require(
        any("onzeker" in str(line.get("notes") or "").lower() for line in uncertain_lines),
        "Onzekere-matchfixture moet aantoonbaar uit een onzekere bronregel komen",
    )
    _require(uncertain["contract"]["review_required"] is True, "Onzekere match moet review vereisen")


def _validate_articles(catalog: dict[str, Any]) -> None:
    fixtures = catalog.get("article_fixtures")
    _require(isinstance(fixtures, dict) and len(fixtures) == 4, "Er moeten vier canonical article-fixtures zijn")
    ids = [str(item.get("id") or "") for item in fixtures.values()]
    _require(all(ids) and len(ids) == len(set(ids)), "Canonical article fixture-IDs moeten uniek en gevuld zijn")
    _require(fixtures["existing_household_article"]["state"] == "existing", "Existing household article fixture is ongeldig")
    _require(fixtures["new_household_article"]["state"] == "new", "New household article fixture is ongeldig")
    _require(fixtures["unclassified_article"]["article_group"] == "Niet ingedeeld", "Niet ingedeeld contract ontbreekt")

    day = fixtures["day_article"]
    _require(day["consumable"] is True, "Dagartikel moet consumable zijn")
    _require(day["auto_consume_mode"] == "purchased_quantity", "Dagartikel moet purchased_quantity-contract gebruiken")
    existing = _as_decimal(day["existing_quantity"], "day existing_quantity")
    purchased = _as_decimal(day["purchased_quantity"], "day purchased_quantity")
    expected = _as_decimal(day["expected_final_quantity"], "day expected_final_quantity")
    _require(existing + purchased - purchased == expected, "Dagartikel eindvoorraadcontract is niet deterministisch")


def _validate_numeric_contracts(catalog: dict[str, Any]) -> None:
    quantity = catalog.get("quantity_contract")
    _require(isinstance(quantity, dict), "quantity_contract ontbreekt")
    values = tuple(str(item) for item in quantity.get("values", []))
    _require(values == _REQUIRED_QUANTITIES, "Quantity contract moet exact 0.404, 1.224 en 1.234567 bevatten")
    _require(quantity.get("generic_decimal_limit") is None, "Quantity mag geen generieke decimalenlimiet hebben")
    _require(quantity.get("must_round") is False, "Quantity mag niet generiek worden afgerond")
    for value in values:
        _require(str(_as_decimal(value, "quantity")) == value, f"Quantity moet tekstueel exact roundtrippen: {value}")

    financial = catalog.get("financial_contract")
    _require(isinstance(financial, dict), "financial_contract ontbreekt")
    _require(financial.get("currency") == "EUR", "Financial fixture gebruikt EUR")
    _require(int(financial.get("scale")) == 2, "Financiële fixture moet schaal 2 hebben")
    for value in financial.get("values", []):
        value_text = str(value)
        parsed = _as_decimal(value_text, "financial value")
        _require(abs(parsed.as_tuple().exponent) == 2, f"Financiële fixture moet twee decimalen hebben: {value_text}")
    _require(financial.get("rounding") == "financial_only", "Afronding moet uitsluitend financieel zijn")


def _validate_almost_out(catalog: dict[str, Any]) -> None:
    cases = catalog.get("almost_out_cases")
    _require(isinstance(cases, dict), "almost_out_cases ontbreekt")
    minimum = _as_decimal(cases.get("min_stock"), "min_stock")
    expected = {
        "above": (Decimal("6"), False),
        "equal": (Decimal("5"), True),
        "below": (Decimal("4"), True),
        "zero": (Decimal("0"), True),
    }
    for name, (quantity, almost_out) in expected.items():
        row = cases.get(name)
        _require(isinstance(row, dict), f"Almost-out fixture ontbreekt: {name}")
        _require(_as_decimal(row.get("quantity"), f"almost_out {name}") == quantity, f"Almost-out quantity wijkt af: {name}")
        _require(bool(row.get("expected_almost_out")) is almost_out, f"Almost-out verwachting wijkt af: {name}")
    _require(
        expected["above"][0] > minimum and expected["equal"][0] == minimum and expected["below"][0] < minimum,
        "Almost-out grensgevallen zijn niet logisch geordend",
    )


def _validate_legacy(catalog: dict[str, Any]) -> None:
    legacy = catalog.get("legacy_adoption_fixture")
    _require(isinstance(legacy, dict), "legacy_adoption_fixture ontbreekt")
    _require(legacy.get("contains_personal_data") is False, "Legacy fixture mag geen persoonsgegevens bevatten")
    _require(legacy.get("source_kind") == "synthetic_legacy_sqlite", "Legacy fixture moet expliciet synthetisch zijn")
    rows = legacy.get("rows")
    _require(isinstance(rows, list) and len(rows) == 3, "Legacy fixture moet drie precisierijen bevatten")
    ids = set()
    for row in rows:
        fixture_id = str(row.get("fixture_id") or "")
        _require(fixture_id and fixture_id not in ids, "Legacy fixture IDs moeten uniek zijn")
        ids.add(fixture_id)
        _require(
            _as_decimal(row.get("quantity"), fixture_id) == _as_decimal(row.get("expected_quantity"), fixture_id),
            f"Legacy quantity moet exact behouden blijven: {fixture_id}",
        )


def validate_canonical_scenario_catalog() -> dict[str, Any]:
    catalog = load_canonical_scenario_catalog()
    _require(int(catalog.get("catalog_version") or 0) == 1, "Onbekende canonical catalog-versie")
    _require(catalog.get("household_contexts") == _REQUIRED_HOUSEHOLDS, "Household contexts wijken af van Fase-1 foundation")

    cross_layer = catalog.get("cross_layer_contract")
    _require(isinstance(cross_layer, dict), "cross_layer_contract ontbreekt")
    _require(tuple(cross_layer.get("consumers", [])) == _REQUIRED_LAYERS, "Catalog moet L2/L3/L4 als consumers hebben")
    _require(cross_layer.get("identifiers_are_stable") is True, "Canonical fixture-IDs moeten stabiel zijn")

    _validate_receipts(catalog)
    _validate_articles(catalog)
    _validate_numeric_contracts(catalog)
    _validate_almost_out(catalog)
    _validate_legacy(catalog)

    raw = CATALOG_PATH.read_bytes()
    return {
        "catalog_version": catalog["catalog_version"],
        "catalog_sha256": hashlib.sha256(raw).hexdigest(),
        "household_context_count": len(catalog["household_contexts"]),
        "receipt_fixture_count": len(catalog["receipt_fixtures"]),
        "article_fixture_count": len(catalog["article_fixtures"]),
        "quantity_case_count": len(catalog["quantity_contract"]["values"]),
        "financial_case_count": len(catalog["financial_contract"]["values"]),
        "almost_out_case_count": len(catalog["almost_out_cases"]) - 1,
        "legacy_row_count": len(catalog["legacy_adoption_fixture"]["rows"]),
        "consumers": list(cross_layer["consumers"]),
    }


def main() -> int:
    result = validate_canonical_scenario_catalog()
    print("REZZERV_CANONICAL_SCENARIO_CATALOG")
    for key in (
        "catalog_version",
        "catalog_sha256",
        "household_context_count",
        "receipt_fixture_count",
        "article_fixture_count",
        "quantity_case_count",
        "financial_case_count",
        "almost_out_case_count",
        "legacy_row_count",
    ):
        print(f"{key}={result[key]}")
    print("consumers=" + ",".join(result["consumers"]))
    print("CANONICAL_SCENARIO_CATALOG_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
