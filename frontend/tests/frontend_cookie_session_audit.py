"""Repository-wide audit for cookie-only frontend session authority."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
AUTH_SESSION = ROOT / "lib" / "authSession.js"
LOGIN_PAGE = ROOT / "features" / "auth" / "LoginPage.jsx"
API_CLIENT = ROOT / "lib" / "apiClient.js"
HOME_PAGE = ROOT / "features" / "home" / "HomePage.jsx"
CATALOG_PAGE = ROOT / "features" / "catalog" / "CatalogPage.jsx"
ADMIN_GUARD = ROOT / "app" / "router" / "AdminGuard.jsx"
FRONTTEAM_GUARD = ROOT / "app" / "router" / "FrontteamGuard.jsx"
PERMISSION_GUARD = ROOT / "app" / "router" / "PermissionGuard.jsx"
APP_ROUTER = ROOT / "app" / "router" / "AppRouter.jsx"
HEADER = ROOT / "ui" / "Header.jsx"

FORBIDDEN = {
    "rezzerv_token": "legacy token storage",
    "Bearer ": "Bearer authorization",
    "/api/auth/context": "legacy auth-context endpoint",
    "Authorization:": "Authorization header",
    "authorization:": "authorization header",
}

ALLOWED_COMPATIBILITY_FILE = AUTH_SESSION.resolve()


def source_files():
    for path in ROOT.rglob("*"):
        if path.suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}:
            yield path


def run() -> int:
    failures: list[str] = []
    for path in source_files():
        text = path.read_text(encoding="utf-8")
        for needle, label in FORBIDDEN.items():
            if needle not in text:
                continue
            if path.resolve() == ALLOWED_COMPATIBILITY_FILE and needle == "rezzerv_token":
                bad_reads = "getItem('rezzerv_token')" in text or 'getItem("rezzerv_token")' in text
                bad_writes = "setItem('rezzerv_token'" in text or 'setItem("rezzerv_token"' in text
                if not bad_reads and not bad_writes:
                    continue
            failures.append(f"{path.relative_to(ROOT)}: {label}")

    auth_text = AUTH_SESSION.read_text(encoding="utf-8")
    login_text = LOGIN_PAGE.read_text(encoding="utf-8")
    api_text = API_CLIENT.read_text(encoding="utf-8")
    home_text = HOME_PAGE.read_text(encoding="utf-8")
    catalog_text = CATALOG_PAGE.read_text(encoding="utf-8")
    admin_guard_text = ADMIN_GUARD.read_text(encoding="utf-8")
    frontteam_guard_text = FRONTTEAM_GUARD.read_text(encoding="utf-8")
    permission_guard_text = PERMISSION_GUARD.read_text(encoding="utf-8")
    router_text = APP_ROUTER.read_text(encoding="utf-8")
    header_text = HEADER.read_text(encoding="utf-8")

    required = {
        "authSession uses /api/session": "/api/session" in auth_text,
        "authSession includes credentials": "credentials: 'include'" in auth_text,
        "authSession has no token authority": "export function getStoredToken() {\n  return ''" in auth_text,
        "login validates server session": "fetchAuthContext({ force: true })" in login_text,
        "api client includes credentials": "credentials: 'include'" in api_text,
        "header reads server session context": "readStoredAuthContext" in header_text,
        "header renders active household": "active_household_id" in header_text and "Huishouden:" in header_text,
        "header does not read legacy localStorage": "localStorage.getItem" not in header_text,
        "household admin helper accepts admin": "'admin'" in auth_text,
        "household admin helper accepts owner": "'owner'" in auth_text,
        "household admin helper accepts frontteam": "'frontteam'" in auth_text,
        "home admin tile uses household admin authority": "canOpenAdmin: isHouseholdAdminFromContext" in home_text,
        "admin route uses household admin authority": "isHouseholdAdminFromContext" in admin_guard_text,
        "frontteam helper exists": "isFrontteamMemberFromContext" in auth_text,
        "platform superuser inherits external database access": "isPlatformSuperuserFromContext(source)" in auth_text,
        "external databases tile uses frontteam authority": "canOpenExternalDatabases: isFrontteamMemberFromContext" in home_text,
        "frontteam route guard exists": "isFrontteamMemberFromContext" in frontteam_guard_text,
        "external databases route uses frontteam guard": "<ProtectedFrontteam><ExternalDatabasesPage" in router_text,
        "generic permission guard exists": "canCurrentUserPerform" in permission_guard_text,
        "catalog overview is available to members": "path: '/catalogus', element: <Protected><CatalogPage" in router_text,
        "catalog detail is available to members": "path: '/catalogus/:globalProductId', element: <Protected><CatalogDetailPageV2" in router_text,
        "gpc mutation requires gpc update": "permission=\"gpc.update\"" in router_text,
        "catalog page reads gpc update permission": "canCurrentUserPerform('gpc.update'" in catalog_text,
        "catalog page hides gpc mutation for read-only roles": "{canUpdateGpc ? <Button" in catalog_text,
        "catalog page explains read-only access": "Alleen-lezen:" in catalog_text,
    }
    for label, passed in required.items():
        if not passed:
            failures.append(label)

    if failures:
        print("FAIL frontend cookie session audit")
        for failure in sorted(set(failures)):
            print(f"FAIL {failure}")
        return 1

    print("PASS /api/session is the sole frontend authority for identity, role and household")
    print("PASS frontend requests use the HttpOnly session cookie")
    print("PASS header renders identity and active household from server session context")
    print("PASS admin is available to beheerder, owner and frontteam roles")
    print("PASS external databases is available to frontteam and platform superuser")
    print("PASS catalog view and GPC mutation controls follow the PO matrix")
    print("FRONTEND_COOKIE_SESSION_AUDIT_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
