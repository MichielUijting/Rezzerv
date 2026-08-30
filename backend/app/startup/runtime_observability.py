"""Startup observability for the configured runtime datastore."""

import logging

from app.db import get_runtime_datastore_info


logger = logging.getLogger("rezzerv.api")


async def log_runtime_datastore_configuration_event() -> None:
    datastore_info = get_runtime_datastore_info()
    logger.info("Datastore: %s", datastore_info.get("datastore", "onbekend"))
    logger.info(
        "Database: %s",
        datastore_info.get("database")
        or datastore_info.get("database_url")
        or "onbekend",
    )
    if datastore_info.get("storage"):
        logger.info("Storage: %s", datastore_info["storage"])
