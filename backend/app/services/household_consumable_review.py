"""Explicit, household-scoped review of historical consumable classifications.

Legacy stored False/NULL values do not encode whether a user set them. Never
rewrite that history speculatively. A household administrator may explicitly
choose the classification; that decision and its audit history are persisted in
existing canonical household_article_settings alongside the article update.
All writes belong to the caller's single database transaction.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

from sqlalchemy import text

from app.services.product_taxonomy_store import infer_food_consumable_from_seed

ORIGIN_KEY = "consumable_origin"
HISTORY_KEY = "consumable_review_history"
EXPLICIT = "explicit_user"
MAX_HISTORY = 5000


class ReviewConflict(ValueError):
    pass


class ReviewNotFound(LookupError):
    pass


def _require_household_and_actor(household_id: str, actor_id: str | None = None):
    owner = str(household_id or "").strip()
    if not owner or owner == "0":
        raise ValueError("Een geldig huishouden is vereist")
    if actor_id is not None and not str(actor_id).strip():
        raise ValueError("Een geauthenticeerde beoordelaar is vereist")
    return owner


def _state(value) -> str:
    if value is None:
        return "unknown"
    return "true" if bool(value) else "false"


def list_consumable_review_candidates(conn, *, household_id: str,
                                      limit: int = 10, offset: int = 0) -> dict:
    """Show uncertain legacy false/unknown items without changing data."""
    owner = _require_household_and_actor(household_id)
    if not 1 <= int(limit) <= 50 or not 0 <= int(offset) <= 100000:
        raise ValueError("Ongeldige paginering voor classificatiebeoordeling")
    params = {"household_id": owner, "origin_key": ORIGIN_KEY,
              "limit": int(limit), "offset": int(offset)}
    filter_sql = """
        FROM household_articles ha
        LEFT JOIN household_article_settings hs
          ON hs.household_article_id = ha.id AND hs.setting_key = :origin_key
        WHERE ha.household_id = :household_id
          AND COALESCE(ha.status, 'active') = 'active'
          AND (ha.consumable IS NULL OR ha.consumable = 0)
          AND hs.id IS NULL
    """
    count = conn.execute(text("SELECT COUNT(*) " + filter_sql), params).scalar_one()
    rows = conn.execute(text("""
        SELECT ha.id, ha.naam, ha.consumable
    """ + filter_sql + """
        ORDER BY CASE WHEN ha.consumable IS FALSE THEN 0 ELSE 1 END,
                 LOWER(TRIM(ha.naam)), ha.id
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()
    return {
        "total": int(count or 0),
        "limit": int(limit),
        "offset": int(offset),
        "items": [
            {
                "id": str(row["id"]),
                "naam": str(row.get("naam") or ""),
                "consumable": (
                    None if row.get("consumable") is None
                    else bool(row["consumable"])
                ),
                # Informational hint; neither proof of identity nor a write.
                "food_hint": infer_food_consumable_from_seed(row.get("naam")) is True,
                "provenance": "unknown",
            }
            for row in rows
        ],
    }


def _read_setting(conn, article_id: str, setting_key: str):
    return conn.execute(text("""
        SELECT setting_value
        FROM household_article_settings
        WHERE household_article_id = :article_id AND setting_key = :setting_key
        FOR UPDATE
    """), {"article_id": article_id, "setting_key": setting_key}).mappings().first()


def _put_setting(conn, article_id: str, setting_key: str, value):
    conn.execute(text("""
        INSERT INTO household_article_settings (
            id, household_article_id, setting_key, setting_value,
            created_at, updated_at
        ) VALUES (
            :id, :article_id, :setting_key, :setting_value,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT(household_article_id, setting_key) DO UPDATE
        SET setting_value = excluded.setting_value, updated_at = CURRENT_TIMESTAMP
    """), {
        "id": str(uuid4()),
        "article_id": article_id,
        "setting_key": setting_key,
        "setting_value": json.dumps(value, sort_keys=True),
    })


