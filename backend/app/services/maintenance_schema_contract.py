"""Alembic-owned maintenance schema specification (no runtime DDL).

The actual Alembic revision MUST be based on the unique current repository
head after complete graph verification. This module intentionally performs
no CREATE, ALTER, DROP or automatic migration.
"""
from __future__ import annotations

import sqlalchemy as sa

maintenance_metadata = sa.MetaData()

maintenance_control = sa.Table(
    "maintenance_control", maintenance_metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("state", sa.String(20), nullable=False),
    sa.Column("generation", sa.Integer, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    sa.CheckConstraint("id = 1", name="ck_maintenance_control_singleton"),
    sa.CheckConstraint("generation >= 0", name="ck_maintenance_generation_nonnegative"),
    sa.CheckConstraint(
        "state IN ('normal','announced','draining','locked','verifying','blocked')",
        name="ck_maintenance_valid_state",
    ),
)

maintenance_operations = sa.Table(
    "maintenance_operations", maintenance_metadata,
    sa.Column("operation_id", sa.String(36), primary_key=True),
    sa.Column("generation", sa.Integer, nullable=False),
    sa.Column("kind", sa.String(100), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.CheckConstraint("generation >= 0", name="ck_maintenance_operation_generation"),
    sa.CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name="ck_maintenance_operation_dates"),
)
sa.Index("ix_maintenance_operations_unfinished", maintenance_operations.c.started_at,
         postgresql_where=maintenance_operations.c.finished_at.is_(None))
