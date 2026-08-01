from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "src/features/home/HomePage.jsx"
ROUTER = ROOT / "src/app/router/AppRouter.jsx"
PLATFORM_PAGE = ROOT / "src/features/support/PlatformSupportPage.jsx"
SUPPORT_API = ROOT / "src/features/support/supportApi.js"


def require(path: Path, *needles: str) -> None:
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise AssertionError(f"{path}: ontbreekt: {needle}")


def main() -> None:
    require(
        HOME,
        "isPlatformSuperuserFromContext",
        "visibility.isPlatformSuperuser ? '/superuser/meldingen' : '/meldingen'",
    )
    require(
        ROUTER,
        "PlatformSupportPage",
        "path: '/superuser/meldingen'",
        'permission="platform.support_access.read"',
    )
    require(
        PLATFORM_PAGE,
        "Alle meldingen",
        "listPlatformThreads",
        "readPlatformThread",
        "replyPlatformThread",
        "updatePlatformThreadStatus",
    )
    require(
        SUPPORT_API,
        "fetchJsonWithAuth",
        "/api/platform/support/threads",
    )
    print("SUPPORT_MESSAGE_ROLE_ROUTING_GREEN")


if __name__ == "__main__":
    main()
