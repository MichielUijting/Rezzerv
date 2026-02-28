import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.db import Base

class Household(Base):
    __tablename__ = "households"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    naam = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
