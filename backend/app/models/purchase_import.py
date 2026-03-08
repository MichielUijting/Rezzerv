import uuid
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey
from sqlalchemy.sql import func
from app.db import Base


class PurchaseImportBatch(Base):
    __tablename__ = "purchase_import_batches"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    household_id = Column(String, nullable=False)
    store_provider_id = Column(String, nullable=False)
    connection_id = Column(String, ForeignKey("household_store_connections.id"), nullable=False)
    source_type = Column(String, nullable=False, default="mock")
    source_reference = Column(String, nullable=True)
    purchase_date_from = Column(DateTime, nullable=True)
    purchase_date_to = Column(DateTime, nullable=True)
    import_status = Column(String, nullable=False, default="new")
    raw_payload = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    processed_at = Column(DateTime, nullable=True)


class PurchaseImportLine(Base):
    __tablename__ = "purchase_import_lines"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(String, ForeignKey("purchase_import_batches.id"), nullable=False)
    external_line_ref = Column(String, nullable=True)
    external_article_code = Column(String, nullable=True)
    article_name_raw = Column(String, nullable=False)
    brand_raw = Column(String, nullable=True)
    quantity_raw = Column(Numeric(10, 2), nullable=False)
    unit_raw = Column(String, nullable=True)
    line_price_raw = Column(Numeric(10, 2), nullable=True)
    currency_code = Column(String, nullable=True)
    match_status = Column(String, nullable=False, default="unmatched")
    matched_global_article_id = Column(String, nullable=True)
    target_location_id = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
