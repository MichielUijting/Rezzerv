"""Read-only equivalence review contract: no linking, household access or writes."""
import unittest

from app.services.synonym_equivalence_review import review_pair


def item(name, size="1", unit="l", brand=""):
    return {"name": name, "variant": "", "size_value": size, "size_unit": unit, "brand": brand}


class SynonymEquivalenceReviewTest(unittest.TestCase):
    def test_equivalent_across_retailers_is_strong_but_not_auto_linked(self):
        result = review_pair(item("Halfvolle melk", brand="AH"),
                             item("Halfvolle melk", brand="Jumbo"))
        self.assertEqual(result["review_level"], "strong")
        self.assertNotIn("link", result)

    def test_milk_fat_contrast_requires_review(self):
        result = review_pair(item("Halfvolle melk"), item("Volle melk"))
        self.assertEqual(result["review_level"], "check")
        self.assertIn("melkvet", result["review_reason"])

    def test_functionally_distinct_types_require_review(self):
        for left, right in (("Halfvolle mayonaise", "Houdbare halfvolle melk"),
                            ("Magere kwark", "Magere yoghurt"),
                            ("Noten", "Kruidnoten")):
            with self.subTest(left=left, right=right):
                self.assertEqual(review_pair(item(left), item(right))["review_level"], "check")

    def test_different_pack_size_is_reviewable_not_dismissed(self):
        result = review_pair(item("Burrata", "125", "g"), item("Burrata", "150", "g"))
        self.assertEqual(result["review_level"], "check")
        self.assertIn("Verpakkingsinhoud", result["review_reason"])

    def test_unknown_amount_is_not_assumed_equal(self):
        result = review_pair(item("Halfvolle melk", "", ""), item("Halfvolle melk", "", ""))
        self.assertEqual(result["review_level"], "possible")

    def test_preparations_and_dietary_variants_are_explicit(self):
        for left, right, reason in (
            ("Roomboter ongezouten", "Roomboter gezouten", "zout"),
            ("Melk lactosevrij", "Melk met lactose", "lactose"),
            ("Vla vanille", "Vla chocolade", "smaak"),
        ):
            with self.subTest(left=left):
                result = review_pair(item(left), item(right))
                self.assertEqual(result["review_level"], "check")
                self.assertIn(reason, result["review_reason"])

    def test_different_brand_alone_is_never_conflict(self):
        result = review_pair(item("Kristalsuiker", "1", "kg", "AH"),
                             item("Kristalsuiker", "1000", "g", "Lidl"))
        self.assertEqual(result["review_level"], "strong")


if __name__ == "__main__":
    unittest.main()
