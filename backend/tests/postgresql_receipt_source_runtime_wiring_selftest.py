from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import engine
import app.main as main


def main_test() -> int:
    assert engine.dialect.name == "postgresql", engine.dialect.name

    household_id = f"f5-source-{uuid.uuid4()}"
    with engine.begin() as conn:
        current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
        runtime_create = bool(
            conn.execute(
                text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            ).scalar_one()
        )
        assert current_user == "rezzerv_app", current_user
        assert runtime_create is False, runtime_create
        conn.execute(
            text(
                """
                INSERT INTO households (id, naam, created_at)
                VALUES (:id, :naam, CURRENT_TIMESTAMP)
                """
            ),
            {"id": household_id, "naam": "F5 receipt source runtime wiring"},
        )

    source = main.ensure_household_email_source(household_id)
    source_id = str(source.get("id") or "").strip()
    route_address = str(source.get("route_address") or "").strip()

    assert source_id == f"{household_id}-email-route", source
    assert str(source.get("household_id") or "") == household_id, source
    assert str(source.get("type") or "") == "email", source
    assert bool(source.get("is_active")) is True, source
    assert route_address == f"bon+{household_id}@receipts.rezzerv.example", source

    with engine.begin() as conn:
        persisted = conn.execute(
            text(
                """
                SELECT id, household_id, type, source_path, is_active
                FROM receipt_sources
                WHERE id = :id
                """
            ),
            {"id": source_id},
        ).mappings().one()

    assert str(persisted["household_id"]) == household_id, persisted
    assert str(persisted["type"]) == "email", persisted
    assert str(persisted["source_path"]) == route_address, persisted
    assert bool(persisted["is_active"]) is True, persisted

    email_bytes = (
        "From: receipts@example.invalid\r\n"
        f"To: {route_address}\r\n"
        "Subject: F5-04 receipt source runtime wiring\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "JUMBO 1234 AB Utrecht\r\n"
        "Testartikel 1,00\r\n"
        "TOTAAL 1,00\r\n"
    ).encode("utf-8")

    ingest_calls: list[dict[str, object]] = []
    original_ingest = main.ingest_receipt

    def fake_ingest_receipt(**kwargs: object) -> dict[str, object]:
        ingest_calls.append(dict(kwargs))
        return {
            "raw_receipt_id": None,
            "receipt_table_id": None,
            "duplicate": False,
            "parse_status": "f5_source_runtime_wiring",
            "source_id": kwargs.get("source_id"),
        }

    main.ingest_receipt = fake_ingest_receipt
    try:
        result = main.import_email_receipt_payload(
            household_id=household_id,
            email_bytes=email_bytes,
            fallback_filename="f5-04-runtime-wiring.eml",
        )
    finally:
        main.ingest_receipt = original_ingest

    assert len(ingest_calls) == 1, ingest_calls
    ingest_call = ingest_calls[0]
    assert str(ingest_call.get("household_id") or "") == household_id, ingest_call
    assert str(ingest_call.get("source_id") or "") == source_id, ingest_call
    assert str(ingest_call.get("filename") or "") == "f5-04-runtime-wiring.eml", ingest_call
    assert str(ingest_call.get("mime_type") or "") == "message/rfc822", ingest_call
    assert str(result.get("source_id") or "") == source_id, result

    print(f"source_id={source_id}")
    print(f"route_address={route_address}")
    print("PASS receipt_source_helper_is_wired_at_runtime_startup")
    print("PASS receipt_email_source_is_persisted_in_postgresql")
    print("PASS receipt_email_source_is_household_scoped")
    print("PASS eml_import_uses_configured_receipt_source")
    print("PASS receipt_source_unconfigured_runtime_error_is_eliminated")
    print("PASS postgresql_runtime_is_dml_only")
    print("F5_RECEIPT_SOURCE_RUNTIME_WIRING_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_test())
