from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app import models
from app.advisor.loop import run_turn
from app.models import SessionLocal
from app.routes.auth import DB, CurrentStudent
from app.schemas.advisor import ChatMessage, ChatRequest, Conversation

router = APIRouter(prefix="/chat", tags=["advisor"])


@router.post("", response_class=StreamingResponse)
async def chat(body: ChatRequest, student: CurrentStudent):
    """Stream one advisor turn as server-sent events (one AdvisorEvent per `data:` line)."""
    student_id = student.id

    async def stream():
        # own session: the request's session closes before the stream finishes
        with SessionLocal() as db:
            st = db.get(models.Student, student_id)
            async for event in run_turn(db, st, body.conversation_id, body.message):
                yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/latest")
def latest_conversation(db: DB, student: CurrentStudent) -> Conversation | None:
    convo = db.scalar(
        select(models.Conversation)
        .where(models.Conversation.student_id == student.id)
        .order_by(models.Conversation.id.desc())
    )
    return _conversation(convo) if convo else None


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, db: DB, student: CurrentStudent) -> Conversation:
    convo = db.get(models.Conversation, conversation_id)
    if convo is None or convo.student_id != student.id:
        raise HTTPException(404, "no such conversation")
    return _conversation(convo)


def _conversation(convo: models.Conversation) -> Conversation:
    out = []
    for m in convo.messages:
        if not m.events:
            continue
        role = "user" if m.role == "user" else "assistant"
        out.append(ChatMessage(id=m.id, role=role, events=m.events))
    return Conversation(id=convo.id, messages=out)
