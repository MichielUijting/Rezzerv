from __future__ import annotations

from sqlalchemy import text


def backfill_catalog_product_images_from_enrichments(engine) -> int:
    """Fill missing central Catalogus images from already persisted enrichment data.

    Existing non-empty Catalogus images are never overwritten. This backfill performs
    no network requests; it only reuses product images that were previously stored in
    product_enrichments.
    """
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    pe.global_product_id,
                    pe.image_url
                FROM product_enrichments pe
                JOIN global_products gp
                  ON gp.id = pe.global_product_id
                WHERE pe.global_product_id IS NOT NULL
                  AND pe.lookup_status = 'found'
                  AND COALESCE(trim(pe.image_url), '') <> ''
                  AND COALESCE(trim(gp.image_url), '') = ''
                  AND lower(COALESCE(gp.status, 'active')) = 'active'
                ORDER BY
                    pe.global_product_id,
                    pe.fetched_at DESC NULLS LAST,
                    pe.id DESC
                """
            )
        ).mappings().all()

        selected: dict[str, str] = {}
        for row in rows:
            global_product_id = str(row.get("global_product_id") or "").strip()
            image_url = str(row.get("image_url") or "").strip()
            if global_product_id and image_url and global_product_id not in selected:
                selected[global_product_id] = image_url

        updated = 0
        for global_product_id, image_url in selected.items():
            result = conn.execute(
                text(
                    """
                    UPDATE global_products
                    SET image_url = :image_url,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :global_product_id
                      AND COALESCE(trim(image_url), '') = ''
                    """
                ),
                {
                    "global_product_id": global_product_id,
                    "image_url": image_url,
                },
            )
            updated += int(getattr(result, "rowcount", 0) or 0)

        return updated
