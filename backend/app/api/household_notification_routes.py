from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.household_notification_service import HouseholdNotificationError, list_household_notifications, mark_household_notification_read
from app.services.support_message_session_adapter import resolve_household_support_actor

router = APIRouter(prefix="/notifications", tags=["notifications"])

@router.get("")
def list_notifications(db: Session = Depends(get_db)):
    actor = resolve_household_support_actor()
    with db.begin():
        items = list_household_notifications(db.connection(), household_id=actor.household_id, user_id=actor.user_id)
    return {"items": items}

@router.post("/{notification_id}/read")
def mark_notification_read(notification_id: str, db: Session = Depends(get_db)):
    actor = resolve_household_support_actor()
    try:
        with db.begin():
            mark_household_notification_read(db.connection(), notification_id=notification_id, household_id=actor.household_id, user_id=actor.user_id)
    except HouseholdNotificationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}
