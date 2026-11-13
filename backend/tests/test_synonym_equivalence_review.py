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

    def test_retailer_prefixes_are_not_part_of_product_identity(self):
        result = review_pair(item("AH Halfvolle melk", brand="Albert Heijn"),
                             item("Jumbo Halfvolle melk", brand="JUMBO"))
        self.assertEqual(result["review_level"], "strong")

    def test_milk_fat_contrast_requires_review(self):
        result = review_pair(item("Halfvolle melk"), item("Volle melk"))
        self.assertEqual(result["review_level"], "check")
        self.assertIn("melkvet", result["review_reason"])

    def test_functionally_distinct_types_require_review(self):
        for left, right in (("Halfvolle mayonaise", "Houdbare halfvolle melk"),
                            ("Zaanse halfvolle mayo", "AH Houdbare halfvolle melk"),
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


    def test_approved_fresh_courgette_family_is_narrow(self):
        from app.services.synonym_product_family_rules import approved_family
        for name in ("Courgette", "Courgettes", "Biologische courgette",
                     "Gele courgette", "Groene bio courgette"):
            self.assertEqual(approved_family(item(name)), "verse_courgette_v1")
        for name in ("Courgette diepvries", "Babyvoeding courgette",
                     "Courgette soep", "Courgette met kruiden", "Groene gele courgette",
                     "2 courgettes", "Courgette mix"):
            self.assertIsNone(approved_family(item(name)))

    def test_exact_units_and_invalid_sizes(self):
        from app.services.synonym_product_family_rules import normalized_package_quantity as q
        self.assertEqual(q(item("X", "1", "kg")), q(item("X", "1000", "g")))
        self.assertEqual(q(item("X", "1", "l")), q(item("X", "1000", "ml")))
        self.assertEqual(q(item("X", "2", "stuks")), q(item("X", "2", "stuk")))
        self.assertNotEqual(q(item("X", "1", "kg")), q(item("X", "1", "l")))
        for value, unit in (("NaN","kg"), ("Infinity","kg"), ("0","g"),
                            ("-1","ml"), ("x","kg"), ("1","pak"),
                            ("1","gr"), ("1","")):
            self.assertIsNone(q(item("X", value, unit)))

    def test_fresh_courgette_and_prepared_product_contrast(self):
        from app.services.synonym_equivalence_review import proven_semantic_conflicts
        for label in ("Olvarit 8+ Maanden Courgette", "Diepvries courgette",
                      "Courgette babyvoeding", "Courgettesoep"):
            with self.subTest(label=label):
                reasons = proven_semantic_conflicts(item("AH Courgette"), item(label))
                self.assertTrue(reasons)
                self.assertIn("babyproduct", reasons[0])
        self.assertEqual(proven_semantic_conflicts(
            item("AH Courgette"), item("Biologische gele courgette")), [])

    def test_rational_package_factor_only_for_approved_family(self):
        from app.services.synonym_product_family_rules import verified_package_ratio as r
        a, b = item("Courgette", "250", "g"), item("Biologische courgette", "500", "g")
        self.assertEqual(r(a,b)["left_to_right"], "1/2")
        self.assertEqual(r(b,a)["left_to_right"], "2")
        self.assertEqual(r(item("Groene courgette","1","kg"),
                           item("Gele courgette","1000","g"))["left_to_right"], "1")
        self.assertEqual(r(item("Groene courgette","2","stuks"),
                           item("Gele courgette","3","stuks"))["left_to_right"], "2/3")
        self.assertIsNone(r(item("Courgette","1","stuk"), item("Courgette","500","g")))
        self.assertIsNone(r(item("Courgette","1","l"), item("Courgette","1","kg")))
        self.assertIsNone(r(item("Babyvoeding courgette","250","g"), b))
        self.assertIsNone(r(item("Courgette","1","g"), item("Courgette","10000","kg")))


if __name__ == "__main__":
    unittest.main()