def record_explicit_consumable_review(
    conn, *, household_id: str, article_id: str,
    actor_id: str, consumable: bool, expected_state: str,
) -> dict:
    """Transactional, audited, guarded explicit choice; no stock write."""
    owner = _require_household_and_actor(household_id, actor_id)
    identifier = str(article_id or "").strip()
    if not identifier:
        raise ValueError("Het artikel-ID is verplicht")
    if expected_state not in {"unknown", "true", "false"}:
        raise ValueError("Ongeldige verwachte classificatie")
    if not isinstance(consumable, bool):
        raise ValueError("Een expliciete Ja/Nee-keuze is verplicht")

    article = conn.execute(text("""
        SELECT id, consumable
        FROM household_articles
        WHERE household_id = :household_id AND id = :article_id
          AND COALESCE(status, 'active') = 'active'
        FOR UPDATE
    """), {"household_id": owner, "article_id": identifier}).mappings().first()
    if not article:
        raise ReviewNotFound("Artikel ontbreekt of hoort bij een ander huishouden")
    previous = (
        None if article.get("consumable") is None
        else bool(article["consumable"])
    )
    if _state(previous) != expected_state:
        raise ReviewConflict("De classificatie is intussen gewijzigd; laad de lijst opnieuw")

    original_origin = _read_setting(conn, identifier, ORIGIN_KEY)
    origin = None
    if original_origin and original_origin.get("setting_value"):
        try:
            origin = json.loads(original_origin["setting_value"])
        except (ValueError, TypeError) as exc:
            raise ReviewConflict("De bestaande herkomst is ongeldig; geen gegevens gewijzigd") from exc
    if origin is not None and not isinstance(origin, dict):
        raise ReviewConflict("De bestaande herkomst is niet veilig te beoordelen")

    if previous is consumable and origin and origin.get("kind") == EXPLICIT:
        return {"status": "unchanged", "article_id": identifier,
                "consumable": consumable, "provenance": EXPLICIT}

    history_row = _read_setting(conn, identifier, HISTORY_KEY)
    try:
        history = json.loads(history_row["setting_value"]) if history_row else []
    except (ValueError, TypeError) as exc:
        raise ReviewConflict("Beoordelingshistorie is ongeldig; geen gegevens gewijzigd") from exc
    if not isinstance(history, list) or len(history) >= MAX_HISTORY:
        raise ReviewConflict("Beoordelingshistorie kon niet veilig worden uitgebreid")

    moment = datetime.now(timezone.utc).isoformat()
    history.append({
        "actor_id": str(actor_id).strip(),
        "at": moment,
        "old": previous,
        "new": consumable,
        "previous_provenance": origin.get("kind") if origin else None,
    })
    updated = conn.execute(text("""
        UPDATE household_articles
        SET consumable = :consumable, updated_at = CURRENT_TIMESTAMP
        WHERE household_id = :household_id AND id = :article_id
          AND COALESCE(status, 'active') = 'active'
    """), {
        "consumable": int(consumable),  # canonical integer 0/1 column on PostgreSQL
        "household_id": owner,
        "article_id": identifier,
    })
    if updated.rowcount != 1:
        raise ReviewConflict("Artikel is intussen gewijzigd; gehele transactie afgebroken")
    _put_setting(conn, identifier, HISTORY_KEY, history)
    _put_setting(conn, identifier, ORIGIN_KEY, {
        "kind": EXPLICIT, "actor_id": str(actor_id).strip(), "at": moment,
    })
    return {"status": "reviewed", "article_id": identifier,
            "consumable": consumable, "provenance": EXPLICIT}

CLASSIFICATION_ORIGINS = {"automatic_positive", "caller_supplied"}


def record_classification_origin(
    conn, *, household_id: str, article_id: str, kind: str,
) -> None:
    """Persist a proven automatic/caller source without overwriting user provenance.

    The owning transaction has already created or positively classified the
    article. An explicit later administrator choice always takes precedence.
    """
    owner = _require_household_and_actor(household_id)
    identifier = str(article_id or "").strip()
    if not identifier or kind not in CLASSIFICATION_ORIGINS:
        raise ValueError("Ongeldige classificatiebron")
    conn.execute(text("""
        INSERT INTO household_article_settings (
            id, household_article_id, setting_key, setting_value,
            created_at, updated_at
        )
        SELECT :id, ha.id, :key, :value,
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM household_articles ha
        WHERE ha.household_id = :household_id AND ha.id = :article_id
          AND ha.consumable IS NOT NULL
        ON CONFLICT (household_article_id, setting_key) DO NOTHING
    """), {
        "id": str(uuid4()),
        "article_id": identifier,
        "household_id": owner,
        "key": ORIGIN_KEY,
        "value": json.dumps({
            "kind": kind,
            "at": datetime.now(timezone.utc).isoformat(),
        }, sort_keys=True),
    })
