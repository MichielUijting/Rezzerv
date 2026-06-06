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
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.db import Base

class Household(Base):
    __tablename__ = "households"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    naam = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
