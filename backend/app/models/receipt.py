import uuid
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, Integer, Boolean, Text
from sqlalchemy.sql import func
from app.db import Base


class ReceiptSource(Base):
    __tablename__ = "receipt_sources"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    household_id = Column(String, ForeignKey("households.id"), nullable=False)
    type = Column(String, nullable=False)
    label = Column(String, nullable=False)
    source_path = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    last_scan_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class RawReceipt(Base):
    __tablename__ = "raw_receipts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    household_id = Column(String, ForeignKey("households.id"), nullable=False)
    source_id = Column(String, ForeignKey("receipt_sources.id"), nullable=True)
    original_filename = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    storage_path = Column(Text, nullable=False)
    sha256_hash = Column(String(64), nullable=False)
    imported_at = Column(DateTime, server_default=func.now())
    duplicate_of_raw_receipt_id = Column(String, ForeignKey("raw_receipts.id"), nullable=True)
    raw_status = Column(String, nullable=False, default="imported")
    created_at = Column(DateTime, server_default=func.now())


class ReceiptTable(Base):
    __tablename__ = "receipt_tables"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    raw_receipt_id = Column(String, ForeignKey("raw_receipts.id"), nullable=False, unique=True)
    household_id = Column(String, ForeignKey("households.id"), nullable=False)
    store_name = Column(String, nullable=True)
    store_branch = Column(String, nullable=True)
    purchase_at = Column(DateTime, nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(3), nullable=False, default="EUR")
    parse_status = Column(String, nullable=False, default="parsed")
    confidence_score = Column(Numeric(5, 4), nullable=True)
    line_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReceiptTableLine(Base):
    __tablename__ = "receipt_table_lines"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    receipt_table_id = Column(String, ForeignKey("receipt_tables.id"), nullable=False)
    line_index = Column(Integer, nullable=False)
    raw_label = Column(Text, nullable=False)
    normalized_label = Column(Text, nullable=True)
    quantity = Column(Numeric(12, 3), nullable=True)
    unit = Column(String, nullable=True)
    unit_price = Column(Numeric(12, 4), nullable=True)
    line_total = Column(Numeric(12, 2), nullable=True)
    discount_amount = Column(Numeric(12, 2), nullable=True)
    barcode = Column(String, nullable=True)
    article_match_status = Column(String, nullable=False, default="unmatched")
    matched_article_id = Column(String, nullable=True)
    confidence_score = Column(Numeric(5, 4), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReceiptProcessingRun(Base):
    __tablename__ = "receipt_processing_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String, ForeignKey("receipt_sources.id"), nullable=True)
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)
    files_found = Column(Integer, nullable=False, default=0)
    files_imported = Column(Integer, nullable=False, default=0)
    files_skipped = Column(Integer, nullable=False, default=0)
    files_failed = Column(Integer, nullable=False, default=0)
