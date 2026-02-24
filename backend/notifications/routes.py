# backend/notifications/routes.py — Notifications REST API
"""
Notification operations using Beanie ODM.
"""

from fastapi import APIRouter, HTTPException, Depends

from auth.dependencies import get_current_user
from db.models import User, Notification

router = APIRouter()


@router.get("/notifications")
async def list_notifications(current_user: User = Depends(get_current_user)):
    """List all notifications for current user."""
    notifications = await Notification.find(
        Notification.user_id == current_user.id
    ).sort(-Notification.created_at).to_list()
    
    return [
        {
            "id": n.id,
            "type": n.type,
            "message": n.message,
            "projectId": n.project_id,
            "read": n.read,
            "createdAt": n.created_at.isoformat() if n.created_at else "",
        }
        for n in notifications
    ]


@router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
):
    """Mark notification as read."""
    notification = await Notification.find_one(Notification.id == notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    if notification.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your notification")

    notification.read = True
    await notification.save()
    return {"message": "Notification marked as read"}


@router.get("/notifications/unread-count")
async def get_unread_count(current_user: User = Depends(get_current_user)):
    """Get count of unread notifications."""
    count = await Notification.find(
        Notification.user_id == current_user.id,
        Notification.read == False,
    ).count()
    
    return {"count": count}
