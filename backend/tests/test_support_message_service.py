from sqlalchemy import create_engine, text

from app.services.support_message_service import (
    RECIPIENT_ALL_ADMINS,
    STATUS_CLOSED,
    STATUS_IN_PROGRESS,
    STATUS_OPEN,
    SupportMessageError,
    add_support_message,
    add_support_recipient,
    create_support_thread,
    ensure_support_message_foundation,
    export_support_threads_csv,
    list_support_messages,
    list_support_threads,
    set_support_thread_status,
)


def make_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        ensure_support_message_foundation(conn)
    return engine


def test_new_household_message_starts_open_and_stores_screen_context():
    engine = make_engine()
    with engine.begin() as conn:
        result = create_support_thread(
            conn,
            created_by_user_id="admin-1",
            created_by_name="Admin Een",
            sender_role="Huishoud-Admin",
            subject="Voorraad wordt niet opgeslagen",
            message_text="Na Verzenden blijft de oude waarde staan.",
            origin_screen_name="Voorraad",
            origin_route="/inventory",
            origin_app_version="v-test",
            household_id="household-1",
        )

        assert result.status == STATUS_OPEN
        row = conn.execute(text("SELECT * FROM support_threads WHERE id = :id"), {"id": result.thread_id}).mappings().one()
        assert row["status"] == STATUS_OPEN
        assert row["origin_screen_name"] == "Voorraad"
        assert row["origin_route"] == "/inventory"
        assert row["origin_app_version"] == "v-test"
        assert row["household_id"] == "household-1"
        assert conn.execute(text("SELECT COUNT(*) FROM support_messages")).scalar_one() == 1


def test_correspondence_is_append_only_and_ordered():
    engine = make_engine()
    with engine.begin() as conn:
        thread = create_support_thread(
            conn,
            created_by_user_id="admin-1",
            created_by_name="Admin Een",
            sender_role="Huishoud-Admin",
            subject="Vraag",
            message_text="Eerste bericht",
            origin_screen_name="Start",
            household_id="household-1",
        )
        add_support_message(
            conn,
            thread_id=thread.thread_id,
            sender_user_id="super-1",
            sender_name="Superuser",
            sender_role="Superuser",
            message_text="Antwoord",
            is_superuser=True,
        )
        add_support_message(
            conn,
            thread_id=thread.thread_id,
            sender_user_id="admin-1",
            sender_name="Admin Een",
            sender_role="Huishoud-Admin",
            message_text="Aanvulling",
            is_superuser=False,
            household_id="household-1",
        )

        messages = list_support_messages(
            conn,
            thread_id=thread.thread_id,
            household_id="household-1",
        )
        assert [row["message_text"] for row in messages] == ["Eerste bericht", "Antwoord", "Aanvulling"]
        assert conn.execute(text("SELECT COUNT(*) FROM support_messages")).scalar_one() == 3


def test_household_cannot_read_or_reply_to_another_households_message():
    engine = make_engine()
    with engine.begin() as conn:
        thread = create_support_thread(
            conn,
            created_by_user_id="admin-1",
            created_by_name="Admin Een",
            sender_role="Huishoud-Admin",
            subject="Privé",
            message_text="Alleen huishouden één",
            origin_screen_name="Voorraad",
            household_id="household-1",
        )

        for action in (
            lambda: list_support_messages(conn, thread_id=thread.thread_id, household_id="household-2"),
            lambda: add_support_message(
                conn,
                thread_id=thread.thread_id,
                sender_user_id="admin-2",
                sender_name="Admin Twee",
                sender_role="Huishoud-Admin",
                message_text="Ongeoorloofd antwoord",
                is_superuser=False,
                household_id="household-2",
            ),
        ):
            try:
                action()
            except SupportMessageError as exc:
                assert "actieve huishouden" in str(exc)
            else:
                raise AssertionError("Huishoudisolatie moet fail-closed zijn")

        assert conn.execute(text("SELECT COUNT(*) FROM support_messages")).scalar_one() == 1


