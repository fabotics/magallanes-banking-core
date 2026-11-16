"""MCP server: the merchant registry lookup as a tool for agents.

MCP (Model Context Protocol) is a standard way to offer tools to an AI agent.
This module serves one tool, `lookup_merchant`, at `/mcp` over the Streamable
HTTP transport, stateless and with plain JSON answers.

The hosting runs each request in a short-lived function, so nothing here
depends on a startup hook: every request builds its own small MCP server,
runs it for that one request and shuts it down.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app import audit
from app.db import Repository, get_repository
from app.routers.registry import find_merchant, normalize_tax_id
from app.security import require_api_key_or_bearer

router = APIRouter(tags=["mcp"])

# The SDK's host check protects servers on a developer's machine from web
# pages. This endpoint is public and guarded by the API key instead.
NO_HOST_CHECK = TransportSecuritySettings(enable_dns_rebinding_protection=False)


TOOL_DESCRIPTION = (
    "Find the business registered under a merchant tax ID. Use it when a customer does not "
    "recognize a card charge: the trade name and city usually tell them where they bought. "
    "An unknown tax ID answers with found false, not with an error."
)


def build_server(repository: Repository) -> MCPServer:
    """Create an MCP server whose single tool reads the merchant registry."""
    server = MCPServer(
        "Banco Magallanes merchant registry",
        instructions="Look up the business behind a merchant tax ID from a card statement.",
        log_level="WARNING",
    )

    @server.tool(description=TOOL_DESCRIPTION)
    def lookup_merchant(tax_id: str) -> dict[str, Any]:
        """Return trade name, legal name, category and city, or found false."""
        merchant = find_merchant(repository, tax_id)
        if merchant is None:
            return {
                "found": False,
                "tax_id": normalize_tax_id(tax_id),
                "message": "No business is registered under this tax ID.",
            }
        return {
            "found": True,
            "tax_id": merchant["tax_id"],
            "trade_name": merchant["trade_name"],
            "legal_name": merchant["legal_name"],
            "category": merchant["activity"],
            "city": merchant["commune"],
        }

    return server


async def run_once(server: MCPServer, request: Request) -> Response:
    """Let the MCP server answer this one request and return its answer.

    The SDK gives us a small web app. We start it, hand it the raw request,
    collect what it sends back, and stop it. Answers are single JSON bodies,
    so collecting them in memory is safe.
    """
    mcp_app = server.streamable_http_app(
        stateless_http=True, json_response=True, transport_security=NO_HOST_CHECK
    )
    answer: dict[str, Any] = {"status": 500, "headers": {}, "body": b""}

    async def collect(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            answer["status"] = message["status"]
            for name, value in message.get("headers", []):
                if name.lower() != b"content-length":
                    answer["headers"][name.decode()] = value.decode()
        elif message["type"] == "http.response.body":
            answer["body"] += message.get("body", b"")

    async with mcp_app.router.lifespan_context(mcp_app):
        await mcp_app(dict(request.scope), request.receive, collect)
    return Response(answer["body"], status_code=answer["status"], headers=answer["headers"])


@router.api_route(
    "/mcp",
    methods=["GET", "POST", "DELETE"],
    include_in_schema=False,
    dependencies=[Depends(require_api_key_or_bearer)],
)
async def mcp_endpoint(
    request: Request, repository: Annotated[Repository, Depends(get_repository)]
) -> Response:
    """The MCP endpoint. Same key as `/v1`, in `X-API-Key` or as a bearer token."""
    audit.note(request, outcome="mcp")
    return await run_once(build_server(repository), request)
