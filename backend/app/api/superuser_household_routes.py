"""S2: audited read-only household inspection for the Rezzerv Beheercentrum.

These routes never rotate the superuser session into a household and expose no
household mutation endpoint. Household data is read through dedicated SELECT
projections; the only write is the mandatory authorization audit event.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from app.services.actor_attribution_service import ensure_actor_attribution_schema
from app.services.authorization_foundation_service import ensure_authorization_foundation, write_authorization_audit
from app.services.server_session_service import SESSION_COOKIE_NAME, resolve_server_session

SUPERUSER_ROLE_KEY = "platform.superuser"
SCREEN_KEYS = ("start", "kassa", "uitpakken", "voorraad", "bijna_op", "winkelen", "prognoses", "diagnose")


def _columns(conn: Connection, table: str) -> set[str]:
    inspector = inspect(conn)
    if table not in inspector.get_table_names():
        return set()
    return {str(c.get("name") or "") for c in inspector.get_columns(table)}


def _pick(columns: set[str], *candidates: str) -> str | None:
    return next((c for c in candidates if c in columns), None)


def _require_superuser(conn: Connection, raw_session_id: str | None):
    context = resolve_server_session(conn, raw_session_id)
    ensure_authorization_foundation(conn)
    granted = conn.execute(text("""
        SELECT 1 FROM auth_platform_user_roles
        WHERE user_id = :user_id AND role_key = :role_key AND active = 1 LIMIT 1
    """), {"user_id": context.user_id, "role_key": SUPERUSER_ROLE_KEY}).first()
    if not granted:
        raise HTTPException(status_code=403, detail="Alleen de platform-supergebruiker heeft toegang tot huishoudinzage")
    return context


def _household_identity_columns(conn: Connection) -> tuple[str, str | None, str | None, str | None]:
    cols = _columns(conn, "household_registry")
    id_col = _pick(cols, "id", "household_id")
    if not id_col:
        raise HTTPException(status_code=503, detail="Huishoudregister heeft geen bruikbare identificatiekolom")
    return id_col, _pick(cols, "naam", "name", "household_name"), _pick(cols, "status"), _pick(cols, "created_at")


def _household_exists(conn: Connection, household_id: str) -> bool:
    id_col, _, _, _ = _household_identity_columns(conn)
    return bool(conn.execute(text(f"SELECT 1 FROM household_registry WHERE CAST({id_col} AS TEXT)=:id LIMIT 1"), {"id": str(household_id)}).first())


def _member_exists(conn: Connection, household_id: str, user_id: str) -> bool:
    cols = _columns(conn, "household_memberships")
    if "household_id" not in cols or "user_id" not in cols:
        return False
    return bool(conn.execute(text("""
        SELECT 1 FROM household_memberships
        WHERE CAST(household_id AS TEXT)=:household_id
          AND CAST(user_id AS TEXT)=:user_id
        LIMIT 1
    """), {"household_id": household_id, "user_id": user_id}).first())


def _audit_view(conn: Connection, *, context, household_id: str, action: str, object_type: str, object_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
    write_authorization_audit(
        conn,
        actor_user_id=context.user_id,
        actor_type="platform_superuser",
        household_id=str(household_id),
        action=action,
        object_type=object_type,
        object_id=object_id or str(household_id),
        new_value=metadata,
        reason="Read-only superuser-inzage",
    )


def _scalar(conn: Connection, sql: str, params: dict[str, Any]) -> int:
    try:
        return int(conn.execute(text(sql), params).scalar() or 0)
    except Exception:
        return 0


def _table_household_count(conn: Connection, table: str, household_id: str, *, household_column: str = "household_id") -> int:
    cols = _columns(conn, table)
    if household_column not in cols:
        return 0
    return _scalar(conn, f"SELECT COUNT(*) FROM {table} WHERE CAST({household_column} AS TEXT)=:household_id", {"household_id": household_id})


def _latest_value(conn: Connection, table: str, household_id: str, candidates: tuple[str, ...], *, household_column: str = "household_id") -> Any:
    cols = _columns(conn, table)
    if household_column not in cols:
        return None
    col = _pick(cols, *candidates)
    if not col:
        return None
    return conn.execute(text(f"SELECT MAX({col}) FROM {table} WHERE CAST({household_column} AS TEXT)=:household_id"), {"household_id": household_id}).scalar()


def _members(conn: Connection, household_id: str, limit: int = 50) -> list[dict[str, Any]]:
    cols = _columns(conn, "household_memberships")
    if "household_id" not in cols:
        return []
    email_col = _pick(cols, "user_email", "email")
    user_col = _pick(cols, "user_id")
    role_col = _pick(cols, "role", "rol")
    status_col = _pick(cols, "status")
    selected = ["household_id"]
    aliases = []
    for col, alias in ((user_col, "user_id"), (email_col, "email"), (role_col, "role"), (status_col, "status")):
        if col:
            selected.append(f"{col} AS {alias}")
            aliases.append(alias)
    rows = conn.execute(text(f"SELECT {', '.join(selected)} FROM household_memberships WHERE CAST(household_id AS TEXT)=:household_id LIMIT :limit"), {"household_id": household_id, "limit": limit}).mappings().all()
    return [{key: row.get(key) for key in aliases} for row in rows]


def _safe_rows(
    conn: Connection,
    table: str,
    household_id: str,
    preferred: tuple[str, ...],
    *,
    where: str = "",
    order_candidates: tuple[str, ...] = ("updated_at", "created_at"),
    limit: int = 100,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    cols = _columns(conn, table)
    if "household_id" not in cols:
        return []
    selected = [c for c in preferred if c in cols]
    if not selected:
        return []
    if user_id and "user_id" not in cols:
        return []
    order_col = _pick(cols, *order_candidates)
    order_sql = f" ORDER BY {order_col} DESC" if order_col else ""
    clauses = ["CAST(household_id AS TEXT)=:household_id"]
    params: dict[str, Any] = {"household_id": household_id, "limit": limit}
    if where:
        clauses.append(f"({where})")
    if user_id:
        clauses.append("CAST(user_id AS TEXT)=:user_id")
        params["user_id"] = user_id
    rows = conn.execute(
        text(f"SELECT {', '.join(selected)} FROM {table} WHERE {' AND '.join(clauses)}{order_sql} LIMIT :limit"),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


def _actor_rows(
    conn: Connection,
    table: str,
    object_type: str,
    household_id: str,
    preferred: tuple[str, ...],
    *,
    order_candidates: tuple[str, ...] = ("updated_at", "created_at"),
    limit: int = 100,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    ensure_actor_attribution_schema(conn)
    cols = _columns(conn, table)
    if "household_id" not in cols or "id" not in cols:
        return []
    selected = [c for c in preferred if c in cols]
    if not selected:
        return []
    selected_sql = [f"t.{c} AS {c}" for c in selected]
    selected_sql.extend([
        "a.actor_user_id AS actor_user_id",
        "a.attribution_source AS actor_attribution_source",
    ])
    order_col = _pick(cols, *order_candidates)
    order_sql = f" ORDER BY t.{order_col} DESC" if order_col else ""
    clauses = ["CAST(t.household_id AS TEXT)=:household_id"]
    params: dict[str, Any] = {
        "household_id": household_id,
        "object_type": object_type,
        "limit": limit,
    }
    if user_id:
        clauses.append("CAST(a.actor_user_id AS TEXT)=:user_id")
        params["user_id"] = user_id
    rows = conn.execute(text(f"""
        SELECT {', '.join(selected_sql)}
        FROM {table} t
        LEFT JOIN actor_object_attributions a
          ON a.object_type = :object_type
         AND CAST(a.object_id AS TEXT) = CAST(t.id AS TEXT)
         AND CAST(a.household_id AS TEXT) = CAST(t.household_id AS TEXT)
        WHERE {' AND '.join(clauses)}
        {order_sql}
        LIMIT :limit
    """), params).mappings().all()
    return [dict(row) for row in rows]


def _diagnostics(conn: Connection, household_id: str) -> dict[str, Any]:
    inventory_cols = _columns(conn, "inventory")
    negative_count = 0
    if "household_id" in inventory_cols and "aantal" in inventory_cols:
        negative_count = _scalar(conn, "SELECT COUNT(*) FROM inventory WHERE CAST(household_id AS TEXT)=:household_id AND COALESCE(aantal,0)<0", {"household_id": household_id})
    receipt_count = _table_household_count(conn, "receipt_tables", household_id)
    inventory_count = _table_household_count(conn, "inventory", household_id)
    event_count = _table_household_count(conn, "inventory_events", household_id)
    unpack_count = _table_household_count(conn, "purchase_import_batches", household_id)
    attributed_count = _table_household_count(conn, "actor_object_attributions", household_id)
    flags = []
    if negative_count:
        flags.append({"severity": "warning", "code": "negative_inventory", "label": f"{negative_count} voorraadregel(s) met negatieve voorraad"})
    return {
        "receipt_count": receipt_count,
        "inventory_count": inventory_count,
        "inventory_event_count": event_count,
        "unpack_batch_count": unpack_count,
        "actor_attribution_count": attributed_count,
        "negative_inventory_count": negative_count,
        "last_receipt_at": _latest_value(conn, "receipt_tables", household_id, ("purchase_at", "imported_at", "created_at")),
        "last_inventory_event_at": _latest_value(conn, "inventory_events", household_id, ("effective_at", "recorded_at", "created_at")),
        "flags": flags,
    }


def create_superuser_household_router(engine: Engine) -> APIRouter:
    router = APIRouter()

    @router.get("/api/superuser/households")
    def list_households(request: Request, q: str = Query(default=""), status: str = Query(default="all"), limit: int = Query(default=100, ge=1, le=500)):
        with engine.begin() as conn:
            context = _require_superuser(conn, request.cookies.get(SESSION_COOKIE_NAME))
            id_col, name_col, status_col, created_col = _household_identity_columns(conn)
            select_parts = [f"CAST({id_col} AS TEXT) AS household_id"]
            select_parts.append(f"{name_col} AS name" if name_col else f"CAST({id_col} AS TEXT) AS name")
            select_parts.append(f"{status_col} AS status" if status_col else "'active' AS status")
            if created_col:
                select_parts.append(f"{created_col} AS created_at")
            clauses = [f"CAST({id_col} AS TEXT) <> '0'"]
            params: dict[str, Any] = {"limit": limit}
            query = str(q or "").strip().lower()
            if query:
                search_parts = [f"lower(CAST({id_col} AS TEXT)) LIKE :q"]
                if name_col:
                    search_parts.append(f"lower(COALESCE({name_col},'')) LIKE :q")
                clauses.append("(" + " OR ".join(search_parts) + ")")
                params["q"] = f"%{query}%"
            normalized_status = str(status or "all").strip().lower()
            if normalized_status != "all" and status_col:
                clauses.append(f"lower(COALESCE({status_col},'active'))=:status")
                params["status"] = normalized_status
            rows = conn.execute(text(f"SELECT {', '.join(select_parts)} FROM household_registry WHERE {' AND '.join(clauses)} ORDER BY {name_col or id_col} LIMIT :limit"), params).mappings().all()
            result = []
            for row in rows:
                hid = str(row.get("household_id") or "")
                item = dict(row)
                item["member_count"] = _table_household_count(conn, "household_memberships", hid)
                item["receipt_count"] = _table_household_count(conn, "receipt_tables", hid)
                item["last_active_at"] = _latest_value(conn, "server_sessions", hid, ("updated_at", "issued_at", "created_at"), household_column="active_household_id")
                result.append(item)
            _audit_view(conn, context=context, household_id="platform", action="superuser.households.searched", object_type="household_search", object_id=query or "all", metadata={"query": query, "status": normalized_status, "result_count": len(result)})
        return {"access": "read_only", "items": result, "total": len(result)}

    @router.get("/api/superuser/households/{household_id}")
    def household_overview(household_id: str, request: Request):
        with engine.begin() as conn:
            context = _require_superuser(conn, request.cookies.get(SESSION_COOKIE_NAME))
            if not _household_exists(conn, household_id):
                raise HTTPException(status_code=404, detail="Huishouden niet gevonden")
            ensure_actor_attribution_schema(conn)
            id_col, name_col, status_col, created_col = _household_identity_columns(conn)
            selected = [f"CAST({id_col} AS TEXT) AS household_id"]
            selected.append(f"{name_col} AS name" if name_col else f"CAST({id_col} AS TEXT) AS name")
            if status_col:
                selected.append(f"{status_col} AS status")
            if created_col:
                selected.append(f"{created_col} AS created_at")
            household = dict(conn.execute(text(f"SELECT {', '.join(selected)} FROM household_registry WHERE CAST({id_col} AS TEXT)=:id LIMIT 1"), {"id": household_id}).mappings().first() or {})
            payload = {"access": "read_only", "household": household, "members": _members(conn, household_id), "diagnostics": _diagnostics(conn, household_id), "screens": list(SCREEN_KEYS)}
            _audit_view(conn, context=context, household_id=household_id, action="superuser.household.viewed", object_type="household", metadata={"view": "overview"})
        return payload

    @router.get("/api/superuser/households/{household_id}/screens/{screen_key}")
    def household_screen(household_id: str, screen_key: str, request: Request, user_id: str | None = Query(default=None)):
        key = str(screen_key or "").strip().lower()
        selected_user_id = str(user_id or "").strip() or None
        if key not in SCREEN_KEYS:
            raise HTTPException(status_code=404, detail="Onbekend read-only Rezzerv-scherm")
        with engine.begin() as conn:
            context = _require_superuser(conn, request.cookies.get(SESSION_COOKIE_NAME))
            if not _household_exists(conn, household_id):
                raise HTTPException(status_code=404, detail="Huishouden niet gevonden")
            if selected_user_id and not _member_exists(conn, household_id, selected_user_id):
                raise HTTPException(status_code=404, detail="Gebruiker behoort niet tot dit huishouden")
            if key == "voorraad":
                rows = _actor_rows(
                    conn, "inventory_events", "inventory_event", household_id,
                    ("id", "article_id", "household_article_id", "article_name", "location_id", "location_label", "event_type", "quantity", "old_quantity", "new_quantity", "source", "note", "effective_at", "recorded_at", "created_at"),
                    order_candidates=("effective_at", "recorded_at", "created_at"), user_id=selected_user_id,
                )
            elif key == "bijna_op":
                cols = _columns(conn, "inventory")
                where = "COALESCE(aantal,0) <= 1" if "aantal" in cols else ""
                rows = _safe_rows(conn, "inventory", household_id, ("id", "naam", "aantal", "household_article_id", "status", "updated_at", "user_id"), where=where, user_id=selected_user_id)
            elif key == "kassa":
                rows = _actor_rows(
                    conn, "receipt_tables", "receipt", household_id,
                    ("id", "retailer", "winkel", "purchase_at", "purchase_date", "status", "source", "imported_at", "created_at"),
                    order_candidates=("purchase_at", "imported_at", "created_at"), user_id=selected_user_id,
                )
            elif key == "uitpakken":
                rows = _actor_rows(
                    conn, "purchase_import_batches", "unpack_batch", household_id,
                    ("id", "receipt_table_id", "source_reference", "status", "import_status", "purchase_date", "approved_at", "processed_at", "updated_at", "created_at"),
                    user_id=selected_user_id,
                )
            elif key == "winkelen":
                table = next((t for t in ("shopping_list", "shopping_list_items", "inkooplijst") if _columns(conn, t)), "")
                rows = _safe_rows(conn, table, household_id, ("id", "naam", "name", "artikel", "quantity", "aantal", "status", "updated_at", "created_at", "user_id"), user_id=selected_user_id) if table else []
            elif key == "prognoses":
                table = next((t for t in ("forecasts", "prognoses", "purchase_forecasts") if _columns(conn, t)), "")
                rows = _safe_rows(conn, table, household_id, ("id", "household_article_id", "article_name", "forecast", "quantity", "period", "updated_at", "created_at", "user_id"), user_id=selected_user_id) if table else []
            else:
                rows = []
            diagnostics = _diagnostics(conn, household_id)
            _audit_view(
                conn,
                context=context,
                household_id=household_id,
                action="superuser.household.screen_viewed",
                object_type="household_screen",
                object_id=key,
                metadata={"screen": key, "row_count": len(rows), "selected_user_id": selected_user_id},
            )
        return {"access": "read_only", "household_id": household_id, "selected_user_id": selected_user_id, "screen": key, "rows": rows, "diagnostics": diagnostics}

    return router
