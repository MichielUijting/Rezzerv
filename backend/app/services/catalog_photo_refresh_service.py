"""Bounded, exact-GTIN OFF photo enrichment for missing central Catalogus images.

No user-facing read waits for OFF. No names, synonyms, classifications, or existing
images are modified. Network failures do not create negative product identities.
"""
from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import urlsplit

from sqlalchemy import text

from app.services.gtin_validation_service import is_valid_gtin
from app.services.off_search_service import lookup_off_product_by_gtin

_LOG = logging.getLogger(__name__)
_ALLOWED_IMAGE_HOSTS = frozenset({"images.openfoodfacts.org", "static.openfoodfacts.org"})
_MAX_BATCH = 5
_START_DELAY_SECONDS = 300
_INTERVAL_SECONDS = 3600


def _trusted_off_image_url(value):
    """Only HTTPS images delivered from OFF's documented image domains."""
    candidate = str(value or "").strip()
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ""
    if (
        parsed.scheme != "https"
        or parsed.hostname not in _ALLOWED_IMAGE_HOSTS
        or parsed.username or parsed.password
        or parsed.port not in (None, 443)
        or not parsed.path.startswith("/")
    ):
        return ""
    return candidate


def refresh_missing_catalog_photos(engine, *, lookup=None, attempted=None, limit=_MAX_BATCH):
    """Refresh a small batch of empty Catalogus images. No request-side network IO.

    attempted is per-worker session memory: a missing or photo-less barcode is
    not requested repeatedly every hour. OFF outages are retried next interval.
    """
    lookup = lookup or lookup_off_product_by_gtin
    attempted = attempted if attempted is not None else set()
    limit = max(0, min(int(limit), _MAX_BATCH))
    outcome = {"queried": 0, "updated": 0, "no_photo": 0,
               "invalid_barcode": 0, "unavailable": 0}
    if not limit:
        return outcome
    # Every candidate is a CENTRAL product identity, never a household article.
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, primary_gtin
              FROM global_products
             WHERE lower(COALESCE(status, 'active')) = 'active'
               AND COALESCE(trim(image_url), '') = ''
               AND COALESCE(trim(primary_gtin), '') <> ''
             ORDER BY updated_at ASC NULLS FIRST, id ASC
             LIMIT 500
        """)).mappings().all()

    for row in rows:
        if outcome["queried"] >= limit:
            break
        product_id = str(row.get("id") or "").strip()
        gtin = str(row.get("primary_gtin") or "").strip()
        if not product_id or product_id in attempted:
            continue
        if not is_valid_gtin(gtin) or not gtin.isdigit():
            attempted.add(product_id)
            outcome["invalid_barcode"] += 1
            continue
        try:
            result = lookup(gtin)
        except Exception:
            _LOG.warning("OFF photo lookup failed for a Catalogus barcode", exc_info=True)
            outcome["unavailable"] += 1
            break
        if result.get("status") == "external_source_unavailable":
            outcome["unavailable"] += 1
            break
        attempted.add(product_id)
        outcome["queried"] += 1
        if result.get("status") != "found":
            outcome["no_photo"] += 1
            continue
        product = result.get("product") or {}
        # The exact-GTIN service already checks the OFF product code; enforce
        # that contract here too, guarding future adapter changes.
        received = str(result.get("gtin") or "").strip()
        expected = gtin[1:] if len(gtin) == 14 and gtin.startswith("0") else gtin
        image = _trusted_off_image_url(product.get("image_url"))
        if received != expected or not image:
            outcome["no_photo"] += 1
            continue
        with engine.begin() as conn:
            update = conn.execute(text("""
                UPDATE global_products
                   SET image_url = :image_url, updated_at = CURRENT_TIMESTAMP
                 WHERE id = :product_id AND primary_gtin = :gtin
                   AND lower(COALESCE(status, 'active')) = 'active'
                   AND COALESCE(trim(image_url), '') = ''
            """), {"product_id": product_id, "gtin": gtin, "image_url": image})
            outcome["updated"] += max(0, int(update.rowcount or 0))
    return outcome


def register_catalog_photo_refresh(app, engine):
    """Install nonblocking, limited periodic refresh after runtime starts.

    Uses an ASGI lifecycle task, never an alternate Docker/process scheduler.
    Disable via REZZERV_CATALOG_PHOTO_AUTOFILL_ENABLED=0 for offline deployments.
    """
    state = {"task": None}
    async def worker():
        attempted = set()
        await asyncio.sleep(_START_DELAY_SECONDS)
        while True:
            try:
                outcome = await asyncio.to_thread(
                    refresh_missing_catalog_photos, engine, attempted=attempted
                )
                if any(outcome.values()):
                    _LOG.info("Catalogusfoto's OFF-bijvullen: %s", outcome)
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOG.exception("Catalogusfoto's OFF-bijvullen overgeslagen")
            await asyncio.sleep(_INTERVAL_SECONDS)

    async def on_startup():
        enabled = os.getenv("REZZERV_CATALOG_PHOTO_AUTOFILL_ENABLED", "1").strip().lower()
        if enabled in {"0", "false", "no", "off"}:
            return
        if getattr(getattr(engine, "dialect", None), "name", "") != "postgresql":
            return
        if state["task"] is None or state["task"].done():
            state["task"] = asyncio.create_task(worker())

    async def on_shutdown():
        task = state["task"]
        state["task"] = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app.add_event_handler("startup", on_startup)
    app.add_event_handler("shutdown", on_shutdown)
