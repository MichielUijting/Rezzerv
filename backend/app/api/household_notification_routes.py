from fastapi import APIRouter, Header, HTTPException
from app.services.household_notification_service import HouseholdNotificationError, list_household_notifications, mark_household_notification_read
from app.services.support_message_session_adapter import household_support_actor
from app import main as main_module

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

@router.get("")
def list_notifications(authorization: str | None = Header(None)):
    actor = household_support_actor(authorization)
    with main_module.engine.begin() as conn:
        items = list_household_notifications(conn, household_id=actor["household_id"], user_id=actor["user_id"])
    return {"items": items}

@router.post("/{notification_id}/read")
def mark_notification_read(notification_id: str, authorization: str | None = Header(None)):
    actor = household_support_actor(authorization)
    try:
        with main_module.engine.begin() as conn:
            mark_household_notification_read(conn, notification_id=notification_id, household_id=actor["household_id"], user_id=actor["user_id"])
    except HouseholdNotificationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}
