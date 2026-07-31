from sqlalchemy import create_engine, text

from app.services.system_superuser_service import (
    SUPERGEBRUIKER_EMAIL,
    SystemSuperuserProvisioningError,
    ensure_fixed_system_superuser,
)


def make_engine(*, with_household_zero: bool = True):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                created_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_memberships (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                user_email TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT,
                updated_at TEXT
            )
        """))
        if with_household_zero:
            conn.execute(text("INSERT INTO household_registry(id, naam) VALUES ('0', 'Testhuishouden 0')"))
        conn.execute(text("INSERT INTO household_registry(id, naam) VALUES ('1', 'Huishouden 1')"))
    return engine


def test_vaste_supergebruiker_wordt_bovenop_bestaand_huishouden_0_aangemaakt():
    engine = make_engine()
    with engine.begin() as conn:
        result = ensure_fixed_system_superuser(conn, password="AfzonderlijkSterk123!")
        account = conn.execute(text("SELECT id, email, password FROM app_users WHERE email = :email"), {"email": SUPERGEBRUIKER_EMAIL}).mappings().one()
        membership = conn.execute(text("SELECT household_id, role, status FROM household_memberships WHERE user_email = :email"), {"email": SUPERGEBRUIKER_EMAIL}).mappings().one()
        household_role = conn.execute(text("SELECT role_key FROM auth_membership_roles WHERE membership_id = :membership_id"), {"membership_id": result.membership_id}).scalar_one()
        platform_roles = set(conn.execute(text("SELECT role_key FROM auth_platform_user_roles WHERE user_id = :email AND active = 1"), {"email": SUPERGEBRUIKER_EMAIL}).scalars().all())

    assert result.household_id == "0"
    assert account["id"] == SUPERGEBRUIKER_EMAIL
    assert account["password"] == "AfzonderlijkSterk123!"
    assert membership == {"household_id": "0", "role": "owner", "status": "active"}
    assert household_role == "huishouden.eigenaar"
    assert platform_roles == {"platform.supergebruiker", "platform.frontteam"}


def test_huishouden_0_wordt_nooit_door_de_service_aangemaakt():
    engine = make_engine(with_household_zero=False)
    with engine.begin() as conn:
        try:
            ensure_fixed_system_superuser(conn, password="AfzonderlijkSterk123!")
        except SystemSuperuserProvisioningError as exc:
            assert "huishouden 0 ontbreekt" in str(exc).lower()
        else:
            raise AssertionError("Ontbrekend huishouden 0 moet de voorziening blokkeren")
        assert conn.execute(text("SELECT COUNT(*) FROM app_users")).scalar_one() == 0


def test_provisioning_is_idempotent_en_ververst_het_wachtwoord():
    engine = make_engine()
    with engine.begin() as conn:
        first = ensure_fixed_system_superuser(conn, password="AfzonderlijkSterk123!")
        second = ensure_fixed_system_superuser(conn, password="NieuwAfzonderlijk456!")
        password = conn.execute(text("SELECT password FROM app_users WHERE email = :email"), {"email": SUPERGEBRUIKER_EMAIL}).scalar_one()

    assert first.account_created is True
    assert first.membership_created is True
    assert second.account_created is False
    assert second.membership_created is False
    assert second.roles_changed is False
    assert password == "NieuwAfzonderlijk456!"


def test_een_tweede_supergebruiker_wordt_gedeactiveerd():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_fixed_system_superuser(conn, password="AfzonderlijkSterk123!")
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('ander@rezzerv.local', 'platform.supergebruiker', 1)
        """))
        ensure_fixed_system_superuser(conn, password="AfzonderlijkSterk123!")
        active = conn.execute(text("""
            SELECT active FROM auth_platform_user_roles
            WHERE user_id = 'ander@rezzerv.local' AND role_key = 'platform.supergebruiker'
        """)).scalar_one()

    assert active == 0


def test_te_kort_wachtwoord_wordt_geweigerd_zonder_account():
    engine = make_engine()
    with engine.begin() as conn:
        try:
            ensure_fixed_system_superuser(conn, password="te-kort")
        except SystemSuperuserProvisioningError as exc:
            assert "minimaal 12" in str(exc)
        else:
            raise AssertionError("Een te kort wachtwoord moet worden geweigerd")
        assert conn.execute(text("SELECT COUNT(*) FROM app_users")).scalar_one() == 0
