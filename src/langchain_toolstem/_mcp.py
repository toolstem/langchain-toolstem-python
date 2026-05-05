"""Core MCP discovery: connect to a Toolstem MCP endpoint, list tools, and
return LangChain DynamicStructuredTool instances."""

from __future__ import annotations

import json
from typing import Any

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model

# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

FINANCE_URL = "https://mcp.toolstem.com/mcp/finance"
SEC_URL = "https://mcp.toolstem.com/mcp/sec"


async def discover_toolstem_tools(
    url: str,
    *,
    http_client: httpx.AsyncClient | None = None,
    headers: dict[str, str] | None = None,
) -> list[StructuredTool]:
    """Connect to a Toolstem MCP endpoint via Streamable HTTP, run
    ``initialize`` + ``tools/list``, and return LangChain
    ``StructuredTool`` instances.

    Each tool's ``.invoke()`` sends a JSON-RPC ``tools/call`` to the same
    endpoint, reusing the MCP session.

    Parameters
    ----------
    url:
        Full MCP endpoint URL (e.g. ``https://mcp.toolstem.com/mcp/finance``).
    http_client:
        Optional ``httpx.AsyncClient`` — pass a paying client from
        :func:`create_x402_httpx_client` to enable paid tool calls.
    headers:
        Extra headers merged into every request.
    """
    client = http_client or httpx.AsyncClient(timeout=30.0)
    owns_client = http_client is None

    base_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if headers:
        base_headers.update(headers)

    try:
        session = _McpSession(url=url, client=client, headers=base_headers)
        await session.initialize()
        raw_tools = await session.list_tools()
        return [_to_langchain_tool(t, session) for t in raw_tools]
    except Exception:
        if owns_client:
            await client.aclose()
        raise


# ---------------------------------------------------------------------------
# MCP JSON-RPC session (Streamable HTTP transport)
# ---------------------------------------------------------------------------

class _McpSession:
    """Minimal MCP client over Streamable HTTP (JSON-RPC over POST)."""

    def __init__(
        self,
        url: str,
        client: httpx.AsyncClient,
        headers: dict[str, str],
    ) -> None:
        self.url = url
        self.client = client
        self.headers = dict(headers)
        self._next_id = 1
        self._session_id: str | None = None

    def _make_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        rid = self._next_id
        self._next_id += 1
        msg: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": rid,
            "method": method,
        }
        if params is not None:
            msg["params"] = params
        return msg

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        hdrs = dict(self.headers)
        if self._session_id:
            hdrs["Mcp-Session-Id"] = self._session_id

        resp = await self.client.post(self.url, json=body, headers=hdrs)
        resp.raise_for_status()

        # Capture session id from response headers
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid

        # The response may be a JSON-RPC response or SSE stream.
        # For Streamable HTTP, non-streaming responses come back as JSON.
        ct = resp.headers.get("content-type", "")
        if "text/event-stream" in ct:
            return _parse_sse_response(resp.text)
        return resp.json()  # type: ignore[no-any-return]

    async def initialize(self) -> dict[str, Any]:
        body = self._make_request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "langchain-toolstem-python", "version": "0.1.0"},
        })
        result = await self._post(body)
        # Send initialized notification (no id, no response expected)
        notif: dict[str, Any] = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        hdrs = dict(self.headers)
        if self._session_id:
            hdrs["Mcp-Session-Id"] = self._session_id
        await self.client.post(self.url, json=notif, headers=hdrs)
        return result

    async def list_tools(self) -> list[dict[str, Any]]:
        body = self._make_request("tools/list")
        resp = await self._post(body)
        result = resp.get("result", {})
        return result.get("tools", [])  # type: ignore[no-any-return]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        body = self._make_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        resp = await self._post(body)
        if "error" in resp:
            raise RuntimeError(f"MCP tools/call error: {resp['error']}")
        result = resp.get("result", {})
        # Return structuredContent if present, otherwise text from content array
        if "structuredContent" in result:
            return result["structuredContent"]
        content = result.get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        combined = "\n".join(texts)
        try:
            return json.loads(combined)
        except (json.JSONDecodeError, ValueError):
            return combined


def _parse_sse_response(text: str) -> dict[str, Any]:
    """Extract the JSON-RPC response from an SSE stream body."""
    for line in text.splitlines():
        if line.startswith("data: "):
            payload = line[6:].strip()
            if payload:
                parsed = json.loads(payload)
                # Return the first message that has an "id" (i.e. a response, not a notification)
                if "id" in parsed:
                    return parsed  # type: ignore[no-any-return]
    raise RuntimeError(f"No JSON-RPC response found in SSE stream: {text[:500]}")


# ---------------------------------------------------------------------------
# Convert MCP tool descriptors to LangChain StructuredTool
# ---------------------------------------------------------------------------

def _json_schema_to_pydantic_field(
    name: str, schema: dict[str, Any], required: bool
) -> tuple[type, Any]:
    """Map a JSON Schema property to a (type, default) pair for Pydantic."""
    type_map: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }
    json_type = schema.get("type", "string")

    if json_type == "array":
        item_type = type_map.get(schema.get("items", {}).get("type", "string"), str)
        py_type: type = list[item_type]  # type: ignore[valid-type]
    elif json_type == "object":
        py_type = dict[str, Any]
    else:
        py_type = type_map.get(json_type, str)

    default = ... if required else schema.get("default", None)
    return (py_type, default)


def _build_args_model(tool_name: str, input_schema: dict[str, Any]) -> type[BaseModel]:
    """Build a Pydantic model from an MCP tool's inputSchema."""
    properties = input_schema.get("properties", {})
    required_set = set(input_schema.get("required", []))

    fields: dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        fields[prop_name] = _json_schema_to_pydantic_field(
            prop_name, prop_schema, prop_name in required_set
        )

    model_name = f"{tool_name}_args"
    return create_model(model_name, **fields)  # type: ignore[call-overload]


def _to_langchain_tool(mcp_tool: dict[str, Any], session: _McpSession) -> StructuredTool:
    """Convert a single MCP tool descriptor to a LangChain StructuredTool."""
    name = mcp_tool["name"]
    description = mcp_tool.get("description", "")
    input_schema = mcp_tool.get("inputSchema", {"type": "object", "properties": {}})

    args_model = _build_args_model(name, input_schema)

    async def _acall(**kwargs: Any) -> Any:
        return await session.call_tool(name, kwargs)

    def _call(**kwargs: Any) -> Any:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, session.call_tool(name, kwargs)).result()
        return asyncio.run(session.call_tool(name, kwargs))

    return StructuredTool(
        name=name,
        description=description,
        args_schema=args_model,
        func=_call,
        coroutine=_acall,
    )
