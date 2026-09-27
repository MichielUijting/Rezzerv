"""Static regression audit for the reintegrated Rezzerv Meldingen flow."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
HOME = ROOT / "features" / "home" / "HomePage.jsx"
HOME_NAVIGATION = ROOT / "features" / "home" / "homeNavigation.js"
ROUTER = ROOT / "app" / "router" / "AppRouter.jsx"
PAGE = ROOT / "features" / "support" / "HouseholdSupportPage.jsx"
PLATFORM_PAGE = ROOT / "features" / "support" / "PlatformSupportPage.jsx"
API = ROOT / "features" / "support" / "supportApi.js"
SUPERUSER_OVERVIEW = ROOT / "features" / "superuser" / "SuperuserOverviewSection.jsx"


def run() -> int:
    failures: list[str] = []
    home = HOME.read_text(encoding="utf-8")
    navigation = HOME_NAVIGATION.read_text(encoding="utf-8")
    router = ROUTER.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")
    platform_page = PLATFORM_PAGE.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")
    overview = SUPERUSER_OVERVIEW.read_text(encoding="utf-8")

    checks = {
        "Meldingen-tegel bestaat voor gewone gebruiker": "key: 'meldingen'" in navigation,
        "Meldingen-tegel blijft onafhankelijk beschikbaar": "if (tile.key === 'meldingen') return true" in navigation,
        "Berichten-tegel is autorisatiegestuurd": "if (tile.key === 'berichten') return visibility.canOpenMessages" in navigation,
        "Superuser Berichten opent platform-inbox": "tile.key === 'berichten' && visibility.isPlatformSuperuser" in home and "'/superuser/meldingen'" in home,
        "Superuser kan niet op huishoudelijke meldingenpagina blijven": 'isPlatformSuperuserFromContext(authContext)' in page and '<Navigate to="/superuser/meldingen" replace />' in page,
        "Huishoudelijke feedback gebruikt overlay": 'support-feedback' in page and 'rz-support-feedback' not in page,
        "Platformfeedback gebruikt overlay": 'platform-support-feedback' in platform_page and 'rz-support-feedback' not in platform_page,
        "gewone Meldingen-tegel opent huishoudroute": "meldingen: '/meldingen'" in home,
        "Superuser Meldingen-ingang staat in Beheercentrum": "navigate(notificationRoute)" in overview and "Meldingen (" in overview,
        "Meldingen-route is beveiligd": "path: '/meldingen'" in router and "<Protected><HouseholdSupportPage" in router,
        "platform-Meldingen-route blijft beveiligd": "path: '/superuser/meldingen'" in router and "PlatformSupportPage" in router,
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

    print("PASS Meldingen blijft onafhankelijk beschikbaar; Berichten routeert Superuser naar de platform-inbox")
    print("PASS gebruikers kunnen melden en antwoorden via server-side sessie")
    print("SUPPORT_MESSAGES_REINTEGRATION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
