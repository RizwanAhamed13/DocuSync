from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from app.auth.dependencies import get_current_user
from app.auth.service import decode_token
from app.db import get_connection
from app.notifications.ws_manager import manager

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(current_user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM notifications WHERE username = ? ORDER BY created_at DESC LIMIT 20",
            (current_user["sub"],),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


@router.get("/unread-count")
def unread_count(current_user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE username = ? AND read = 0",
            (current_user["sub"],),
        ).fetchone()
        return {"count": row["c"] if row else 0}
    finally:
        conn.close()


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        exists = conn.execute(
            "SELECT 1 FROM notifications WHERE notification_id = ? AND username = ?",
            (notification_id, current_user["sub"]),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
        conn.execute(
            "UPDATE notifications SET read = 1 WHERE notification_id = ? AND username = ?",
            (notification_id, current_user["sub"]),
        )
        conn.commit()
        return {"notification_id": notification_id, "read": True}
    finally:
        conn.close()


@router.post("/read-all")
def mark_all_read(current_user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE notifications SET read = 1 WHERE username = ?",
            (current_user["sub"],),
        )
        conn.commit()
        return {"read_all": True}
    finally:
        conn.close()


@router.delete("/clear-all")
def clear_all_notifications(current_user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM notifications WHERE username = ?",
            (current_user["sub"],),
        )
        conn.commit()
        return {"status": "ok", "message": "All notifications cleared"}
    finally:
        conn.close()


@router.delete("/{notification_id}")
def clear_notification(notification_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        exists = conn.execute(
            "SELECT 1 FROM notifications WHERE notification_id = ? AND username = ?",
            (notification_id, current_user["sub"]),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
        conn.execute(
            "DELETE FROM notifications WHERE notification_id = ? AND username = ?",
            (notification_id, current_user["sub"]),
        )
        conn.commit()
        return {"status": "ok", "message": "Notification deleted"}
    finally:
        conn.close()


@router.websocket("/ws")
async def notifications_ws(websocket: WebSocket, token: str):
    payload = decode_token(token)
    if payload is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    username = payload.get("sub")
    if not username:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    await manager.connect(username, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(username, websocket)

