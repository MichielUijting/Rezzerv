"""PO acceptance test for the Rezzerv authorization matrix.

Run locally from the repository root with:
    docker compose exec -T backend python -m app.testing.authorization_matrix_acceptance

The program compares the household role permissions from matrix v1.1 plus the
active Superuser-v2 platform boundary with the runtime. It exits with code 0
for GO and code 1 for NO-GO.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.authorization_foundation_service import (
    ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS,
    PLATFORM_ADMIN_PERMISSIONS,
    permissions_for_session_role,
)


ROLES = ("lid", "beheerder", "superuser", "frontteamlid")


@dataclass(frozen=True)
class MatrixRule:
    domain: str
    function: str
    permission: str
    lid: bool
    beheerder: bool
    superuser: bool
    frontteamlid: bool

    def expected(self, role: str) -> bool:
        return bool(getattr(self, role))


RULES = (
    MatrixRule("Voorraad", "Voorraad bekijken", "inventory.view", True, True, True, True),
    MatrixRule("Voorraad", "Voorraad wijzigen", "inventory.update", True, True, True, True),
    MatrixRule("Voorraad", "Voorraad corrigeren", "inventory.correct", True, True, True, True),
    MatrixRule("Kassabonnen", "Kassabonnen bekijken", "receipts.view", True, True, True, True),
    MatrixRule("Kassabonnen", "Kassabonnen verwerken", "receipts.process", True, True, True, True),
    MatrixRule("Kassabonnen", "Kassabonnen verwijderen", "receipts.delete", True, True, True, True),
    MatrixRule("Uitpakken", "Uitpakken bekijken", "unpacking.view", True, True, True, True),
    MatrixRule("Uitpakken", "Uitpakken verwerken", "unpacking.process", True, True, True, True),
    MatrixRule("Uitpakken", "Uitpakken corrigeren", "unpacking.correct", True, True, True, True),
    MatrixRule("Bijna op", "Bijna op bekijken", "almost_out.view", True, True, True, True),
    MatrixRule("Bijna op", "Bijna op wijzigen", "almost_out.update", True, True, True, True),
    MatrixRule("Inkooplijst", "Inkooplijst bekijken", "shopping_list.view", True, True, True, True),
    MatrixRule("Inkooplijst", "Inkooplijst wijzigen", "shopping_list.update", True, True, True, True),
    MatrixRule("Inkooplijst", "Inkooplijst beheren", "shopping_list.manage", True, True, True, True),
    MatrixRule("Artikelen", "Artikelen bekijken", "articles.view", True, True, True, True),
    MatrixRule("Artikelen", "Artikelen wijzigen", "articles.update", False, True, True, True),
    MatrixRule("Artikelen", "Artikelen beheren", "articles.manage", False, True, True, True),
    MatrixRule("Artikelgroepen", "Artikelgroepen bekijken", "article_groups.view", True, True, True, True),
    MatrixRule("Artikelgroepen", "Artikelgroep toewijzen", "article_groups.assign", True, True, True, True),
    MatrixRule("Artikelgroepen", "Artikelgroepen beheren", "article_groups.manage", False, True, True, True),
    MatrixRule("Locaties", "Locaties bekijken", "locations.view", True, True, True, True),
    MatrixRule("Locaties", "Locaties wijzigen", "locations.update", False, True, True, True),
    MatrixRule("Locaties", "Locaties beheren", "locations.manage", False, True, True, True),
    MatrixRule("Winkels", "Winkels bekijken", "stores.view", True, True, True, True),
    MatrixRule("Winkels", "Winkels wijzigen", "stores.update", True, True, True, True),
    MatrixRule("Winkels", "Winkels beheren", "stores.manage", True, True, True, True),
    MatrixRule("Spaartegoeden", "Spaartegoeden bekijken", "loyalty.view", True, True, True, True),
    MatrixRule("Spaartegoeden", "Spaartegoeden wijzigen", "loyalty.update", True, True, True, True),
    MatrixRule("Spaartegoeden", "Spaartegoeden beheren", "loyalty.manage", True, True, True, True),
    MatrixRule("Inzichten", "Inzichten / prognoses bekijken", "insights.view", True, True, True, True),
    MatrixRule("Inzichten", "Gegevens exporteren", "insights.export", False, True, True, True),
    MatrixRule("Catalogus", "Catalogus bekijken", "catalog.view", True, True, True, True),
    MatrixRule("Catalogus", "Catalogus wijzigen", "catalog.update", False, False, True, True),
    MatrixRule("Catalogus", "Catalogus beheren", "catalog.manage", False, False, True, True),
    MatrixRule("GPC", "GPC bekijken", "gpc.view", True, True, True, True),
    MatrixRule("GPC", "GPC wijzigen", "gpc.update", False, True, True, True),
    MatrixRule("GPC", "GPC beheren", "gpc.manage", False, True, True, True),
    MatrixRule("Huishouden", "Huishoudinstellingen bekijken", "household_settings.view", True, True, True, True),
    MatrixRule("Huishouden", "Huishoudinstellingen beheren", "household_settings.manage", False, True, True, True),
    MatrixRule("Autorisaties", "Leden bekijken", "members.view", True, True, True, True),
    MatrixRule("Autorisaties", "Leden beheren", "members.manage", False, True, True, True),
    MatrixRule("Autorisaties", "Rechten bekijken", "permissions.view", True, True, True, True),
    MatrixRule("Autorisaties", "Rechten beheren", "permissions.manage", False, True, True, True),
    MatrixRule("Admin", "Admin-tegel en /admin", "admin.access", False, True, True, True),
    MatrixRule("Externe databases", "Tegel en directe route", "frontteam.external_databases.access", False, False, True, True),
)


def permission_sets() -> dict[str, set[str]]:
    return {
        "lid": permissions_for_session_role("member"),
        "beheerder": permissions_for_session_role("admin"),
        "superuser": permissions_for_session_role("owner", platform_superuser=True),
        "frontteamlid": permissions_for_session_role("frontteam"),
    }


def run() -> int:
    actual = permission_sets()
    failures: list[str] = []
    checks = 0

    print("REZZERV AUTORISATIEMATRIX ACCEPTATIETEST v1.1 + SUPERUSER-v2")
    print("=" * 70)

    for rule in RULES:
        for role in ROLES:
            expected = rule.expected(role)
            granted = rule.permission in actual[role]
            checks += 1
            if expected != granted:
                failures.append(
                    f"{rule.domain} | {rule.function} | {role}: "
                    f"verwacht={'JA' if expected else 'NEE'}, "
                    f"werkelijk={'JA' if granted else 'NEE'} ({rule.permission})"
                )

    superuser_platform = {p for p in actual["superuser"] if p.startswith("platform.")}

    # High-risk structural assertions. Household matrix v1.1 remains intact while
    # the platform Superuser follows the explicit v2 functional boundary.
    invariants = (
        ("beheerder heeft alle toegestane lidrechten", actual["lid"] <= actual["beheerder"]),
        ("superuser heeft alle beheerder-huishoudrechten", actual["beheerder"] <= actual["superuser"]),
        (
            "superuser heeft exact de actieve functionele platform-v2-rechten",
            superuser_platform == set(ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS),
        ),
        (
            "superuser heeft geen technische Platformbeheerderrechten",
            not (set(PLATFORM_ADMIN_PERMISSIONS) & superuser_platform),
        ),
        (
            "superuser beheert geen speciale platformrollen",
            "platform.special_roles.manage" not in superuser_platform,
        ),
        ("beheerder heeft geen platformrechten", not any(p.startswith("platform.") for p in actual["beheerder"])),
        ("lid heeft geen Admin-toegang", "admin.access" not in actual["lid"]),
        ("beheerder heeft geen Externe-databases-toegang", "frontteam.external_databases.access" not in actual["beheerder"]),
        ("superuser heeft volledige Externe-databases-toegang", "frontteam.external_databases.access" in actual["superuser"]),
        ("frontteamlid heeft Externe-databases-toegang", "frontteam.external_databases.access" in actual["frontteamlid"]),
        ("beheerder mag GPC wijzigen", "gpc.update" in actual["beheerder"]),
        ("beheerder mag Catalogus niet wijzigen", "catalog.update" not in actual["beheerder"]),
    )
    for label, passed in invariants:
        checks += 1
        if not passed:
            failures.append(f"STRUCTUURREGEL: {label}")

    if failures:
        print(f"NO-GO: {len(failures)} afwijking(en) bij {checks} controles")
        print("-")
        for failure in failures:
            print(f"FOUT: {failure}")
        return 1

    print(f"GO: alle {checks} controles zijn conform household-matrix v1.1 + Superuser-v2")
    print(f"- {len(RULES)} functionele rechten x {len(ROLES)} rollen")
    print(f"- {len(invariants)} extra risicocontroles")
    print("AUTORISATIEMATRIX_ACCEPTATIE_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
