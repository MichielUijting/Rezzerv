import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/rezzerv.db")

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    sqlite_path = DATABASE_URL.replace("sqlite:////", "/", 1) if DATABASE_URL.startswith("sqlite:////") else DATABASE_URL.replace("sqlite:///", "", 1)
    if sqlite_path and sqlite_path != ':memory:':
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
