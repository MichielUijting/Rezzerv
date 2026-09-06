import ast
import unittest
import uuid
from pathlib import Path


MAIN_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"


def load_adoption_helper():
    source = MAIN_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_adopt_synthetic_household_article_identity"
    )
    module = ast.Module(body=[helper_node], type_ignores=[])
    namespace = {"uuid": uuid, "text": lambda statement: statement}
    exec(compile(module, str(MAIN_PATH), "exec"), namespace)
    return namespace["_adopt_synthetic_household_article_identity"]


class RecordingConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), dict(params)))
        return None


class LiveHouseholdArticleIdentityAdoptionTest(unittest.TestCase):
    def test_live_identity_is_rekeyed_and_direct_consumers_follow(self):
        adopt = load_adoption_helper()
        conn = RecordingConnection()

        canonical_id = adopt(conn, "house-a", "live::volle-melk")

        self.assertFalse(canonical_id.startswith("live::"))
        self.assertEqual(str(uuid.UUID(canonical_id)), canonical_id)
        self.assertEqual(len(conn.calls), 3)

        article_sql, article_params = conn.calls[0]
        inventory_sql, inventory_params = conn.calls[1]
        event_sql, event_params = conn.calls[2]

        self.assertIn("UPDATE household_articles", article_sql)
        self.assertIn("WHERE household_id = :household_id", article_sql)
        self.assertIn("id = :synthetic_article_id", article_sql)

        self.assertIn("UPDATE inventory", inventory_sql)
        self.assertIn("WHERE household_id = :household_id", inventory_sql)
        self.assertIn("household_article_id = :synthetic_article_id", inventory_sql)

        self.assertIn("UPDATE inventory_events", event_sql)
        self.assertIn("article_id = :synthetic_article_id", event_sql)
        self.assertIn("household_article_id = :synthetic_article_id", event_sql)
        self.assertIn("WHERE household_id = :household_id", event_sql)

        for params in (article_params, inventory_params, event_params):
            self.assertEqual(params["household_id"], "house-a")
            self.assertEqual(params["synthetic_article_id"], "live::volle-melk")
            self.assertEqual(params["canonical_article_id"], canonical_id)

    def test_non_live_identity_is_unchanged_without_writes(self):
        adopt = load_adoption_helper()
        conn = RecordingConnection()
        canonical_id = str(uuid.uuid4())

        self.assertEqual(adopt(conn, "house-a", canonical_id), canonical_id)
        self.assertEqual(conn.calls, [])

    def test_ensure_boundary_adopts_before_linking_and_returning(self):
        source = MAIN_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        ensure_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "ensure_household_article"
        )
        ensure_source = ast.get_source_segment(source, ensure_node) or ""

        adoption_pos = ensure_source.index("_adopt_synthetic_household_article_identity")
        link_pos = ensure_source.index("ensure_household_article_global_product_link", adoption_pos)
        return_pos = ensure_source.index("return str(article_id)", link_pos)
        self.assertLess(adoption_pos, link_pos)
        self.assertLess(link_pos, return_pos)

    def test_product_enrichment_ordering_is_postgresql_native(self):
        source = MAIN_PATH.read_text(encoding="utf-8")
        self.assertNotIn("datetime(COALESCE(last_lookup_at, fetched_at))", source)
        self.assertGreaterEqual(source.count("COALESCE(last_lookup_at, fetched_at) DESC"), 4)


if __name__ == "__main__":
    unittest.main()
