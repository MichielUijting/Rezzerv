from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.db.base import Base

class Sublocation(Base):
    __tablename__ = "sublocations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    naam = Column(String, nullable=False)
    space_id = Column(UUID(as_uuid=True), ForeignKey("spaces.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())