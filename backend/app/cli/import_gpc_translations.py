"""Export and import a Dutch language overlay for the GS1 GPC catalog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import create_engine

from app.services.gpc_translation_service import (
    export_translation_template,
    import_gpc_translations_csv,
    translation_coverage,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Beheer Nederlandse GPC-vertalingen.")
    parser.add_argument("--database", required=True, help="Pad naar de Rezzerv SQLite-database")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export-template")
    export.add_argument("output_csv")
    import_command = sub.add_parser("import")
    import_command.add_argument("translation_csv")
    import_command.add_argument("--allow-incomplete", action="store_true")
    sub.add_parser("coverage")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database = Path(args.database)
    if not database.is_file():
        print(json.dumps({"status": "failed", "detail": f"Database ontbreekt: {database}"}), file=sys.stderr)
        return 2
    engine = create_engine(f"sqlite:///{database}")
    try:
        if args.command == "export-template":
            result = export_translation_template(Path(args.output_csv), db_engine=engine)
        elif args.command == "import":
            result = import_gpc_translations_csv(
                Path(args.translation_csv),
                require_complete=not args.allow_incomplete,
                db_engine=engine,
            )
        else:
            result = translation_coverage(db_engine=engine)
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"status": "failed", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        engine.dispose()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
