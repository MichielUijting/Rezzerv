from __future__ import annotations

from app.db import engine
from app.services.authorization_foundation_service import ensure_authorization_foundation


def main() -> None:
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
    print("AUTHORIZATION_FOUNDATION_INITIALIZED")


if __name__ == "__main__":
    main()
