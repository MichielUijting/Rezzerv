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
