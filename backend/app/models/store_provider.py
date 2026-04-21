import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.db import Base


class StoreProvider(Base):
    __tablename__ = "store_providers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")
    import_mode = Column(String, nullable=False, default="mock")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
