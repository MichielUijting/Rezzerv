"""Contract tests: python -m unittest backend.tests.test_maintenance_state_contract"""
import unittest
from backend.app.services.maintenance_state_contract import (
    MaintenanceState as S, MaintenanceTransitionError, allows_new_writes, validate_transition,
)


class MaintenanceStateContractTest(unittest.TestCase):
    def test_states_block_all_writes_during_maintenance(self):
        for state in S:
            self.assertEqual(allows_new_writes(state), state in (S.NORMAL, S.ANNOUNCED))

    def test_requires_authorized_operator(self):
        with self.assertRaises(MaintenanceTransitionError):
            validate_transition(S.NORMAL, S.ANNOUNCED, authorized=False)

    def test_drain_must_prove_zero_writers(self):
        for count, verified in ((None, True), (1, True), (0, False)):
            with self.subTest(count=count, verified=verified):
                with self.assertRaises(MaintenanceTransitionError):
                    validate_transition(S.DRAINING, S.LOCKED, authorized=True,
                                        active_writers=count, runtime_verified=verified)
        validate_transition(S.DRAINING, S.LOCKED, authorized=True,
                            active_writers=0, runtime_verified=True)

    def test_no_direct_unlock(self):
        with self.assertRaises(MaintenanceTransitionError):
            validate_transition(S.LOCKED, S.NORMAL, authorized=True,
                                active_writers=0, runtime_verified=True)

    def test_after_reboot_requires_verification(self):
        with self.assertRaises(MaintenanceTransitionError):
            validate_transition(S.LOCKED, S.VERIFYING, authorized=True)
        validate_transition(S.LOCKED, S.VERIFYING, authorized=True, runtime_verified=True)
        with self.assertRaises(MaintenanceTransitionError):
            validate_transition(S.VERIFYING, S.NORMAL, authorized=True)
        validate_transition(S.VERIFYING, S.NORMAL, authorized=True, runtime_verified=True)


if __name__ == "__main__":
    unittest.main()
