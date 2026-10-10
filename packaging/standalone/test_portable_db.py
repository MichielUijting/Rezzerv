"""Offline unit tests for portable bootstrap; no real PostgreSQL needed."""
from pathlib import Path
import importlib.util
import tempfile
import unittest

MODULE = Path(__file__).with_name("portable_db.py")
spec = importlib.util.spec_from_file_location("portable_db", MODULE)
db = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db)


class PortableDatabaseTests(unittest.TestCase):
    def test_random_credentials_persist(self):
        with tempfile.TemporaryDirectory() as root:
            data = Path(root)
            first = db.credentials(data)
            self.assertEqual(first, db.credentials(data))
            self.assertEqual(first[0], "inhuis_local")
            self.assertGreaterEqual(len(first[1]), 32)

    def test_missing_credentials_never_recreate_existing_database(self):
        with tempfile.TemporaryDirectory() as root:
            data = Path(root)
            (data / "postgres").mkdir()
            (data / "postgres" / "PG_VERSION").write_text("17", encoding="ascii")
            with self.assertRaises(RuntimeError):
                db.credentials(data)

    def test_credentials_url_is_encoded(self):
        url = db.database_url("name@test", "pw+&?")
        self.assertIn("name%40test", url)
        self.assertIn("pw%2B%26%3F", url)


if __name__ == "__main__":
    unittest.main()
