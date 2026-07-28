"""Import a caller-supplied GS1 GPC XML file into the Rezzerv database.

Example from the backend container or backend working directory:
    python -m app.cli.import_gpc_catalog /app/data/gpc/nl-v20241202.xml \
        --language nl --source-version 20241202
"""

from __future__ import annotations

import argparse
import json
import sys

from app.db import get_runtime_datastore_info
from app.services.gpc_catalog_service import import_gpc_xml


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Importeer een GS1 GPC XML-bestand in de actieve Rezzerv-database."
    )
    parser.add_argument("xml_file", help="Pad naar het lokaal beschikbare GPC XML-bestand")
    parser.add_argument("--language", default="nl", help="Taalcode van het bestand (standaard: nl)")
    parser.add_argument("--source-version", default=None, help="GS1 GPC bronversie, bijvoorbeeld 20241202")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = import_gpc_xml(
            args.xml_file,
            language_code=args.language,
            source_version=args.source_version,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"status": "failed", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - operational safety net
        print(
            json.dumps(
                {"status": "failed", "detail": f"Onverwachte importfout: {exc}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "status": "success",
                "datastore": get_runtime_datastore_info(),
                "import": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
