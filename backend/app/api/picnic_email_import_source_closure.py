from __future__ import annotations

import sys
from typing import Any, Optional

from fastapi import APIRouter, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import text

from app.db import engine
from app.services.receipt_service import ingest_receipt
from app.services.receipt_source_helper_service import ensure_household_email_source

PICNIC_EMAIL_IMPORT_PATH = "/api/receipts/picnic-email-import"
LEGACY_PICNIC_EMAIL_IMPORT_ENDPOINT_NAME = "import_picnic_email_receipt"


def _is_legacy_picnic_email_import_route(route: Any) -> bool:
    if not isinstance(route, APIRoute):
        return False
    methods = {str(method).upper() for method in (route.methods or set())}
    endpoint_name = str(getattr(getattr(route, "endpoint", None), "__name__", ""))
    return (
        route.path == PICNIC_EMAIL_IMPORT_PATH
        and "POST" in methods
        and endpoint_name == LEGACY_PICNIC_EMAIL_IMPORT_ENDPOINT_NAME
    )


def retire_legacy_picnic_email_import_route(app: FastAPI) -> APIRoute:
    """Retire exactly the legacy Picnic EML endpoint before canonical replacement.

    The legacy endpoint fabricated ``<household>-picnic-eml-upload`` as source_id.
    Under the PostgreSQL receipt-source foreign-key authority that id is invalid
    unless a source row exists. The replacement route below preserves the Picnic
    import behavior but resolves the household's persisted canonical email source.
    """

    matches = [route for route in app.router.routes if _is_legacy_picnic_email_import_route(route)]
    if len(matches) != 1:
        raise RuntimeError(
            "Picnic EML source closure expected exactly one "
            f"POST {PICNIC_EMAIL_IMPORT_PATH} route named "
            f"{LEGACY_PICNIC_EMAIL_IMPORT_ENDPOINT_NAME!r}; found {len(matches)}"
        )

    retired = matches[0]
    app.router.routes[:] = [route for route in app.router.routes if route is not retired]
    return retired


def retire_legacy_picnic_email_import_route_from_loaded_main() -> bool:
    """Apply the closure while app.main is finishing route registration."""

    main_module = sys.modules.get("app.main")
    app = getattr(main_module, "app", None) if main_module is not None else None
    if app is None:
        return False
    retire_legacy_picnic_email_import_route(app)
    return True


def _require_loaded_main():
    main_module = sys.modules.get("app.main")
    if main_module is None:
        raise RuntimeError("app.main is niet geladen voor Picnic EML import")
    required = (
        "require_household_context",
        "_looks_like_email_upload",
        "parse_email_receipt_payload",
        "store_receipt_email_metadata",
        "_normalized_purchase_at_or_fallback",
        "RECEIPT_STORAGE_ROOT",
        "logger",
    )
    missing = [name for name in required if not hasattr(main_module, name)]
    if missing:
        raise RuntimeError(
            "Picnic EML source closure mist app.main dependency/dependencies: "
            + ", ".join(missing)
        )
    return main_module


def create_picnic_email_import_source_closure_router() -> APIRouter:
    router = APIRouter(tags=["receipts-picnic-email-source-closure"])

    @router.post(PICNIC_EMAIL_IMPORT_PATH)
    async def import_picnic_email_receipt_with_persisted_source(
        household_id: str = Form(...),
        email_file: UploadFile = File(...),
        authorization: Optional[str] = Header(None),
    ):
        main_module = _require_loaded_main()
        context = main_module.require_household_context(authorization, household_id)
        effective_household_id = str(context["active_household_id"]).strip() or "1"

        email_bytes = await email_file.read()
        if not email_bytes:
            raise HTTPException(status_code=400, detail="Het Picnic e-mailbestand is leeg.")

        source_filename = email_file.filename or "picnic-receipt.eml"
        if not main_module._looks_like_email_upload(source_filename, email_file.content_type):
            raise HTTPException(status_code=400, detail="Gebruik een opgeslagen .eml-bestand voor Picnic.")

        try:
            source = ensure_household_email_source(effective_household_id)
            source_id = str(source.get("id") or "").strip()
            if not source_id:
                raise RuntimeError("De e-mailbron voor dit huishouden kon niet worden bepaald.")

            payload = main_module.parse_email_receipt_payload(
                email_bytes,
                fallback_filename=source_filename,
            )

            result = ingest_receipt(
                engine=engine,
                receipt_storage_root=main_module.RECEIPT_STORAGE_ROOT,
                household_id=effective_household_id,
                filename=source_filename,
                file_bytes=email_bytes,
                source_id=source_id,
                mime_type="message/rfc822",
                reject_non_receipt=False,
                create_failed_receipt_table=True,
                failed_store_name="Picnic",
                failed_purchase_at=None,
            )

            raw_receipt_id = result.get("raw_receipt_id")
            if raw_receipt_id:
                main_module.store_receipt_email_metadata(
                    raw_receipt_id,
                    effective_household_id,
                    payload,
                )

            receipt_table_id = result.get("receipt_table_id")
            if receipt_table_id:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            UPDATE receipt_tables
                            SET store_name = COALESCE(store_name, 'Picnic'),
                                store_chain = COALESCE(store_chain, 'Picnic'),
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :id
                            """
                        ),
                        {"id": receipt_table_id},
                    )

            result = main_module._normalized_purchase_at_or_fallback(
                str(result.get("receipt_table_id") or ""),
                result,
            )
            result["source_id"] = source_id
            result["source_label"] = "Handmatige Picnic e-mailupload"
            result["sender_email"] = payload.get("sender_email")
            result["sender_name"] = payload.get("sender_name")
            result["subject"] = payload.get("subject")
            result["received_at"] = payload.get("received_at")

        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            main_module.logger.exception(
                "Onverwachte fout bij handmatige Picnic e-mailimport voor household %s",
                effective_household_id,
            )
            raise HTTPException(
                status_code=500,
                detail="Het Picnic e-mailbestand kon niet volledig als kassabon worden verwerkt.",
            ) from exc

        status_code = 200 if result.get("duplicate") else 201
        return JSONResponse(status_code=status_code, content=result)

    return router
