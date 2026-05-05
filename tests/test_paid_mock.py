"""Mocked paid call tests — no real USDC spent.

Verifies that the x402 payment flow is wired correctly by mocking
the HTTP 402 → payment → retry cycle.
"""

import base64
import json

import httpx
import pytest

from langchain_toolstem._mcp import _McpSession


class _PaymentMockTransport(httpx.AsyncBaseTransport):
    """Simulates an MCP server that returns 402 on tools/call, then
    accepts the retry with a payment header."""

    def __init__(self) -> None:
        self.call_count = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        method = body.get("method", "")
        self.call_count += 1

        # initialize — always free
        if method == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"protocolVersion": "2025-03-26"},
                },
                headers={
                    "content-type": "application/json",
                    "mcp-session-id": "paid-session",
                },
            )

        # notifications — accept silently
        if "id" not in body:
            return httpx.Response(200, json={"jsonrpc": "2.0"}, headers={"content-type": "application/json"})

        # tools/list — always free
        if method == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "tools": [{
                            "name": "get_stock_snapshot",
                            "description": "Snapshot",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"symbol": {"type": "string"}},
                                "required": ["symbol"],
                            },
                        }],
                    },
                },
                headers={"content-type": "application/json"},
            )

        # tools/call — check for payment header
        if method == "tools/call":
            payment = request.headers.get("x-payment")
            if not payment:
                # Return 402 with payment-required header
                payment_required = {
                    "accepts": [{
                        "scheme": "exact",
                        "network": "eip155:8453",
                        "asset": "USDC",
                        "amount": "10000",
                        "pay_to": "0x1234567890abcdef1234567890abcdef12345678",
                    }],
                }
                return httpx.Response(
                    402,
                    headers={
                        "content-type": "application/json",
                        "payment-required": base64.b64encode(
                            json.dumps(payment_required).encode()
                        ).decode(),
                    },
                    json={"error": "Payment required"},
                )
            # Payment provided — return result
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "structuredContent": {"symbol": "AAPL", "price": 198.50},
                    },
                },
                headers={"content-type": "application/json"},
            )

        return httpx.Response(404)


@pytest.mark.asyncio
async def test_free_discovery_succeeds_without_payment() -> None:
    """initialize + tools/list should succeed without any payment."""
    transport = _PaymentMockTransport()
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
async def test_tools_call_returns_402_without_payment() -> None:
    """tools/call without payment returns HTTP 402."""
    transport = _PaymentMockTransport()
    client = httpx.AsyncClient(transport=transport)
    session = _McpSession(
        url="https://example.com/mcp",
        client=client,
        headers={"Content-Type": "application/json"},
    )
    await session.initialize()

    # Direct tools/call without payment should get 402
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await session.call_tool("get_stock_snapshot", {"symbol": "AAPL"})
    assert exc_info.value.response.status_code == 402


@pytest.mark.asyncio
async def test_tools_call_succeeds_with_payment_header() -> None:
    """tools/call with X-PAYMENT header returns data."""
    transport = _PaymentMockTransport()
    client = httpx.AsyncClient(transport=transport)

    # Simulate a pre-paid session by adding the payment header
    session = _McpSession(
        url="https://example.com/mcp",
        client=client,
        headers={
            "Content-Type": "application/json",
            "x-payment": base64.b64encode(b'{"signed": true}').decode(),
        },
    )
    await session.initialize()
    result = await session.call_tool("get_stock_snapshot", {"symbol": "AAPL"})
    assert result["symbol"] == "AAPL"
    assert result["price"] == 198.50
