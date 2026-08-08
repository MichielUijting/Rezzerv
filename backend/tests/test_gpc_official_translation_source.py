from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.gpc_official_translation_source import download_official_gpc_translation


class Publication:
    version = "2025-11-27"


async def _client_factory():
    async def get_language(code):
        return {"code": code} if code == "nl" else None

    async def get_publications(language):
        return [Publication()]

    async def fetch_file(stream, publication, format):
        stream.write(b"<schema language='nl'/>")

    return get_language, get_publications, fetch_file


@pytest.mark.asyncio
async def test_download_writes_file_and_source_manifest(tmp_path: Path) -> None:
    result = await download_official_gpc_translation(
        tmp_path, language_code="nl", file_format="xml", client_factory=_client_factory
    )
    downloaded = Path(result["file_path"])
    manifest = Path(result["manifest_path"])
    assert downloaded.read_bytes() == b"<schema language='nl'/>"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["language_code"] == "nl"
    assert data["publication_version"] == "2025-11-27"
    assert data["file_sha256"] == hashlib.sha256(downloaded.read_bytes()).hexdigest()


@pytest.mark.asyncio
async def test_unknown_language_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="taalcode"):
        await download_official_gpc_translation(
            tmp_path, language_code="zz", client_factory=_client_factory
        )
