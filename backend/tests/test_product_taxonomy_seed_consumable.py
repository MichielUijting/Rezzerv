"""Read-only consumable inference from the existing product taxonomy seed."""
import pytest

from app.services.product_taxonomy_store import infer_food_consumable_from_seed


@pytest.mark.parametrize("article", [
    "Champignons", "Scharreleieren", "Rundergehakt 12%",
    "Olijfolie", "Komkommer", "Verse halfvolle melk",
])
def test_proven_food_is_consumable(article):
    assert infer_food_consumable_from_seed(article) is True


@pytest.mark.parametrize("article", [
    "Kwastenset", "Parkside kruislijnlaser", "Eiersnijder",
    "Onbekend huishoudartikel",
])
def test_non_food_or_unknown_is_not_forced_consumable(article):
    assert infer_food_consumable_from_seed(article) is None
