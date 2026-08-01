from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOUSEHOLD = (ROOT / "frontend/src/features/support/HouseholdSupportPage.jsx").read_text(encoding="utf-8")
PLATFORM = (ROOT / "frontend/src/features/support/PlatformSupportPage.jsx").read_text(encoding="utf-8")
API = (ROOT / "frontend/src/features/support/supportApi.js").read_text(encoding="utf-8")
CSS = (ROOT / "frontend/src/features/support/support.css").read_text(encoding="utf-8")
ROUTES = (ROOT / "backend/app/api/support_message_routes.py").read_text(encoding="utf-8")

checks = {
    "household defaults to Open": "useState('Open')" in HOUSEHOLD,
    "platform defaults to Open": "useState('Open')" in PLATFORM,
    "household shows refresh status": "Laatst ververst:" in HOUSEHOLD and "refreshCount" in HOUSEHOLD,
    "platform shows refresh status": "Laatst ververst:" in PLATFORM and "refreshCount" in PLATFORM,
    "household supports deletion": "deleteHouseholdThread" in HOUSEHOLD and "rz-support-delete" in HOUSEHOLD,
    "platform supports deletion": "deletePlatformThread" in PLATFORM and "rz-support-delete" in PLATFORM,
    "API exposes delete calls": "method: 'DELETE'" in API,
    "backend exposes household delete": '@router.delete("/api/support/threads/{thread_id}")' in ROUTES,
    "backend exposes platform delete": '@router.delete("/api/platform/support/threads/{thread_id}")' in ROUTES,
    "backend supplies last sender": "last_sender_user_id" in ROUTES,
    "unread panels are light green": "rz-support-thread-row--unread" in CSS and "#e8f6e8" in CSS,
    "message body remains normal weight": ".rz-support-message p" in CSS and "font-weight:400" in CSS,
    "title remains bold": ".rz-support-detail-head h2" in CSS and "font-weight:700" in CSS,
}

failed = [name for name, passed in checks.items() if not passed]
if failed:
    for name in failed:
        print(f"FOUT: {name}")
    raise SystemExit(1)

print(f"GO: {len(checks)} meldingen-verbetercontroles groen")
print("SUPPORT_MESSAGE_IMPROVEMENTS_GREEN")
