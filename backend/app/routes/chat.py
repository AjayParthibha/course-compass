from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, services
from app.advisor.loop import run_turn
from app.models import SessionLocal
from app.routes.auth import DB, CurrentStudent
from app.schemas.advisor import ChatMessage, ChatRequest, Conversation, ConversationSummary

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


@router.get("")
def list_conversations(
    db: DB, student: CurrentStudent, limit: int = 30
) -> list[ConversationSummary]:
    """The student's chats with at least one question, most recently active first."""
    convos = db.scalars(
        select(models.Conversation).where(models.Conversation.student_id == student.id)
    ).all()
    out = []
    for convo in convos:
        asked = [m for m in convo.messages if m.role == "user" and m.events]
        if not asked:
            continue
        first = "".join(e.get("delta", "") for e in asked[0].events if e.get("type") == "text")
        title = " ".join(first.split())
        out.append(
            ConversationSummary(
                id=convo.id,
                title=title if len(title) <= 80 else title[:79].rstrip() + "…",
                last_at=convo.messages[-1].created_at,
                questions=len(asked),
            )
        )
    out.sort(key=lambda c: c.last_at, reverse=True)
    return out[:limit]


@router.get("/latest")
def latest_conversation(db: DB, student: CurrentStudent) -> Conversation | None:
    convo = db.scalar(
        select(models.Conversation)
        .where(models.Conversation.student_id == student.id)
        .order_by(models.Conversation.id.desc())
    )
    return _conversation(db, student, convo) if convo else None


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, db: DB, student: CurrentStudent) -> Conversation:
    convo = db.get(models.Conversation, conversation_id)
    if convo is None or convo.student_id != student.id:
        raise HTTPException(404, "no such conversation")
    return _conversation(db, student, convo)


def _conversation(db: Session, student: models.Student, convo: models.Conversation) -> Conversation:
    current = _current_proposals(db, student, convo)
    out = []
    for m in convo.messages:
        if not m.events:
            continue
        role = "user" if m.role == "user" else "assistant"
        events = [
            {**e, "proposal": current[e["proposal"]["id"]]}
            if e.get("type") == "proposal" and e["proposal"]["id"] in current
            else e
            for e in m.events
        ]
        out.append(ChatMessage(id=m.id, role=role, events=events))
    return Conversation(id=convo.id, messages=out)


def _current_proposals(db: Session, student: models.Student, convo: models.Conversation):
    """Proposals in this conversation as they stand now; events keep the snapshot from creation."""
    ids = [
        e["proposal"]["id"]
        for m in convo.messages
        for e in m.events or []
        if e.get("type") == "proposal"
    ]
    if not ids or not student.plans:
        return {}
    plan = services.get_plan(db, student)
    rows = db.scalars(
        select(models.Proposal).where(
            models.Proposal.id.in_(ids), models.Proposal.plan_id == plan.id
        )
    )
    return {r.id: services.proposal_schema(r, plan.version) for r in rows}
