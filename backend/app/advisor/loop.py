"""One advisor turn: stream the model's reply, run tool calls through MCP, repeat.

Yields the SSE events the chat panel renders. Every model call and tool call is
logged to agent_events for cost and evaluation numbers.
"""

import json
import time
from collections.abc import AsyncIterator

import openai
from mcp.client import Client
from sqlalchemy.orm import Session

from app import models
from app.advisor.mcp_server import build_server
from app.advisor.prompts import SYSTEM, context_block
from app.advisor.tools import ToolContext, tool_schemas
from app.config import get_settings
from app.schemas.advisor import DoneEvent, ErrorEvent, TextEvent, ToolEndEvent, ToolStartEvent

MAX_RESULT_CHARS = 20_000


def get_conversation(db: Session, student: models.Student, conversation_id: int | None):
    if conversation_id:
        convo = db.get(models.Conversation, conversation_id)
        if convo and convo.student_id == student.id:
            return convo
    convo = models.Conversation(student_id=student.id)
    db.add(convo)
    db.commit()
    return convo


def _tool_output(result) -> tuple[str, str]:
    """(text for the model, summary for the UI) from an MCP CallToolResult."""
    text = "".join(getattr(c, "text", "") for c in result.content)
    if result.is_error:
        return text, f"error: {text[:80]}"
    try:
        payload = json.loads(text)
        return json.dumps(payload.get("data"), default=str)[:MAX_RESULT_CHARS], payload["summary"]
    except (ValueError, KeyError):
        return text[:MAX_RESULT_CHARS], text[:80]


async def run_turn(
    db: Session, student: models.Student, conversation_id: int | None, user_text: str
) -> AsyncIterator:
    settings = get_settings()
    convo = get_conversation(db, student, conversation_id)
    # each Message row holds Responses API input items
    history = [item for m in convo.messages for item in m.content]
    new_rows = [
        models.Message(
            conversation_id=convo.id, role="user", content=[{"role": "user", "content": user_text}]
        )
    ]
    items = history + new_rows[0].content
    ui_events: list = []

    def emit(event):
        ui_events.append(event)
        return event

    if not settings.openai_api_key:
        yield emit(ErrorEvent(message="The advisor isn't configured (OPENAI_API_KEY is not set)."))
        yield DoneEvent(conversation_id=convo.id)
        return

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    ctx = ToolContext(db=db, student=student, conversation_id=convo.id)
    instructions = SYSTEM + "\n\n" + context_block(db, student, convo.id)
    tools = tool_schemas()

    try:
        async with Client(build_server(ctx)) as mcp:
            for _ in range(settings.max_tool_calls + 1):
                started = time.monotonic()
                async with client.responses.stream(
                    model=settings.advisor_model,
                    instructions=instructions,
                    input=items,
                    tools=tools,
                    reasoning={"effort": settings.advisor_effort},
                    store=False,
                    include=["reasoning.encrypted_content"],
                ) as stream:
                    async for event in stream:
                        if event.type == "response.output_text.delta":
                            yield emit(TextEvent(delta=event.delta))
                    final = await stream.get_final_response()

                usage = final.usage
                db.add(
                    models.AgentEvent(
                        conversation_id=convo.id,
                        kind="llm",
                        name=final.model,
                        model=final.model,
                        input_tokens=usage.input_tokens if usage else None,
                        output_tokens=usage.output_tokens if usage else None,
                        cache_read_tokens=usage.input_tokens_details.cached_tokens
                        if usage
                        else None,
                        latency_ms=int((time.monotonic() - started) * 1000),
                    )
                )
                output = [o.model_dump(mode="json", exclude_none=True) for o in final.output]
                items += output
                new_rows.append(
                    models.Message(conversation_id=convo.id, role="assistant", content=output)
                )

                refused = any(
                    c.type == "refusal"
                    for o in final.output
                    if o.type == "message"
                    for c in o.content
                )
                if refused:
                    yield emit(ErrorEvent(message="The advisor couldn't help with that request."))
                    break
                calls = [o for o in final.output if o.type == "function_call"]
                if not calls:
                    break

                results = []
                for call in calls:
                    try:
                        args = json.loads(call.arguments or "{}")
                    except ValueError:
                        args = {}
                    yield emit(ToolStartEvent(id=call.call_id, name=call.name, args=args))
                    started = time.monotonic()
                    result = await mcp.call_tool(call.name, args)
                    text, summary = _tool_output(result)
                    db.add(
                        models.AgentEvent(
                            conversation_id=convo.id,
                            kind="tool",
                            name=call.name,
                            input=args,
                            summary=summary,
                            latency_ms=int((time.monotonic() - started) * 1000),
                        )
                    )
                    yield emit(
                        ToolEndEvent(
                            id=call.call_id, name=call.name, summary=summary, ok=not result.is_error
                        )
                    )
                    for e in ctx.events:
                        yield emit(e)
                    ctx.events.clear()
                    output = f"Error: {text}" if result.is_error else text
                    results.append(
                        {"type": "function_call_output", "call_id": call.call_id, "output": output}
                    )

                items += results
                new_rows.append(
                    models.Message(conversation_id=convo.id, role="tool", content=results)
                )
                if ctx.end_turn:
                    break
    except openai.APIError as e:
        yield emit(ErrorEvent(message=f"The advisor hit an API error: {e.message}"))

    new_rows[0].events = [TextEvent(delta=user_text).model_dump()]
    if len(new_rows) > 1:
        new_rows[-1].events = [e.model_dump(mode="json") for e in ui_events]
    db.add_all(new_rows)
    db.commit()
    yield DoneEvent(conversation_id=convo.id)
