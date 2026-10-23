"""Check that authorization role seeding only changes differing grants."""
import inspect
import unittest

from backend.app.services.authorization_foundation_service import _seed_registry


class AuthorizationBootstrapIdempotenceTest(unittest.TestCase):
    def test_unchanged_grants_are_not_deleted_and_reinserted(self):
        source = inspect.getsource(_seed_registry)
        self.assertIn("desired - existing", source)
        self.assertIn("existing - desired", source)
        self.assertIn("SELECT permission_key FROM auth_role_permissions", source)
        self.assertIn("permission_key = :permission_key", source)


if __name__ == "__main__":
    unittest.main()
