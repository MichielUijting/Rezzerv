from __future__ import annotations

import argparse

from app.db import engine
from app.services.beta_superuser_provisioning_service import provision_po_beta_superuser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ken één expliciet PO/bèta-account huishoudbeheer en platform-superuser toe."
    )
    parser.add_argument("--email", required=True, help="Bestaand Rezzerv-account")
    parser.add_argument(
        "--household-id",
        help="Verplicht wanneer het account meer dan één actief huishoudlidmaatschap heeft",
    )
    parser.add_argument(
        "--actor-user-id",
        default="system:po-beta-provisioning",
        help="Actor voor de append-only autorisatieaudit",
    )
    parser.add_argument(
        "--reason",
        default="Expliciete PO-bètatoegang",
        help="Reden die in de audit wordt vastgelegd",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    with engine.begin() as conn:
        result = provision_po_beta_superuser(
            conn,
            email=args.email,
            household_id=args.household_id,
            actor_user_id=args.actor_user_id,
            reason=args.reason,
        )
    print(
        "PO_BETA_SUPERUSER_PROVISIONED "
        f"user_id={result.user_id} "
        f"email={result.email} "
        f"household_id={result.household_id} "
        f"membership_id={result.membership_id} "
        f"household_changed={int(result.household_role_created_or_updated)} "
        f"platform_changed={int(result.platform_role_created_or_updated)}"
    )


if __name__ == "__main__":
    main()
