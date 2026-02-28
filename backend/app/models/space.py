from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.db.base import Base

class Space(Base):
    __tablename__ = "spaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    naam = Column(String, nullable=False)
    household_id = Column(UUID(as_uuid=True), ForeignKey("households.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())