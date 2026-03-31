import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import httpx
import websockets
from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

WRITE_ACTIONS = {"create_notification", "update_notification", "delete_notification", "archive_notification"}
ROLES_CAN_WRITE = {"Партнер", "IT отдел", "Офис менеджер"}


async def get_user_from_token(token: str) -> dict | None:
    """Валидация токена через auth, возврат {id, role} или None."""
    if not token or not token.strip():
        return None
    token = token.replace("Bearer ", "").strip()
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{settings.auth_service_url}/users/me",
                headers={"Authorization": f"Bearer {token}"},
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return None
    if r.status_code != 200:
        return None
    user = r.json()
    return {"id": user["id"], "role": user.get("role") or "Сотрудник"}


async def forward_to_notifications_service(message: dict) -> dict:
    """Отправить одно сообщение в сервис уведомлений по WebSocket, получить один ответ."""
    settings = get_settings()
    base = settings.notifications_service_url
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_base}/ws/notifications"
    try:
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps(message))
            raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
            return json.loads(raw)
    except Exception:
        return {"error": "Service unavailable", "request_id": message.get("request_id")}


@router.websocket("/ws")
async def ws_notifications(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            raw = await websocket.receive_text()
        except WebSocketDisconnect:
            break
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.send_json({"error": "Invalid JSON"})
            continue

        token = msg.get("token") or (msg.get("payload") or {}).get("token")
        user = await get_user_from_token(token) if token else None
        if not user:
            await websocket.send_json({
                "request_id": msg.get("request_id"),
                "error": "Authorization required. Send 'token' in message or in payload.",
            })
            continue

        action = msg.get("action")
        if action in WRITE_ACTIONS and user["role"] not in ROLES_CAN_WRITE:
            await websocket.send_json({
                "request_id": msg.get("request_id"),
                "error": "Only Partner, IT department and Office manager can create, edit, archive or delete notifications.",
            })
            continue

        payload = dict(msg.get("payload") or {})
        payload.pop("token", None)
        forward_msg = {"action": action, "payload": payload, "request_id": msg.get("request_id")}

        response = await forward_to_notifications_service(forward_msg)
        await websocket.send_json(response)
