from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "frontend/src/features/support/PlatformSupportPage.jsx").read_text(encoding="utf-8")
API = (ROOT / "frontend/src/features/support/supportApi.js").read_text(encoding="utf-8")
ROUTE = (ROOT / "backend/app/api/support_broadcast_routes.py").read_text(encoding="utf-8")
ENTRYPOINT = (ROOT / "backend/app/session_entrypoint.py").read_text(encoding="utf-8")

checks = {
    "superuserformulier aanwezig": "Nieuwe melding aan alle leden" in PAGE,
    "centrale bevestiging aanwezig": "support-broadcast-confirmation" in PAGE and "showFeedback" in PAGE,
    "frontend broadcast-API aanwezig": "createPlatformBroadcast" in API and "/api/platform/support/broadcast" in API,
    "backend broadcast-route aanwezig": '@router.post("/api/platform/support/broadcast"' in ROUTE,
    "alleen platformmutatie toegestaan": "platform.support_access.mutate" in ROUTE,
    "actieve leden worden geselecteerd": "_active_member_targets" in ROUTE and "household_memberships" in ROUTE,
    "systeemhuishouden wordt uitgesloten": 'household_id == "0"' in ROUTE,
    "ieder lid krijgt eigen gesprek": "for target_user_id, household_id in targets" in ROUTE,
    "superuser blijft afzender": "UPDATE support_messages" in ROUTE and 'sender_user_id": actor["user_id"]' in ROUTE,
    "route is geregistreerd": "support_broadcast_router" in ENTRYPOINT and "app.include_router(support_broadcast_router)" in ENTRYPOINT,
}

failed = [name for name, passed in checks.items() if not passed]
if failed:
    for name in failed:
        print(f"FOUT: {name}")
    raise SystemExit(1)

print(f"GO: {len(checks)} superuserbroadcastcontroles groen")
print("SUPPORT_MESSAGE_BROADCAST_GREEN")
