from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FUNCTIONAL = ROOT / "docs/features/MELDINGEN-FUNCTIONEEL-ONTWERP-v1.0.md"
REGRESSION = ROOT / "docs/testing/MELDINGEN-REGRESSIEPROTOCOL-v1.0.md"

files = {
    "functioneel ontwerp": FUNCTIONAL,
    "regressieprotocol": REGRESSION,
    "rolroutering-audit": ROOT / "frontend/tests/support_message_role_routing_audit.py",
    "verbeteringen-audit": ROOT / "frontend/tests/support_message_improvements_audit.py",
    "broadcast-audit": ROOT / "frontend/tests/support_message_broadcast_audit.py",
}

failed = []
for label, path in files.items():
    if not path.exists():
        failed.append(f"{label} ontbreekt: {path.relative_to(ROOT)}")

if not failed:
    functional = FUNCTIONAL.read_text(encoding="utf-8")
    regression = REGRESSION.read_text(encoding="utf-8")
    checks = {
        "PO-GO is vastgelegd": "PO-GO" in functional and "2026-08-01" in functional,
        "gebruikersketen is vastgelegd": "Gebruikersmelding naar superuser" in functional,
        "superuserbroadcast is vastgelegd": "Platformbericht aan alle leden" in functional,
        "centrale feedback is verplicht": "AppFeedbackProvider" in functional and "window.confirm" in functional,
        "standaardfilter Open is vastgelegd": "standaardfilter is **Open**" in functional,
        "lichtgroene markering is vastgelegd": "lichtgroen" in functional,
        "handmatige PO-steekproef bestaat": "Verplichte handmatige PO-steekproef" in regression,
        "negatieve autorisatie wordt getest": "Negatieve autorisatie" in regression,
        "NO-GO-criteria bestaan": "NO-GO-criteria" in regression,
        "broadcastontvanger-query is beschreven": "user_email" in functional and "app_users" in functional,
    }
    failed.extend(name for name, passed in checks.items() if not passed)

if failed:
    for item in failed:
        print(f"FOUT: {item}")
    raise SystemExit(1)

print("GO: Meldingen-functionaliteit, PO-acceptatie en regressiecontract zijn vastgelegd")
print("SUPPORT_MESSAGE_DOCUMENTATION_CONTRACT_GREEN")
