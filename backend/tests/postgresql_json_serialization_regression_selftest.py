from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import engine
from app.services.receipt_service import serialize_receipt_row


def check(condition: bool, name: str, detail: object = "") -> None:
    if not condition:
        raise AssertionError(f"FAIL {name}: {detail}")
    print(f"PASS {name}")


def main() -> int:
    check(engine.dialect.name == "postgresql", "postgresql_runtime", engine.dialect.name)

    with engine.begin() as conn:
        current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
        runtime_create = bool(
            conn.execute(
                text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            ).scalar_one()
        )
        row = conn.execute(
            text(
                """
                SELECT
                    CAST('7f1c20d4-e1a5-4db4-8808-5ba53806bbca' AS uuid) AS native_uuid,
                    CAST('0.404' AS numeric) AS quantity_0404,
                    CAST('1.224' AS numeric) AS quantity_1224,
                    CAST('1.234567' AS numeric) AS quantity_1234567,
                    TIMESTAMPTZ '2026-09-07 12:34:56+00' AS purchase_at,
                    TIMESTAMPTZ '2026-09-07 12:35:57+00' AS created_at
                """
            )
        ).mappings().one()

    check(current_user == "rezzerv_app", "dml_only_runtime_user", current_user)
    check(runtime_create is False, "dml_only_runtime_has_no_schema_create", runtime_create)
    check(isinstance(row["native_uuid"], UUID), "postgresql_native_uuid_type", type(row["native_uuid"]))
    check(isinstance(row["quantity_0404"], Decimal), "postgresql_native_numeric_type", type(row["quantity_0404"]))
    check(isinstance(row["purchase_at"], datetime), "postgresql_native_timestamptz_type", type(row["purchase_at"]))

    # This is the production receipt serialization helper followed by the same
    # FastAPI encoder/Starlette JSONResponse boundary used for JSON responses.
    serialized = serialize_receipt_row(row)
    encoded = jsonable_encoder(serialized)
    response = JSONResponse(content=encoded)
    body_text = response.body.decode("utf-8")
    body = json.loads(body_text)

    check(response.media_type == "application/json", "json_response_media_type", response.media_type)
    check(body["native_uuid"] == "7f1c20d4-e1a5-4db4-8808-5ba53806bbca", "uuid_json_serialization", body["native_uuid"])
    check(body["purchase_at"] == "2026-09-07T12:34:56+00:00", "timestamptz_json_serialization", body["purchase_at"])
    check(body["created_at"] == "2026-09-07T12:35:57+00:00", "second_timestamptz_json_serialization", body["created_at"])

    expected_quantities = {
        "quantity_0404": 0.404,
        "quantity_1224": 1.224,
        "quantity_1234567": 1.234567,
    }
    for key, expected in expected_quantities.items():
        check(body[key] == expected, f"{key}_numeric_value", body[key])

    # Guard the historical quantity contract at the actual JSON bytes boundary:
    # quantities are not financial values and may not be rounded to scale 2/3.
    for literal in ("0.404", "1.224", "1.234567"):
        check(literal in body_text, f"quantity_literal_{literal}_preserved", body_text)

    print("F5_POSTGRESQL_JSON_SERIALIZATION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
