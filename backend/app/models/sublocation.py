import uuid
from sqlalchemy import Column, String
from app.db import Base

class Sublocation(Base):
    __tablename__ = "sublocations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    naam = Column(String, nullable=False)
    space_id = Column(String)
