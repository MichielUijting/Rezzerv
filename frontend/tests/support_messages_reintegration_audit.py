"""Static regression audit for the reintegrated Rezzerv Meldingen flow."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
HOME = ROOT / "features" / "home" / "HomePage.jsx"
ROUTER = ROOT / "app" / "router" / "AppRouter.jsx"
PAGE = ROOT / "features" / "support" / "HouseholdSupportPage.jsx"
API = ROOT / "features" / "support" / "supportApi.js"


def run() -> int:
    failures: list[str] = []
    home = HOME.read_text(encoding="utf-8")
    router = ROUTER.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")

    checks = {
        "Meldingen-tegel bestaat": "key: 'meldingen'" in home,
        "Meldingen-tegel routeert rolgebonden": (
            "visibility.isPlatformSuperuser" in home
            and "'/superuser/meldingen'" in home
            and "'/meldingen'" in home
        ),
        "Meldingen-route is beveiligd": "path: '/meldingen'" in router and "<Protected><HouseholdSupportPage" in router,
        "gebruiker kan melding maken": "createHouseholdThread" in page and "Melding versturen" in page,
        "gebruiker kan gesprek voortzetten": "replyHouseholdThread" in page and "Reactie" in page,
        "API gebruikt HttpOnly-cookieclient": "fetchJsonWithAuth" in api,
        "API gebruikt geen legacy bearer-token": "rezzerv_token" not in api and "Authorization" not in api,
        "pagina gebruikt geen legacy identiteit": "localStorage" not in page,
    }
    for label, passed in checks.items():
        if not passed:
            failures.append(label)

    if failures:
        print("NO-GO support messages reintegration")
        for failure in failures:
            print(f"FAIL {failure}")
        return 1

    print("PASS Meldingen-tegel en rolgebonden beveiligde routes hersteld")
    print("PASS gebruikers kunnen melden en antwoorden via server-side sessie")
    print("SUPPORT_MESSAGES_REINTEGRATION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
