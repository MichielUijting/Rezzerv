"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Backend application module
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

import uuid
from sqlalchemy import Column, String, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.db import Base


class HouseholdStoreConnection(Base):
    __tablename__ = "household_store_connections"
    __table_args__ = (
        UniqueConstraint("household_id", "store_provider_id", name="uq_household_store_provider"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    household_id = Column(String, nullable=False)
    store_provider_id = Column(String, nullable=False)
    connection_status = Column(String, nullable=False, default="active")
    external_account_ref = Column(String, nullable=True)
    consent_scope_json = Column(String, nullable=True)
    linked_at = Column(DateTime, server_default=func.now())
    last_sync_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
