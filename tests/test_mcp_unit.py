"""Unit tests for MCP session and tool conversion logic.

These tests mock HTTP responses — no network access needed.
"""

import json

import httpx
import pytest

from langchain_toolstem._mcp import _McpSession, _build_args_model, _to_langchain_tool


# ---------------------------------------------------------------------------
# _build_args_model
# ---------------------------------------------------------------------------

def test_build_args_model_simple() -> None:
    schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Ticker symbol"},
            "period": {"type": "string", "default": "annual"},
        },
        "required": ["symbol"],
    }
    Model = _build_args_model("test_tool", schema)
    assert Model.__name__ == "test_tool_args"

    # Required field
    instance = Model(symbol="AAPL")
    assert instance.symbol == "AAPL"  # type: ignore[attr-defined]
    assert instance.period == "annual"  # type: ignore[attr-defined]


def test_build_args_model_array_field() -> None:
    schema = {
        "type": "object",
        "properties": {
            "symbols": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["symbols"],
    }
    Model = _build_args_model("compare", schema)
    instance = Model(symbols=["AAPL", "MSFT"])
    assert instance.symbols == ["AAPL", "MSFT"]  # type: ignore[attr-defined]


def test_build_args_model_optional_fields() -> None:
    schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": [],
    }
    Model = _build_args_model("optional_test", schema)
    instance = Model()
    assert instance.symbol is None  # type: ignore[attr-defined]
    assert instance.limit is None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# _McpSession (mocked HTTP)
# ---------------------------------------------------------------------------

class _MockTransport(httpx.AsyncBaseTransport):
    """Mock transport that returns pre-configured JSON-RPC responses."""

    def __init__(self) -> None:
        self.call_count = 0
        self.responses: list[dict] = []

    def add_response(self, body: dict, headers: dict[str, str] | None = None) -> None:
        self.responses.append({"body": body, "headers": headers or {}})

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        idx = min(self.call_count, len(self.responses) - 1)
        resp_def = self.responses[idx]
        self.call_count += 1
        headers = {"content-type": "application/json", **resp_def.get("headers", {})}
        return httpx.Response(
            200,
            json=resp_def["body"],
            headers=headers,
        )


@pytest.mark.asyncio
async def test_session_initialize() -> None:
    transport = _MockTransport()
    # initialize response
    transport.add_response(
        {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
        {"mcp-session-id": "test-session-123"},
    )
    # notification response (ignored)
    transport.add_response({"jsonrpc": "2.0"})

    client = httpx.AsyncClient(transport=transport)
    session = _McpSession(
        url="https://example.com/mcp",
        client=client,
        headers={"Content-Type": "application/json"},
    )

    result = await session.initialize()
    assert result["result"]["protocolVersion"] == "2025-03-26"
    assert session._session_id == "test-session-123"


@pytest.mark.asyncio
async def test_session_list_tools() -> None:
    transport = _MockTransport()
    # initialize
    transport.add_response(
        {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
        {"mcp-session-id": "sess-1"},
    )
    # notification
    transport.add_response({"jsonrpc": "2.0"})
    # tools/list
    transport.add_response({
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "tools": [
                {
                    "name": "get_stock_snapshot",
                    "description": "Get a stock snapshot",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"symbol": {"type": "string"}},
                        "required": ["symbol"],
                    },
                }
            ]
        },
    })

    client = httpx.AsyncClient(transport=transport)
    session = _McpSession(
        url="https://example.com/mcp",
        client=client,
        headers={"Content-Type": "application/json"},
    )
    await session.initialize()
    tools = await session.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "get_stock_snapshot"


@pytest.mark.asyncio
async def test_session_call_tool_structured() -> None:
    transport = _MockTransport()
    # initialize
    transport.add_response(
        {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
        {"mcp-session-id": "sess-2"},
    )
    # notification
    transport.add_response({"jsonrpc": "2.0"})
    # tools/call
    transport.add_response({
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "structuredContent": {"symbol": "AAPL", "price": 198.50},
        },
    })

    client = httpx.AsyncClient(transport=transport)
    session = _McpSession(
        url="https://example.com/mcp",
        client=client,
        headers={"Content-Type": "application/json"},
    )
    await session.initialize()
    result = await session.call_tool("get_stock_snapshot", {"symbol": "AAPL"})
    assert result == {"symbol": "AAPL", "price": 198.50}


@pytest.mark.asyncio
async def test_session_call_tool_text_fallback() -> None:
    transport = _MockTransport()
    transport.add_response(
        {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
        {"mcp-session-id": "sess-3"},
    )
    transport.add_response({"jsonrpc": "2.0"})
    # tools/call returns text content (no structuredContent)
    transport.add_response({
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "content": [{"type": "text", "text": '{"answer": 42}'}],
        },
    })

    client = httpx.AsyncClient(transport=transport)
    session = _McpSession(
        url="https://example.com/mcp",
        client=client,
        headers={"Content-Type": "application/json"},
    )
    await session.initialize()
    result = await session.call_tool("some_tool", {"q": "hello"})
    assert result == {"answer": 42}


@pytest.mark.asyncio
async def test_session_call_tool_error() -> None:
    transport = _MockTransport()
    transport.add_response(
        {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
        {"mcp-session-id": "sess-4"},
    )
    transport.add_response({"jsonrpc": "2.0"})
    transport.add_response({
        "jsonrpc": "2.0",
        "id": 2,
        "error": {"code": -32600, "message": "Invalid tool"},
    })

    client = httpx.AsyncClient(transport=transport)
    session = _McpSession(
        url="https://example.com/mcp",
        client=client,
        headers={"Content-Type": "application/json"},
    )
    await session.initialize()
    with pytest.raises(RuntimeError, match="MCP tools/call error"):
        await session.call_tool("bad_tool", {})
