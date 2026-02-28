import uuid
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from app.db import Base

class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    naam = Column(String, nullable=False)
    aantal = Column(Integer, nullable=False)
    household_id = Column(String)
    space_id = Column(String)
    sublocation_id = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
