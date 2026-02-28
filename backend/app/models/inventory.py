from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.db.base import Base

class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    naam = Column(String, nullable=False)
    aantal = Column(Integer, nullable=False)
    household_id = Column(UUID(as_uuid=True), ForeignKey("households.id"))
    space_id = Column(UUID(as_uuid=True), ForeignKey("spaces.id"))
    sublocation_id = Column(UUID(as_uuid=True), ForeignKey("sublocations.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())