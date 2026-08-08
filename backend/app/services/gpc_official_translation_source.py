"""Fetch an official translated GPC publication through the public GS1 browser client.

The optional ``gpcc`` dependency is imported lazily so normal Rezzerv runtime use
has no network dependency. Downloads are explicit operator actions and produce a
manifest with source metadata and SHA-256 evidence.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class OfficialGpcDownload:
    language_code: str
    publication_version: str
    format: str
    downloaded_at: str
    file_name: str
    file_sha256: str
    source: str = "GS1 GPC Browser"
    client: str = "gpcc"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _default_client():
    try:
        from gpcc import fetch_file, get_language, get_publications
    except ImportError as exc:
        raise RuntimeError(
            "De optionele dependency 'gpcc' ontbreekt. Installeer deze alleen in de beheerdersomgeving."
        ) from exc
    return get_language, get_publications, fetch_file


async def download_official_gpc_translation(
    output_dir: str | Path,
    *,
    language_code: str = "nl",
    file_format: str = "xml",
    client_factory: Callable[[], Awaitable[tuple[Any, Any, Any]]] = _default_client,
) -> dict:
    """Download the latest official publication for one language and write evidence."""
    language_code = language_code.strip().lower()
    file_format = file_format.strip().lower()
    if not language_code:
        raise ValueError("Taalcode ontbreekt")
    if file_format not in {"xml", "json", "xlsx"}:
        raise ValueError("Formaat moet xml, json of xlsx zijn")

    get_language, get_publications, fetch_file = await client_factory()
    language = await get_language(language_code)
    if not language:
        raise ValueError(f"GS1 GPC Browser bevat geen taalcode: {language_code}")
    publications = await get_publications(language)
    if not publications:
        raise ValueError(f"Geen GS1 GPC-publicatie gevonden voor taal: {language_code}")

    publication = publications[0]
    version = str(publication.version)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"gpc-{language_code}-{version}.{file_format}"
    with target.open("wb") as stream:
        await fetch_file(stream, publication, format=file_format)
    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError("GS1-download leverde geen bruikbaar bestand op")

    evidence = OfficialGpcDownload(
        language_code=language_code,
        publication_version=version,
        format=file_format,
        downloaded_at=datetime.now(timezone.utc).isoformat(),
        file_name=target.name,
        file_sha256=_sha256(target),
    )
    manifest = output / f"gpc-{language_code}-{version}.source.json"
    manifest.write_text(json.dumps(asdict(evidence), ensure_ascii=False, indent=2), encoding="utf-8")
    return {**asdict(evidence), "file_path": str(target), "manifest_path": str(manifest)}


def download_official_gpc_translation_sync(*args, **kwargs) -> dict:
    return asyncio.run(download_official_gpc_translation(*args, **kwargs))
