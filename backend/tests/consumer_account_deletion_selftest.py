"""Account deletion acceptance on isolated PostgreSQL, not the PO's runtime."""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from app.services.consumer_account_file_deletion_service import (
    HouseholdFileStage,
    reconcile_household_file_staging,
)
from app.services.consumer_account_deletion_service import (
    AccountDeletionConflictError,
    AccountDeletionPasswordError,
    CONFIRMATION,
    delete_consumer_account,
    delete_platform_managed_account,
    deletion_preview,
)
from app.testing.postgresql_acceptance_foundation import (
    create_postgresql_runtime_test_engine,
    postgresql_acceptance_snapshot,
    reset_postgresql_test_database,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    seed_household,
    seed_membership,
    seed_user,
)


def _id(name):
    return name + "-" + uuid.uuid4().hex


def _count(conn, table, where, params):
    return int(conn.execute(text("SELECT COUNT(*) FROM " + table + " WHERE " + where), params).scalar() or 0)


def run() -> int:
    checks = []
    # This test performs a full reset: strictly GitHub's short-lived test service.
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("TEST_POSTGRES_DB") != "rezzerv_authorization_membership_ci":
        raise RuntimeError("Account deletion acceptance requires the isolated GitHub PostgreSQL test database.")
    snap = postgresql_acceptance_snapshot()
    if snap["database"] != "rezzerv_authorization_membership_ci":
        raise RuntimeError("Unexpected database; refusing destructive test reset.")
    assert snap["datastore"] == "postgresql"
    assert snap["runtime_create"] is False
    checks.append("isolated_postgresql_dml_only")

    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    try:
        users = [_id("departing"), _id("oldest"), _id("newest"), _id("outsider")]
        emails = [u + "@example.test" for u in users]
        shared, solo, unrelated = (_id("shared"), _id("solo"), _id("unrelated"))
        departed_membership, oldest_membership, newest_membership = (_id("membership") for _ in range(3))
        with engine.begin() as conn:
            for hid in [shared, solo, unrelated]:
                seed_household(conn, household_id=hid, name=hid)
            for uid, email in zip(users, emails):
                seed_user(conn, user_id=uid, email=email, password="TestPassword123!")
            for uid, date in zip(users, ["2026-11-20", "2023-01-02", "2025-09-11", "2022-01-01"]):
                conn.execute(text("UPDATE app_users SET created_at=CAST(:created_at AS TIMESTAMP) WHERE id=:uid"), {
                    "uid": uid, "created_at": date + " 12:00:00",
                })
            seed_membership(conn, membership_id=departed_membership, household_id=shared,
                            user_id=users[0], email=emails[0], role="admin")
            seed_membership(conn, membership_id=oldest_membership, household_id=shared,
                            user_id=users[1], email=emails[1], role="member")
            seed_membership(conn, membership_id=newest_membership, household_id=shared,
                            user_id=users[2], email=emails[2], role="member")
            seed_membership(conn, membership_id=_id("membership"), household_id=solo,
                            user_id=users[0], email=emails[0], role="admin")
            seed_membership(conn, membership_id=_id("membership"), household_id=unrelated,
                            user_id=users[3], email=emails[3], role="admin")
            for hid in [shared, solo, unrelated]:
                conn.execute(text("INSERT INTO spaces(id, naam, household_id, active) VALUES (:id,'Kast',:hid,TRUE)"), {
                    "id": _id("space"), "hid": hid,
                })
            preview = deletion_preview(conn, user_id=users[0])
            assert preview["households_to_keep"] == 1
            assert preview["households_to_delete"] == 1
        checks.append("multiple_households_preview_correct")

        for bad_confirmation, bad_password, expected_exception in [
            ("NIET VERWIJDEREN", "TestPassword123!", AccountDeletionConflictError),
            (CONFIRMATION, "WrongPassword123!", AccountDeletionPasswordError),
        ]:
            try:
                with engine.begin() as conn:
                    delete_consumer_account(conn, user_id=users[0],
                                            current_password=bad_password,
                                            confirmation=bad_confirmation)
            except expected_exception:
                pass
            else:
                raise AssertionError("Deletion without confirmation/password unexpectedly succeeded")
        with engine.begin() as conn:
            assert _count(conn, "app_users", "id=:uid", {"uid": users[0]}) == 1
            assert _count(conn, "spaces", "household_id=:hid", {"hid": shared}) == 1
            assert _count(conn, "spaces", "household_id=:hid", {"hid": solo}) == 1
        checks.append("invalid_credentials_or_confirmation_changes_nothing")

        # Files without matching DB metadata must never be silently orphaned.
        # The dedicated CI database guard above prevents any PO-runtime mutation.
        receipt_root = Path(os.environ["RECEIPT_STORAGE_ROOT"])
        probe = receipt_root / solo / "unknown-unindexed-receipt.txt"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("isolated-file-probe", encoding="utf-8")
        try:
            # The exception MUST exit engine.begin() so SQLAlchemy rolls back
            # all earlier household changes, including admin promotion.
            try:
                with engine.begin() as conn:
                    delete_consumer_account(
                        conn, user_id=users[0], current_password="TestPassword123!",
                        confirmation=CONFIRMATION,
                    )
            except AccountDeletionConflictError:
                pass
            else:
                raise AssertionError("Account deletion without a file stage orphaned an unindexed receipt file")
            with engine.begin() as conn:
                assert _count(conn, "app_users", "id=:uid", {"uid": users[0]}) == 1
                assert _count(conn, "spaces", "household_id=:hid", {"hid": solo}) == 1
                assert _count(conn, "household_memberships",
                              "household_id=:hid", {"hid": shared}) == 3
                assert _count(conn, "household_memberships",
                              "household_id=:hid", {"hid": solo}) == 1
        finally:
            probe.unlink()
        checks.append("unindexed_receipt_file_blocks_all_deletion_without_mutation")

        # Before commit, household files can be staged. A crash/rollback must
        # restore the original content without affecting shared households.
        staged_probe = receipt_root / solo / "2026" / "11" / "raw-receipt.txt"
        staged_probe.parent.mkdir(parents=True, exist_ok=True)
        staged_probe.write_text("private-sole-household-file", encoding="utf-8")
        source_probe = receipt_root.parent / "sources" / solo / "scan-folder" / "source.pdf"
        source_probe.parent.mkdir(parents=True, exist_ok=True)
        source_probe.write_bytes(b"%PDF-1.4\nsole user\n")
        debug_probe = receipt_root.parent / "debug" / solo / "2026" / "11" / "debug.json"
        debug_probe.parent.mkdir(parents=True, exist_ok=True)
        debug_probe.write_text('{"personal":"test-only"}', encoding="utf-8")
        shared_probe = receipt_root / shared / "shared-receipt.txt"
        shared_probe.parent.mkdir(parents=True, exist_ok=True)
        shared_probe.write_text("keep shared household data", encoding="utf-8")
        # Digital AH/Lidl/Jumbo receipts are stored under an independent root.
        # The previous deletion guard rejected their valid storage_path outright.
        retailer_root = Path(os.environ["RETAILER_RECEIPT_STORAGE_ROOT"])
        retailer_probe = retailer_root / solo / "2026" / "11" / "ah-receipt.json"
        retailer_probe.parent.mkdir(parents=True, exist_ok=True)
        retailer_probe.write_text('{"provider":"ah","fixture":true}', encoding="utf-8")
        retailer_shared = retailer_root / shared / "2026" / "11" / "keep.json"
        retailer_shared.parent.mkdir(parents=True, exist_ok=True)
        retailer_shared.write_text('{"provider":"ah","shared":true}', encoding="utf-8")
        # Real receipt rows as well as physical files must remain for shared
        # households, while sole-household receipt rows are deleted.
        with engine.begin() as conn:
            for hid, file_path, raw_id, digest in (
                (shared, shared_probe, _id("raw-shared"), "a" * 64),
                (solo, staged_probe, _id("raw-sole"), "b" * 64),
                (solo, retailer_probe, _id("raw-sole-retailer"), "e" * 64),
                (shared, retailer_shared, _id("raw-shared-retailer"), "f" * 64),
            ):
                conn.execute(text("""
                    INSERT INTO raw_receipts(
                        id, household_id, source_id, original_filename,
                        mime_type, storage_path, sha256_hash, raw_status
                    ) VALUES(
                        :id, :hid, NULL, :filename,
                        'text/plain', :storage_path, :sha, 'failed'
                    )
                """), {
                    "id": raw_id, "hid": hid, "filename": file_path.name,
                    "storage_path": str(file_path), "sha": digest,
                })
        stage = HouseholdFileStage()
        try:
            with engine.begin() as conn:
                stage.stage(conn, [solo])
                assert not staged_probe.exists()
                assert not source_probe.exists()
                assert not debug_probe.exists()
                assert not retailer_probe.exists()
                assert retailer_shared.exists()
                raise RuntimeError("deliberate before-commit failure")
        except RuntimeError as exc:
            assert str(exc) == "deliberate before-commit failure"
        # Simulate process restart: consult committed SQL identity to restore.
        assert reconcile_household_file_staging(engine) == 4
        assert staged_probe.read_text(encoding="utf-8") == "private-sole-household-file"
        assert source_probe.read_bytes().startswith(b"%PDF-1.4")
        assert debug_probe.read_text(encoding="utf-8").startswith("{")
        assert retailer_probe.read_text(encoding="utf-8").startswith('{"provider":"ah"')
        assert retailer_shared.exists()
        assert shared_probe.read_text(encoding="utf-8") == "keep shared household data"
        checks.append("staged_receipts_and_source_folders_recovered_after_rollback")

        stage = HouseholdFileStage()
        with engine.begin() as conn:
            result = delete_consumer_account(
                conn, user_id=users[0], current_password="TestPassword123!",
                confirmation=CONFIRMATION, file_stage=stage,
            )
            assert result["deleted"] is True
            assert result["households_deleted"] == 1
            assert result["households_preserved"] == 1
            assert result["admins_transferred"] == 1
        stage.finalize()
        assert not staged_probe.exists()
        assert not source_probe.exists()
        assert not debug_probe.exists()
        assert not retailer_probe.exists()
        assert retailer_shared.read_text(encoding="utf-8").startswith('{"provider":"ah"')
        assert shared_probe.read_text(encoding="utf-8") == "keep shared household data"
        checks.append("digital_retailer_receipt_removed_only_for_deleted_household")
        checks.append("multi_household_deletion_transaction_committed")
        checks.append("sole_household_receipt_source_debug_files_removed_after_commit")
        checks.append("shared_household_receipt_file_preserved")

        with engine.begin() as conn:
            assert _count(conn, "app_users", "id=:uid", {"uid": users[0]}) == 0
            assert _count(conn, "household_memberships", "lower(trim(user_email))=:email", {"email": emails[0]}) == 0
            assert _count(conn, "household_registry", "id=:hid", {"hid": solo}) == 0
            assert _count(conn, "spaces", "household_id=:hid", {"hid": solo}) == 0
            assert _count(conn, "raw_receipts", "household_id=:hid", {"hid": solo}) == 0
            assert _count(conn, "raw_receipts", "household_id=:hid", {"hid": shared}) == 2
            assert _count(conn, "household_registry", "id=:hid", {"hid": shared}) == 1
            assert _count(conn, "spaces", "household_id=:hid", {"hid": shared}) == 1
            assert _count(conn, "household_registry", "id=:hid", {"hid": unrelated}) == 1
            assert _count(conn, "spaces", "household_id=:hid", {"hid": unrelated}) == 1
            role = conn.execute(text("""
                SELECT role_key FROM auth_membership_roles
                WHERE household_id=:hid AND membership_id=:mid
            """), {"hid": shared, "mid": oldest_membership}).scalar_one()
            assert role == "household.admin"
            mirror = conn.execute(text("""
                SELECT role FROM household_memberships WHERE household_id=:hid AND id=:mid
            """), {"hid": shared, "mid": oldest_membership}).scalar_one()
            assert mirror == "admin"
            late_role = conn.execute(text("""
                SELECT role_key FROM auth_membership_roles
                WHERE household_id=:hid AND membership_id=:mid
            """), {"hid": shared, "mid": newest_membership}).scalar_one()
            assert late_role == "household.member"
            assert _count(conn, "app_users", "id=:uid", {"uid": users[1]}) == 1
            assert _count(conn, "app_users", "id=:uid", {"uid": users[2]}) == 1
        checks.append("oldest_remaining_user_promoted_and_shared_data_preserved")
        checks.append("sole_household_and_only_its_data_deleted")
        checks.append("other_user_and_household_untouched")

        # A legacy advanced_member is user-visible as a Beheerder; an accepted
        # membership remains a real member when choosing an admin successor.
        legacy_household = _id("legacy-shared")
        legacy_user, legacy_successor = _id("legacy-admin"), _id("legacy-successor")
        legacy_email, successor_email = legacy_user + "@example.test", legacy_successor + "@example.test"
        successor_mid = _id("membership")
        with engine.begin() as conn:
            seed_household(conn, household_id=legacy_household, name="Legacy shared")
            seed_user(conn, user_id=legacy_user, email=legacy_email, password="TestPassword123!")
            seed_user(conn, user_id=legacy_successor, email=successor_email, password="TestPassword123!")
            seed_membership(conn, membership_id=_id("membership"), household_id=legacy_household,
                            user_id=legacy_user, email=legacy_email, role="advanced_member")
            seed_membership(conn, membership_id=successor_mid, household_id=legacy_household,
                            user_id=legacy_successor, email=successor_email, role="member")
            # Historical schemas may have status; canonical ones do not.
            member_cols = {item["name"] for item in inspect(conn).get_columns("household_memberships")}
            if "status" in member_cols:
                conn.execute(text(
                    "UPDATE household_memberships SET status='accepted' WHERE id=:mid"
                ), {"mid": successor_mid})
        with engine.begin() as conn:
            legacy_result = delete_consumer_account(
                conn, user_id=legacy_user, current_password="TestPassword123!",
                confirmation=CONFIRMATION,
            )
            assert legacy_result["admins_transferred"] == 1
            assert legacy_result["households_preserved"] == 1
            role = conn.execute(text("""
                SELECT role_key FROM auth_membership_roles
                WHERE household_id=:hid AND membership_id=:mid
            """), {"hid": legacy_household, "mid": successor_mid}).scalar_one()
            assert role == "household.admin"
        checks.append("legacy_beheerder_succession_with_optional_status_column")


        # Platformbeheer invokes the identical protected deletion engine.
        # A suspended household Beheerder can be removed, while shared receipts
        # and ownership are retained and passed to the remaining member.
        platform_actor = _id("platform-admin")
        platform_actor_email = platform_actor + "@example.test"
        with engine.begin() as conn:
            seed_user(conn, user_id=platform_actor, email=platform_actor_email, password="TestPassword123!")
            conn.execute(text("""
                INSERT INTO auth_platform_user_roles(user_id, role_key, active)
                VALUES (:uid, 'platform.platform_admin', TRUE)
            """), {"uid": platform_actor})
            conn.execute(text("""
                UPDATE app_users SET account_status='suspended', suspended_at=CURRENT_TIMESTAMP
                WHERE id=:uid
            """), {"uid": users[1]})
            conn.execute(text("""
                INSERT INTO auth_platform_user_roles(user_id, role_key, active)
                VALUES (:uid, 'platform.frontteam', TRUE)
            """), {"uid": users[3]})
        checks.append("platform_admin_and_protected_targets_seeded")

        def expect_conflict(*, actor, target, confirmation):
            try:
                with engine.begin() as conn:
                    delete_platform_managed_account(
                        conn, actor_user_id=actor, user_id=target, confirmation=confirmation,
                    )
            except AccountDeletionConflictError:
                return
            raise AssertionError("Unauthorized or unconfirmed account deletion was accepted")

        expect_conflict(actor=users[3], target=users[1], confirmation="VERWIJDER " + emails[1])
        expect_conflict(actor=platform_actor, target=platform_actor,
                        confirmation="VERWIJDER " + platform_actor_email)
        expect_conflict(actor=platform_actor, target=users[1], confirmation="WRONG")
        expect_conflict(actor=platform_actor, target=users[3], confirmation="VERWIJDER " + emails[3])
        with engine.begin() as conn:
            assert _count(conn, "app_users", "id=:uid", {"uid": users[1]}) == 1
            assert _count(conn, "raw_receipts", "household_id=:hid", {"hid": shared}) == 2
            assert _count(conn, "household_memberships", "household_id=:hid", {"hid": shared}) == 2
        checks.append("platform_delete_denies_nonadmin_self_protected_and_wrong_confirmation")

        stage = HouseholdFileStage()
        with engine.begin() as conn:
            outcome = delete_platform_managed_account(
                conn, actor_user_id=platform_actor, user_id=users[1],
                confirmation="VERWIJDER " + emails[1], file_stage=stage,
            )
            assert outcome["deleted"] is True
            assert outcome["households_deleted"] == 0
            assert outcome["households_preserved"] == 1
            assert outcome["admins_transferred"] == 1
        stage.finalize()
        with engine.begin() as conn:
            assert _count(conn, "app_users", "id=:uid", {"uid": users[1]}) == 0
            assert _count(conn, "household_registry", "id=:hid", {"hid": shared}) == 1
            assert _count(conn, "raw_receipts", "household_id=:hid", {"hid": shared}) == 2
            assert _count(conn, "app_users", "id=:uid", {"uid": users[2]}) == 1
            assert _count(conn, "app_users", "id=:uid", {"uid": platform_actor}) == 1
            assert conn.execute(text("""
                SELECT role_key FROM auth_membership_roles
                WHERE household_id=:hid AND membership_id=:mid
            """), {"hid": shared, "mid": newest_membership}).scalar_one() == "household.admin"
        assert shared_probe.read_text(encoding="utf-8") == "keep shared household data"
        checks.append("platform_delete_suspended_admin_preserves_shared_receipts_and_promotes_successor")

        # Platform-managed deletion of a *sole-member* household is the precise
        # product path that failed in the local PO test. Use the real PostgreSQL
        # runtime role, a receipt row and a staged private file, never PO data.
        solo_platform_user = _id("platform-solo-user")
        solo_platform_email = solo_platform_user + "@example.test"
        solo_platform_household = _id("platform-solo-household")
        solo_direct_space = _id("direct-space")
        solo_platform_file = receipt_root / solo_platform_household / "test-receipt.txt"
        solo_platform_file.parent.mkdir(parents=True, exist_ok=True)
        solo_platform_file.write_text("isolated-platform-deletion-fixture", encoding="utf-8")
        with engine.begin() as conn:
            seed_household(conn, household_id=solo_platform_household, name="Sole member for platform deletion")
            seed_user(conn, user_id=solo_platform_user, email=solo_platform_email,
                      password="TestPassword123!")
            seed_membership(conn, membership_id=_id("membership"),
                            household_id=solo_platform_household, user_id=solo_platform_user,
                            email=solo_platform_email, role="admin")
            # Canonical Direct exists in real onboarded households. The
            # ordinary DELETE trigger forbids removing this location.
            conn.execute(text("""
                INSERT INTO spaces(id, naam, household_id, active, is_direct)
                VALUES (:id, 'Direct', :hid, TRUE, 1)
            """), {"id": solo_direct_space, "hid": solo_platform_household})
            conn.execute(text("""
                INSERT INTO raw_receipts(
                    id, household_id, source_id, original_filename,
                    mime_type, storage_path, sha256_hash, raw_status
                ) VALUES(
                    :id, :hid, NULL, :filename,
                    'text/plain', :storage_path, :sha, 'failed'
                )
            """), {
                "id": _id("raw-sole-platform"),
                "hid": solo_platform_household,
                "filename": solo_platform_file.name,
                "storage_path": str(solo_platform_file),
                "sha": "c" * 64,
            })
            assert deletion_preview(conn, user_id=solo_platform_user)["households_to_delete"] == 1

        # Outside a full household reset, deleting Direct must still fail.
        try:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM spaces WHERE id=:id"), {"id": solo_direct_space})
        except DBAPIError as exc:
            assert "Direct is een vaste locatie" in str(exc)
        else:
            raise AssertionError("Ordinary Direct DELETE bypassed canonical immutable trigger")
        with engine.connect() as conn:
            assert _count(conn, "spaces", "id=:id", {"id": solo_direct_space}) == 1
        checks.append("canonical_direct_location_immutable_outside_full_reset")

        solo_stage = HouseholdFileStage()
        try:
            with engine.begin() as conn:
                solo_result = delete_platform_managed_account(
                    conn, actor_user_id=platform_actor, user_id=solo_platform_user,
                    confirmation="VERWIJDER " + solo_platform_email,
                    file_stage=solo_stage,
                )
                assert solo_result["deleted"] is True
                assert solo_result["households_deleted"] == 1
                assert solo_result["households_preserved"] == 0
        except Exception:
            solo_stage.restore()
            raise
        # Simulate a crash after SQL commit but before file finalization.
        # Reconciliation must finish the purge from the committed DB identity.
        assert reconcile_household_file_staging(engine) == 1
        assert not solo_platform_file.exists()
        with engine.connect() as conn:
            assert _count(conn, "app_users", "id=:uid", {"uid": solo_platform_user}) == 0
            assert _count(conn, "household_registry", "id=:hid", {"hid": solo_platform_household}) == 0
            assert _count(conn, "raw_receipts", "household_id=:hid", {"hid": solo_platform_household}) == 0
            assert _count(conn, "spaces", "id=:id", {"id": solo_direct_space}) == 0
            assert _count(conn, "app_users", "id=:uid", {"uid": platform_actor}) == 1
            assert _count(conn, "household_registry", "id=:hid", {"hid": shared}) == 1
        checks.append("platform_delete_sole_household_with_direct_and_receipt_atomic_postgresql")

    finally:
        engine.dispose()
        reset_postgresql_test_database()

    for check in checks:
        print("PASS", check)
    print("RESULT", len(checks), "/", len(checks), "checks passed")
    print("ACCOUNT_DELETION_HOUSEHOLD_RETENTION_POSTGRESQL_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
