"""Repository-wide authority for the unique current Alembic head."""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_CONFIG = BACKEND_ROOT / "alembic.ini"


def repository_head_revision() -> str:
    """Return the single Alembic head declared by the repository migration graph."""
    config = Config(str(ALEMBIC_CONFIG))
    script = ScriptDirectory.from_config(config)
    heads = tuple(str(value or "").strip() for value in script.get_heads())
    heads = tuple(value for value in heads if value)
    if len(heads) != 1:
        raise RuntimeError(
            "Rezzerv requires exactly one Alembic head; "
            f"found {len(heads)}: {list(heads)!r}"
        )
    return heads[0]


def main() -> int:
    print(repository_head_revision())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
