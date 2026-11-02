"""CBS reference validation keeps codes, classification and identity separate."""
import pytest

from app.services.cbs_classification_authority import (
    validate_cbs_code,
    validate_cbs_reference,
)

HASH = "a" * 64
ROWS = [
    {"cbs_code": "010000", "name_nl": "Voedingsmiddelen en alcoholvrije dranken",
     "level": 1, "parent_code": None},
    {"cbs_code": "011000", "name_nl": "Voedingsmiddelen",
     "level": 2, "parent_code": "010000"},
    {"cbs_code": "011400", "name_nl": "Melk, kaas en eieren",
     "level": 3, "parent_code": "011000"},
    {"cbs_code": "011420", "name_nl": "Halfvolle en magere melk",
     "level": 4, "parent_code": "011400"},
]


def test_preserves_six_character_codes_and_explicit_parentage():
    result = validate_cbs_reference(ROWS, reference_version="CBS-ECOICOPv2-2026",
                                    source_sha256=HASH)
    assert result[0]["cbs_code"] == "010000"
    assert result[-1]["cbs_code"] == "011420"
    assert result[-1]["parent_code"] == "011400"
    assert result[-1]["reference_version"] == "CBS-ECOICOPv2-2026"


@pytest.mark.parametrize("code", [11420, "11420", "01142A", "0114200", "-11420", "０１１４２０", None])
def test_rejects_invalid_or_numeric_codes(code):
    with pytest.raises(ValueError):
        validate_cbs_code(code)


def test_rejects_unverified_missing_parent():
    rows = [{**ROWS[3], "parent_code": "011410"}]
    with pytest.raises(ValueError, match="ontbrekende ouder"):
        validate_cbs_reference(rows, reference_version="2026", source_sha256=HASH)


def test_rejects_ambiguous_reference_structure():
    with pytest.raises(ValueError, match="Dubbele CBS-code"):
        validate_cbs_reference(ROWS + ROWS[:1], reference_version="2026", source_sha256=HASH)
    with pytest.raises(ValueError, match="niveau"):
        validate_cbs_reference([ROWS[0], {**ROWS[1], "level": 3}],
                               reference_version="2026", source_sha256=HASH)
    with pytest.raises(ValueError, match="checksum"):
        validate_cbs_reference(ROWS, reference_version="2026", source_sha256="invalid")


def test_category_cannot_be_promoted_to_product_equivalence():
    # Both halfvolle and magere melk can have CBS code 011420, yet different
    # physical products. The reference validator never creates product links.
    category = validate_cbs_reference(ROWS, reference_version="2026", source_sha256=HASH)[-1]
    assert "global_product_id" not in category
    assert "product_equivalence_id" not in category
    assert "gtin" not in category


def test_pinned_complete_official_reference_preserves_parentage_and_all_levels():
    import json
    from collections import Counter
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "app" / "data" / "cbs_ecoicop_v2_2026_reference.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    categories = data["categories"]
    assert data["source_sha256"] == "6871458274be87aa0126eab1bf334365502438f5e976845df8e5c28cdf95858f"
    assert data["reference_version"] == "CBS-ECOICOPv2-2026"
    assert len(categories) == len({row["cbs_code"] for row in categories}) == 440
    assert Counter(row["level"] for row in categories) == {1: 15, 2: 59, 3: 134, 4: 224, 5: 8}
    assert sum(row["lowest"] for row in categories) == 314
    parent_codes = {row["parent_code"] for row in categories if row["parent_code"] is not None}
    assert len(parent_codes) == 126
    by_code = {row["cbs_code"]: row for row in categories}
    assert by_code["011420"]["parent_code"] == "011400"
    assert by_code["011221"]["parent_code"] == "011220"
    for row in categories:
        assert len(row["cbs_code"]) == 6 and row["cbs_code"].isascii() and row["cbs_code"].isdecimal()
        parent = row["parent_code"]
        if parent is not None:
            assert parent in by_code
            gap = row["level"] - by_code[parent]["level"]
            assert gap == 1 or (gap == 2 and parent in {"023000", "054000", "101000", "105000", "112000", "133000", "139000"})
        assert row["lowest"] == (row["cbs_code"] not in parent_codes)

    # Source-level structure: 22 legitimate classes bypass an unused intermediate level.
    skips = [row for row in categories if row["parent_code"] and
             row["level"] - by_code[row["parent_code"]]["level"] == 2]
    assert len(skips) == 22
