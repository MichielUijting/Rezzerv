import ast
import sqlite3
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


class LiveHouseholdArticleIdentityAdoptionTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(
            """
            CREATE TABLE household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                naam TEXT NOT NULL,
                updated_at TEXT
            );
            CREATE TABLE inventory (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                household_article_id TEXT
            );
            CREATE TABLE inventory_events (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                article_id TEXT NOT NULL,
                household_article_id TEXT NOT NULL
            );
            """
        )
        self.synthetic_id = "live::volle-melk"
        self.conn.execute(
            "INSERT INTO household_articles (id, household_id, naam) VALUES (?, ?, ?)",
            (self.synthetic_id, "house-a", "Volle melk"),
        )
        self.conn.execute(
            "INSERT INTO inventory (id, household_id, household_article_id) VALUES (?, ?, ?)",
            ("inv-a", "house-a", self.synthetic_id),
        )
        self.conn.execute(
            "INSERT INTO inventory (id, household_id, household_article_id) VALUES (?, ?, ?)",
            ("inv-b", "house-b", self.synthetic_id),
        )
        self.conn.execute(
            "INSERT INTO inventory_events (id, household_id, article_id, household_article_id) VALUES (?, ?, ?, ?)",
            ("evt-a", "house-a", self.synthetic_id, self.synthetic_id),
        )
        self.conn.execute(
            "INSERT INTO inventory_events (id, household_id, article_id, household_article_id) VALUES (?, ?, ?, ?)",
            ("evt-b", "house-b", self.synthetic_id, self.synthetic_id),
        )

    def tearDown(self):
        self.conn.close()

    def test_live_identity_is_rekeyed_and_direct_consumers_follow(self):
        adopt = load_adoption_helper()
        canonical_id = adopt(self.conn, "house-a", self.synthetic_id)

        self.assertFalse(canonical_id.startswith("live::"))
        self.assertEqual(str(uuid.UUID(canonical_id)), canonical_id)
        article = self.conn.execute(
            "SELECT id FROM household_articles WHERE household_id = ? AND naam = ?",
            ("house-a", "Volle melk"),
        ).fetchone()
        self.assertEqual(article[0], canonical_id)
        self.assertEqual(
            self.conn.execute("SELECT household_article_id FROM inventory WHERE id = 'inv-a'").fetchone()[0],
            canonical_id,
        )
        self.assertEqual(
            self.conn.execute("SELECT article_id, household_article_id FROM inventory_events WHERE id = 'evt-a'").fetchone(),
            (canonical_id, canonical_id),
        )
        self.assertEqual(
            self.conn.execute("SELECT household_article_id FROM inventory WHERE id = 'inv-b'").fetchone()[0],
            self.synthetic_id,
        )
        self.assertEqual(
            self.conn.execute("SELECT article_id, household_article_id FROM inventory_events WHERE id = 'evt-b'").fetchone(),
            (self.synthetic_id, self.synthetic_id),
        )

    def test_non_live_identity_is_unchanged(self):
        adopt = load_adoption_helper()
        canonical_id = str(uuid.uuid4())
        self.assertEqual(adopt(self.conn, "house-a", canonical_id), canonical_id)

    def test_ensure_boundary_invokes_adoption_before_return(self):
        source = MAIN_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        ensure_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "ensure_household_article"
        )
        ensure_source = ast.get_source_segment(source, ensure_node) or ""
        self.assertIn('startswith("live::")', ensure_source)
        self.assertIn("_adopt_synthetic_household_article_identity", ensure_source)


if __name__ == "__main__":
    unittest.main()
