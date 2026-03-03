import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database import async_session_factory
from infrastructure.repositories import TicketRepository, CommentRepository
from application.ports import TicketFilters
from application.use_cases import (
    CreateTicketUseCase,
    GetTicketUseCase,
    ListTicketsUseCase,
    UpdateTicketUseCase,
    ArchiveTicketUseCase,
    CreateCommentUseCase,
    ListCommentsUseCase,
    UpdateCommentUseCase,
    DeleteCommentUseCase,
)
from domain.entities import Status, Priority

router = APIRouter(tags=["ws"])


def _ticket_to_dict(t):
    return {
        "id": t.id,
        "uuid": t.uuid,
        "theme": t.theme,
        "description": t.description,
        "attachment_path": t.attachment_path,
        "status": t.status,
        "created_by_user_id": t.created_by_user_id,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "category": t.category,
        "priority": t.priority,
        "is_archived": getattr(t, "is_archived", False),
    }


def _comment_to_dict(c):
    return {
        "id": c.id,
        "ticket_id": c.ticket_id,
        "user_id": c.user_id,
        "content": c.content,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.websocket("/ws/tickets")
async def ws_tickets(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
        except WebSocketDisconnect:
            break
        except json.JSONDecodeError:
            await websocket.send_json({"error": "Invalid JSON"})
            continue
        action = msg.get("action")
        payload = msg.get("payload") or {}
        request_id = msg.get("request_id")

        def reply(result=None, error=None):
            out = {"request_id": request_id}
            if error is not None:
                out["error"] = error
            else:
                out["result"] = result
            return out

        async with async_session_factory() as session:
            try:
                ticket_repo = TicketRepository(session)
                comment_repo = CommentRepository(session)

                if action == "list_statuses":
                    await websocket.send_json(reply(result=[{"value": s.value, "label": s.value} for s in Status]))
                    continue

                if action == "list_priorities":
                    await websocket.send_json(reply(result=[{"value": p.value, "label": p.value} for p in Priority]))
                    continue

                if action == "create_ticket":
                    uc = CreateTicketUseCase(ticket_repo)
                    ticket = await uc.execute(
                        theme=payload.get("theme", ""),
                        description=payload.get("description", ""),
                        attachment_path=payload.get("attachment_path"),
                        created_by_user_id=payload["created_by_user_id"],
                        category=payload.get("category", ""),
                        priority=payload.get("priority", ""),
                    )
                    await session.commit()
                    await websocket.send_json(reply(result=_ticket_to_dict(ticket)))
                    continue

                if action == "get_ticket":
                    uc = GetTicketUseCase(ticket_repo)
                    ticket = await uc.execute(payload.get("ticket_uuid", ""))
                    if not ticket:
                        await websocket.send_json(reply(error="Ticket not found"))
                    else:
                        await websocket.send_json(reply(result=_ticket_to_dict(ticket)))
                    continue

                if action == "list_tickets":
                    filters = TicketFilters(
                        skip=payload.get("skip", 0),
                        limit=payload.get("limit", 50),
                        status=payload.get("status"),
                        priority=payload.get("priority"),
                        category=payload.get("category"),
                        created_by_user_id=payload.get("created_by_user_id"),
                        include_archived=payload.get("include_archived", False),
                    )
                    uc = ListTicketsUseCase(ticket_repo)
                    tickets = await uc.execute(filters)
                    await websocket.send_json(reply(result=[_ticket_to_dict(t) for t in tickets]))
                    continue

                if action == "update_ticket":
                    uc = UpdateTicketUseCase(ticket_repo)
                    ticket = await uc.execute(
                        ticket_uuid=payload.get("ticket_uuid", ""),
                        theme=payload.get("theme"),
                        description=payload.get("description"),
                        attachment_path=payload.get("attachment_path"),
                        status=payload.get("status"),
                        category=payload.get("category"),
                        priority=payload.get("priority"),
                    )
                    if not ticket:
                        await websocket.send_json(reply(error="Ticket not found"))
                    else:
                        await session.commit()
                        await websocket.send_json(reply(result=_ticket_to_dict(ticket)))
                    continue

                if action == "archive_ticket":
                    uc = ArchiveTicketUseCase(ticket_repo)
                    ticket = await uc.execute(
                        ticket_uuid=payload.get("ticket_uuid", ""),
                        is_archived=payload.get("is_archived", True),
                    )
                    if not ticket:
                        await websocket.send_json(reply(error="Ticket not found"))
                    else:
                        await session.commit()
                        await websocket.send_json(reply(result=_ticket_to_dict(ticket)))
                    continue

                if action == "list_comments":
                    uc_ticket = GetTicketUseCase(ticket_repo)
                    ticket = await uc_ticket.execute(payload.get("ticket_uuid", ""))
                    if not ticket:
                        await websocket.send_json(reply(error="Ticket not found"))
                    else:
                        uc = ListCommentsUseCase(comment_repo)
                        comments = await uc.execute(ticket.id)
                        await websocket.send_json(reply(result=[_comment_to_dict(c) for c in comments]))
                    continue

                if action == "add_comment":
                    uc_ticket = GetTicketUseCase(ticket_repo)
                    ticket = await uc_ticket.execute(payload.get("ticket_uuid", ""))
                    if not ticket:
                        await websocket.send_json(reply(error="Ticket not found"))
                    else:
                        uc = CreateCommentUseCase(comment_repo)
                        comment = await uc.execute(
                            ticket_id=ticket.id,
                            user_id=payload["user_id"],
                            content=payload.get("content", ""),
                        )
                        await session.commit()
                        await websocket.send_json(reply(result=_comment_to_dict(comment)))
                    continue

                if action == "edit_comment":
                    uc = UpdateCommentUseCase(comment_repo)
                    comment = await uc.execute(
                        comment_id=payload["comment_id"],
                        content=payload.get("content", ""),
                    )
                    if not comment:
                        await websocket.send_json(reply(error="Comment not found"))
                    else:
                        await session.commit()
                        await websocket.send_json(reply(result=_comment_to_dict(comment)))
                    continue

                if action == "delete_comment":
                    uc = DeleteCommentUseCase(comment_repo)
                    ok = await uc.execute(comment_id=payload["comment_id"])
                    if not ok:
                        await websocket.send_json(reply(error="Comment not found"))
                    else:
                        await session.commit()
                        await websocket.send_json(reply(result={"deleted": True}))
                    continue

                await websocket.send_json(reply(error=f"Unknown action: {action}"))

            except Exception as e:
                await session.rollback()
                await websocket.send_json(reply(error=str(e)))
