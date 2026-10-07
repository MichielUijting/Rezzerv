from datetime import datetime, timezone

from sqlalchemy import create_engine, text

from app.services.household_dashboard_service import build_household_dashboard, build_household_dashboard_drilldown


NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                store_name TEXT,
                store_branch TEXT,
                purchase_at TEXT,
                total_amount NUMERIC,
                currency TEXT,
                parse_status TEXT,
                workflow_state TEXT,
                approved_at TEXT,
                deleted_at TEXT,
                created_at TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE receipt_table_lines (
                id TEXT PRIMARY KEY,
                receipt_table_id TEXT NOT NULL,
                quantity NUMERIC,
                raw_label TEXT,
                line_total NUMERIC,
                matched_article_id TEXT,
                matched_global_product_id TEXT,
                is_deleted INTEGER,
                inventory_eligible INTEGER,
                line_role TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE purchase_import_batches (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                source_type TEXT,
                source_reference TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE purchase_import_lines (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                processing_status TEXT,
                review_decision TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE shopping_lists (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                status TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE shopping_list_items (
                id TEXT PRIMARY KEY,
                shopping_list_id TEXT NOT NULL,
                household_id TEXT NOT NULL,
                checked INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_notifications (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                recipient_user_id TEXT,
                read_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                global_product_id TEXT,
                representative_image_gpc_brick_code TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE global_product_gpc_bricks (
                global_product_id TEXT PRIMARY KEY,
                brick_code TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE gpc_bricks (
                brick_code TEXT PRIMARY KEY,
                class_code TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE gpc_classes (
                class_code TEXT PRIMARY KEY,
                description TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE gpc_translations (
                entity_type TEXT,
                entity_code TEXT,
                language_code TEXT,
                translated_text TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE gpc_product_groups (
                gpc_brick_code TEXT PRIMARY KEY,
                gpc_brick_name TEXT,
                gpc_class_code TEXT,
                gpc_class_name TEXT,
                gpc_family_code TEXT,
                gpc_family_name TEXT,
                gpc_segment_code TEXT,
                gpc_segment_name TEXT,
                language_code TEXT,
                active INTEGER
            )
        """))
    return engine


def test_dashboard_counts_only_real_purchases_and_deduplicates_store_visit_per_day():
    engine = _engine()
    try:
        with engine.begin() as conn:
            receipts = [
                ("r1", "h1", "AH", "2026-10-01T10:00:00+00:00", 10, "approved", "active", "2026-10-01T10:05:00+00:00", None),
                ("r2", "h1", "AH", "2026-10-01T16:00:00+00:00", 5, "approved", "active", "2026-10-01T16:05:00+00:00", None),
                ("r3", "h1", "Lidl", "2026-09-22T10:00:00+00:00", 20, "approved", "active", "2026-09-22T10:05:00+00:00", None),
                ("r4", "h1", "Jumbo", "2026-10-01T11:00:00+00:00", 99, "approved", "archived", "2026-10-01T11:05:00+00:00", None),
                ("r5", "h1", "Plus", "2026-10-01T12:00:00+00:00", 88, "needs_review", "active", None, None),
                ("r6", "h1", "AH", "2025-10-01T10:00:00+00:00", 12, "approved", "active", "2025-10-01T10:05:00+00:00", None),
            ]
            for rid, household, store, purchase_at, total, status, workflow, approved_at, deleted_at in receipts:
                conn.execute(text("""
                    INSERT INTO receipt_tables(
                        id, household_id, store_name, purchase_at, total_amount, currency,
                        parse_status, workflow_state, approved_at, deleted_at, created_at
                    ) VALUES (
                        :id, :household_id, :store_name, :purchase_at, :total_amount, 'EUR',
                        :parse_status, :workflow_state, :approved_at, :deleted_at, :created_at
                    )
                """), {
                    "id": rid,
                    "household_id": household,
                    "store_name": store,
                    "purchase_at": purchase_at,
                    "total_amount": total,
                    "parse_status": status,
                    "workflow_state": workflow,
                    "approved_at": approved_at,
                    "deleted_at": deleted_at,
                    "created_at": purchase_at,
                })

            lines = [
                ("l1", "r1", 2, False, True, "product"),
                ("l2", "r1", 1, False, True, "product"),
                ("l3", "r1", 9, False, False, "discount"),
                ("l4", "r1", 7, True, True, "product"),
                ("l5", "r2", 3, False, True, "product"),
                ("l6", "r3", 4, False, True, "product"),
                ("l7", "r4", 50, False, True, "product"),
                ("l8", "r5", 40, False, True, "product"),
            ]
            for line in lines:
                conn.execute(text("""
                    INSERT INTO receipt_table_lines(
                        id, receipt_table_id, quantity, raw_label, line_total,
                        matched_article_id, matched_global_product_id,
                        is_deleted, inventory_eligible, line_role
                    ) VALUES (
                        :id, :receipt, :quantity, :label, :line_total,
                        :article_id, :product_id, :deleted, :eligible, :role
                    )
                """), {
                    "id": line[0], "receipt": line[1], "quantity": line[2],
                    "label": f"Artikel {line[0]}",
                    "line_total": float(line[2]),
                    "article_id": ("ha-l1" if line[0] == "l6" else f"ha-{line[0]}") if line[4] else None,
                    "product_id": (None if line[0] == "l5" else f"gp-{line[0]}") if line[4] else None,
                    "deleted": line[3], "eligible": line[4], "role": line[5],
                })

            conn.execute(text("""
                INSERT INTO gpc_classes(class_code, description) VALUES
                  ('10000001', 'Food'),
                  ('10000002', 'Fruit')
            """))
            conn.execute(text("""
                INSERT INTO gpc_bricks(brick_code, class_code) VALUES
                  ('20000001', '10000001'),
                  ('20000002', '10000002')
            """))
            conn.execute(text("""
                INSERT INTO global_product_gpc_bricks(global_product_id, brick_code) VALUES
                  ('gp-l1', '20000001'),
                  ('gp-l2', '20000001'),
                  ('gp-l5', '20000002'),
                  ('gp-l6', '20000001')
            """))
            conn.execute(text("""
                INSERT INTO gpc_translations(entity_type, entity_code, language_code, translated_text) VALUES
                  ('class', '10000001', 'nl', 'Voeding'),
                  ('class', '10000002', 'nl', 'Fruit')
            """))
            conn.execute(text("""
                INSERT INTO gpc_product_groups(
                    gpc_brick_code, gpc_brick_name,
                    gpc_class_code, gpc_class_name,
                    gpc_family_code, gpc_family_name,
                    gpc_segment_code, gpc_segment_name,
                    language_code, active
                ) VALUES
                  ('20000001', 'Algemene voeding', '10000001', 'Voeding', '30000001', 'Voedingsmiddelen', '40000001', 'Levensmiddelen', 'nl', 1),
                  ('20000002', 'Vers fruit', '10000002', 'Fruit', '30000002', 'Verse groenten en fruit', '40000001', 'Levensmiddelen', 'nl', 1)
            """))
            conn.execute(text("""
                INSERT INTO household_articles(
                    id, household_id, global_product_id, representative_image_gpc_brick_code
                ) VALUES
                  ('ha-l5', 'h1', NULL, '20000002')
            """))

            # r1 staat in Uitpakken: twee regels nog te verwerken, één al verwerkt.
            conn.execute(text("""
                INSERT INTO purchase_import_batches(id, household_id, source_type, source_reference)
                VALUES ('b1', 'h1', 'receipt', 'receipt:r1')
            """))
            conn.execute(text("""
                INSERT INTO purchase_import_lines(id, batch_id, processing_status, review_decision)
                VALUES
                  ('p1', 'b1', 'pending', 'selected'),
                  ('p2', 'b1', 'failed', 'selected'),
                  ('p3', 'b1', 'processed', 'selected'),
                  ('p4', 'b1', 'pending', 'removed')
            """))

            # r3 is volledig verwerkt en telt niet meer bij Nog opbergen.
            conn.execute(text("""
                INSERT INTO purchase_import_batches(id, household_id, source_type, source_reference)
                VALUES ('b3', 'h1', 'receipt', 'receipt:r3')
            """))
            conn.execute(text("""
                INSERT INTO purchase_import_lines(id, batch_id, processing_status, review_decision)
                VALUES ('p5', 'b3', 'processed', 'selected')
            """))

            conn.execute(text("INSERT INTO shopping_lists(id, household_id, status) VALUES ('s1', 'h1', 'active')"))
            conn.execute(text("""
                INSERT INTO shopping_list_items(id, shopping_list_id, household_id, checked)
                VALUES
                  ('sli1', 's1', 'h1', FALSE),
                  ('sli2', 's1', 'h1', TRUE)
            """))
            conn.execute(text("""
                INSERT INTO household_notifications(id, household_id, recipient_user_id, read_at)
                VALUES
                  ('n1', 'h1', 'u1', NULL),
                  ('n2', 'h1', NULL, '2026-10-01T10:00:00+00:00')
            """))

            dashboard = build_household_dashboard(conn, household_id="h1", user_id="u1", now=NOW)

        assert dashboard["purchases"]["current"] == 6.0
        assert dashboard["purchases"]["previous"] == 4.0
        assert dashboard["spend"]["current"] == 15.0
        assert dashboard["spend"]["previous"] == 20.0
        assert len(dashboard["purchases"]["views"]["days"]) == 4
        assert len(dashboard["purchases"]["views"]["weeks"]) == 4
        assert len(dashboard["purchases"]["views"]["months"]) == 4
        assert len(dashboard["spend_year_over_year"]["views"]["days"]) == 4
        assert dashboard["spend_year_over_year"]["views"]["days"][-2]["current"] == 15.0
        assert dashboard["spend_year_over_year"]["views"]["days"][-2]["previous"] == 12.0
        assert len(dashboard["spend_year_over_year"]["views"]["weeks"]) == 4
        assert len(dashboard["spend_year_over_year"]["views"]["months"]) == 4
        assert [row["receipt_id"] for row in dashboard["purchases"]["receipts"]] == ["r2", "r1"]
        assert dashboard["purchases"]["receipts"][0]["articles"][0]["label"] == "Artikel l5"
        assert dashboard["purchases"]["receipts"][0]["articles"][0]["household_article_id"] == "ha-l5"
        assert len(dashboard["purchases"]["receipts"][1]["articles"]) == 2
        assert dashboard["spend"]["receipts"] == dashboard["purchases"]["receipts"]
        day_groups = dashboard["spend"]["group_views"]["days"]
        assert [item["label"] for item in day_groups["legend"]] == ["Voedingsmiddelen", "Verse groenten en fruit"]
        assert day_groups["points"][-2]["current"] == 15.0
        assert sum(item["value"] for item in day_groups["points"][-2]["current_segments"]) == 15.0
        assert dashboard["spend_year_over_year"]["group_views"]["days"]["points"][-2]["previous"] == 12.0

        # Twee AH-bonnen op dezelfde kalenderdag vormen één winkelbezoek.
        assert dashboard["stores"]["unique"] == 1
        assert dashboard["stores"]["visits"] == 1
        assert dashboard["stores"]["items"][0]["name"] == "AH"
        assert dashboard["stores"]["items"][0]["spend"] == 15.0
        assert len(dashboard["stores"]["views"]["days"]["points"]) == 4
        assert len(dashboard["stores"]["views"]["weeks"]["points"]) == 4
        assert len(dashboard["stores"]["views"]["months"]["points"]) == 4
        assert [row["receipt_id"] for row in dashboard["stores"]["items"][0]["receipts"]] == ["r2", "r1"]
        assert {row["receipt_id"] for row in dashboard["forecast"]["basis_receipts"]} >= {"r1", "r2", "r3"}
        assert dashboard["forecast"]["method"].startswith("Herhalingskoop")
        assert dashboard["forecast"]["total"] == 9.0
        assert len(dashboard["forecast"]["items"]) >= 3
        assert {item["household_article_id"] for item in dashboard["forecast"]["items"]} == {"ha-l1"}
        assert dashboard["forecast"]["items"][0]["cadence_days"] == 9
        assert len(dashboard["forecast"]["views"]["days"]) == 4
        assert len(dashboard["forecast"]["views"]["weeks"]) == 4
        assert len(dashboard["forecast"]["views"]["months"]) == 4

        assert dashboard["status"]["notifications"] == 1

        # Boodschappen telt alle regels op de actieve lijst: zowel "Nog te kopen"
        # (checked=False) als "In winkelwagen" (checked=True).
        assert dashboard["status"]["shopping"] == 2

        # Bonnen open telt unieke bonnen, niet bonregels:
        # r2 en de nog niet goedgekeurde r5 staan in Kassa; r1 staat in Uitpakken
        # en telt daar precies één keer ondanks meerdere nog open regels.
        assert dashboard["status"]["put_away_kassa"] == 2
        assert dashboard["status"]["put_away_unpack"] == 1
        assert dashboard["status"]["put_away"] == 3
        assert dashboard["status"]["put_away_route"] == "/kassa?view=bonnen"
    finally:
        engine.dispose()


def test_dashboard_drilldown_selects_exact_bar_period_and_deduplicates_store_visit():
    engine = _engine()
    try:
        with engine.begin() as conn:
            receipts = [
                ("r-current-1", "h1", "AH", "2026-10-02T09:00:00+00:00", 10),
                ("r-current-2", "h1", "AH", "2026-10-02T16:00:00+00:00", 5),
                ("r-previous", "h1", "Lidl", "2026-09-28T10:00:00+00:00", 7),
                ("r-year", "h1", "Jumbo", "2025-10-02T10:00:00+00:00", 12),
            ]
            for rid, household, store, purchase_at, total in receipts:
                conn.execute(text("""
                    INSERT INTO receipt_tables(
                        id, household_id, store_name, purchase_at, total_amount, currency,
                        parse_status, workflow_state, approved_at, deleted_at, created_at
                    ) VALUES (
                        :id, :household_id, :store_name, :purchase_at, :total_amount, 'EUR',
                        'approved', 'active', :purchase_at, NULL, :purchase_at
                    )
                """), {
                    "id": rid,
                    "household_id": household,
                    "store_name": store,
                    "purchase_at": purchase_at,
                    "total_amount": total,
                })
                conn.execute(text("""
                    INSERT INTO receipt_table_lines(
                        id, receipt_table_id, quantity, raw_label, line_total,
                        matched_article_id, matched_global_product_id,
                        is_deleted, inventory_eligible, line_role
                    ) VALUES (
                        :id, :receipt_table_id, 1, :label, :line_total,
                        NULL, NULL, 0, 1, 'product'
                    )
                """), {
                    "id": "line-" + rid,
                    "receipt_table_id": rid,
                    "label": rid,
                    "line_total": total,
                })

            current = build_household_dashboard_drilldown(
                conn,
                household_id="h1",
                user_id="u1",
                metric="spend",
                granularity="days",
                bucket_index=3,
                series="current",
                comparison="previous",
                now=NOW,
            )
            assert current["label"] == "02-10-2026"
            assert current["spend"] == 15.0
            assert len(current["receipts"]) == 2
            assert len(current["stores"]) == 1
            assert current["stores"][0]["visits"] == 1

            unclassified = build_household_dashboard_drilldown(
                conn,
                household_id="h1",
                user_id="u1",
                metric="spend",
                granularity="days",
                bucket_index=3,
                series="current",
                comparison="previous",
                group_key="unclassified",
                now=NOW,
            )
            assert unclassified["group_label"] == "Niet ingedeeld"
            assert unclassified["spend"] == 15.0

            previous = build_household_dashboard_drilldown(
                conn,
                household_id="h1",
                user_id="u1",
                metric="spend",
                granularity="days",
                bucket_index=3,
                series="previous",
                comparison="previous",
                now=NOW,
            )
            assert previous["label"] == "28-09-2026"
            assert previous["spend"] == 7.0

            previous_year = build_household_dashboard_drilldown(
                conn,
                household_id="h1",
                user_id="u1",
                metric="spend",
                granularity="days",
                bucket_index=3,
                series="previous",
                comparison="year",
                now=NOW,
            )
            assert previous_year["label"] == "02-10-2025"
            assert previous_year["spend"] == 12.0
    finally:
        engine.dispose()