def test_superuser_can_assign_only_the_three_supported_statuses():
    engine = make_engine()
    with engine.begin() as conn:
        thread = create_support_thread(
            conn,
            created_by_user_id="admin-1",
            created_by_name="Admin Een",
            sender_role="Huishoud-Admin",
            subject="Status",
            message_text="Statuscontrole",
            origin_screen_name="Instellingen",
            household_id="household-1",
        )

        set_support_thread_status(conn, thread_id=thread.thread_id, status=STATUS_IN_PROGRESS)
        assert conn.execute(text("SELECT status FROM support_threads")).scalar_one() == STATUS_IN_PROGRESS

        set_support_thread_status(conn, thread_id=thread.thread_id, status=STATUS_CLOSED)
        closed = conn.execute(text("SELECT status, closed_at FROM support_threads")).mappings().one()
        assert closed["status"] == STATUS_CLOSED
        assert closed["closed_at"] is not None

        set_support_thread_status(conn, thread_id=thread.thread_id, status=STATUS_OPEN)
        reopened = conn.execute(text("SELECT status, closed_at FROM support_threads")).mappings().one()
        assert reopened["status"] == STATUS_OPEN
        assert reopened["closed_at"] is None

        try:
            set_support_thread_status(conn, thread_id=thread.thread_id, status="Verwijderd")
        except SupportMessageError as exc:
            assert "Onbekende status" in str(exc)
        else:
            raise AssertionError("Onbekende statussen moeten worden geweigerd")


def test_reply_disabled_blocks_admin_but_not_superuser():
    engine = make_engine()
    with engine.begin() as conn:
        thread = create_support_thread(
            conn,
            created_by_user_id="super-1",
            created_by_name="Superuser",
            sender_role="Superuser",
            subject="Onderhoud",
            message_text="Vanavond onderhoud.",
            origin_screen_name="Platformbeheer",
            household_id="household-1",
            recipient_type=RECIPIENT_ALL_ADMINS,
            reply_allowed=False,
        )
        add_support_recipient(conn, thread_id=thread.thread_id, household_id="household-1", admin_user_id="admin-1")

        try:
            add_support_message(
                conn,
                thread_id=thread.thread_id,
                sender_user_id="admin-1",
                sender_name="Admin Een",
                sender_role="Huishoud-Admin",
                message_text="Ik probeer te reageren",
                is_superuser=False,
                household_id="household-1",
            )
        except SupportMessageError as exc:
            assert "niet toegestaan" in str(exc)
        else:
            raise AssertionError("Admin-reactie moet geblokkeerd zijn")

        add_support_message(
            conn,
            thread_id=thread.thread_id,
            sender_user_id="super-1",
            sender_name="Superuser",
            sender_role="Superuser",
            message_text="Aanvulling van beheer",
            is_superuser=True,
        )
        assert conn.execute(text("SELECT COUNT(*) FROM support_messages")).scalar_one() == 2


def test_list_filters_by_household_and_status():
    engine = make_engine()
    with engine.begin() as conn:
        first = create_support_thread(
            conn,
            created_by_user_id="admin-1",
            created_by_name="Admin Een",
            sender_role="Huishoud-Admin",
            subject="Eerste",
            message_text="Eerste",
            origin_screen_name="Voorraad",
            household_id="household-1",
        )
        create_support_thread(
            conn,
            created_by_user_id="admin-2",
            created_by_name="Admin Twee",
            sender_role="Huishoud-Admin",
            subject="Tweede",
            message_text="Tweede",
            origin_screen_name="Winkels",
            household_id="household-2",
        )
        set_support_thread_status(conn, thread_id=first.thread_id, status=STATUS_IN_PROGRESS)

        rows = list_support_threads(conn, household_id="household-1", status=STATUS_IN_PROGRESS)
        assert len(rows) == 1
        assert rows[0]["subject"] == "Eerste"


def test_csv_export_uses_one_row_per_thread_and_respects_status_filter():
    engine = make_engine()
    with engine.begin() as conn:
        open_thread = create_support_thread(
            conn,
            created_by_user_id="admin-1",
            created_by_name="Admin Een",
            sender_role="Huishoud-Admin",
            subject="Open melding",
            message_text="Bericht",
            origin_screen_name="Voorraad",
            origin_route="/inventory",
            household_id="household-1",
        )
        closed_thread = create_support_thread(
            conn,
            created_by_user_id="admin-2",
            created_by_name="Admin Twee",
            sender_role="Huishoud-Admin",
            subject="Gesloten melding",
            message_text="Bericht",
            origin_screen_name="Winkels",
            household_id="household-2",
        )
        set_support_thread_status(conn, thread_id=closed_thread.thread_id, status=STATUS_CLOSED)

        csv_text = export_support_threads_csv(conn, status=STATUS_OPEN)
        lines = csv_text.splitlines()
        assert len(lines) == 2
        assert "Meldingsnummer;Status;Onderwerp" in lines[0]
        assert open_thread.thread_number in lines[1]
        assert "Open melding" in lines[1]
        assert closed_thread.thread_number not in csv_text
