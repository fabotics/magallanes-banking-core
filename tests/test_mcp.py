"""The MCP endpoint: one tool, the same key as the REST API, stateless JSON answers."""

from fastapi.testclient import TestClient

from seed.movements import RESTAURANT_TAX_ID
from tests.conftest import API_KEY, TEST_API_KEY
from tests.fake_db import InMemoryRepository

MCP_HEADERS = {"Accept": "application/json, text/event-stream"}
BEARER = {"Authorization": f"Bearer {TEST_API_KEY}"}


def rpc(client: TestClient, method: str, params: dict | None = None, auth: dict = BEARER) -> dict:
    """Send one JSON-RPC request to `/mcp` and return the decoded answer."""
    message = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    response = client.post("/mcp", json=message, headers={**MCP_HEADERS, **auth})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    return response.json()


def lookup(client: TestClient, tax_id: str) -> dict:
    arguments = {"name": "lookup_merchant", "arguments": {"tax_id": tax_id}}
    return rpc(client, "tools/call", arguments)["result"]


def test_exactly_one_tool_is_offered(client: TestClient) -> None:
    tools = rpc(client, "tools/list")["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["lookup_merchant"]
    assert tools[0]["inputSchema"]["required"] == ["tax_id"]


def test_lookup_returns_trade_name_legal_name_category_and_city(client: TestClient) -> None:
    result = lookup(client, RESTAURANT_TAX_ID)
    assert result["isError"] is False
    assert result["structuredContent"] == {
        "found": True,
        "tax_id": "66871234-7",
        "trade_name": "Restaurante El Mirador",
        "legal_name": "Inversiones Gastronomicas Providencia SpA",
        "category": "Restaurant",
        "city": "Providencia",
    }


def test_unknown_tax_id_is_a_clear_not_found_result_not_an_error(client: TestClient) -> None:
    result = lookup(client, "11.111.111-1")
    assert result["isError"] is False
    assert result["structuredContent"]["found"] is False
    assert result["structuredContent"]["tax_id"] == "11111111-1"
    assert "No business" in result["structuredContent"]["message"]


def test_the_key_works_as_a_header_or_as_a_bearer_token(client: TestClient) -> None:
    assert "result" in rpc(client, "tools/list", auth=API_KEY)
    assert "result" in rpc(client, "tools/list", auth=BEARER)


def test_requests_without_a_valid_key_are_refused(client: TestClient) -> None:
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    for auth in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": TEST_API_KEY}):
        response = client.post("/mcp", json=message, headers={**MCP_HEADERS, **auth})
        assert response.status_code == 401
        assert response.json()["error"] == "invalid_api_key"


def test_each_request_stands_alone(client: TestClient) -> None:
    for _ in range(3):
        assert lookup(client, RESTAURANT_TAX_ID)["structuredContent"]["found"] is True


def test_mcp_calls_are_audited(client: TestClient, repository: InMemoryRepository) -> None:
    lookup(client, RESTAURANT_TAX_ID)
    row = repository.select("audit_log")[-1]
    assert row["endpoint"] == "/mcp" and row["outcome"] == "mcp"
    assert TEST_API_KEY not in str(row)
