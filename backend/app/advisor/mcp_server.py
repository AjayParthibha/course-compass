"""Expose the tool registry over MCP.

The advisor loop connects to this in-process for every turn. You can also run
it over stdio for an MCP client or poking at tools by hand:

    uv run python -m app.advisor.mcp_server --student DEMO-1
"""

import argparse
import inspect
import json

from mcp.server.mcpserver import MCPServer
from sqlalchemy import select

from app.advisor.tools import REGISTRY, Tool, ToolContext


def _bind(tool: Tool, ctx: ToolContext):
    def handler(**kwargs) -> str:
        result = tool.call(ctx, kwargs)
        return json.dumps({"summary": result.summary, "data": result.data}, default=str)

    params = list(inspect.signature(tool.fn).parameters.values())[1:]
    handler.__signature__ = inspect.Signature(params, return_annotation=str)
    handler.__annotations__ = {p.name: p.annotation for p in params} | {"return": str}
    handler.__name__ = tool.name
    return handler


def build_server(ctx: ToolContext) -> MCPServer:
    server = MCPServer(name="coursecompass")
    for tool in REGISTRY.values():
        server.add_tool(_bind(tool, ctx), name=tool.name, description=tool.description)
    return server


if __name__ == "__main__":
    from app import models
    from app.models import SessionLocal

    parser = argparse.ArgumentParser()
    parser.add_argument("--student", required=True, help="participant code")
    args = parser.parse_args()

    db = SessionLocal()
    student = db.scalar(select(models.Student).where(models.Student.code == args.student.upper()))
    if student is None:
        raise SystemExit(f"no participant {args.student}")
    build_server(ToolContext(db=db, student=student)).run()
