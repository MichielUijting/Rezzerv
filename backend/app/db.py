import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/rezzerv.db")
SQLITE_RUNTIME_VOLUME = os.getenv("SQLITE_RUNTIME_VOLUME", "sqlite_data").strip() or 'sqlite_data'

engine_kwargs = {}
SQLITE_DATABASE_PATH = None
DATASTORE_KIND = 'postgresql' if DATABASE_URL.startswith('postgresql') else 'sqlite' if DATABASE_URL.startswith('sqlite') else 'other'
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    sqlite_path = DATABASE_URL.replace("sqlite:////", "/", 1) if DATABASE_URL.startswith("sqlite:////") else DATABASE_URL.replace("sqlite:///", "", 1)
    if sqlite_path and sqlite_path != ':memory:':
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        SQLITE_DATABASE_PATH = sqlite_path

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def get_runtime_datastore_info() -> dict:
    info = {
        'datastore': DATASTORE_KIND,
        'database_url': DATABASE_URL,
    }
    if DATASTORE_KIND == 'sqlite':
        info['database'] = SQLITE_DATABASE_PATH or ':memory:'
        info['storage'] = SQLITE_RUNTIME_VOLUME
    return info
