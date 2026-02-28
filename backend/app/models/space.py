import uuid
from sqlalchemy import Column, String
from app.db import Base

class Space(Base):
    __tablename__ = "spaces"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    naam = Column(String, nullable=False)
    household_id = Column(String)
