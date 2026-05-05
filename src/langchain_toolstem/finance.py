"""Finance MCP tools: ``get_stock_snapshot``, ``get_company_metrics``,
``compare_companies``.

Discover and return LangChain tools connected to the Toolstem Finance MCP
server at ``https://mcp.toolstem.com/mcp/finance``.
"""

from __future__ import annotations

import httpx
from langchain_core.tools import StructuredTool

from langchain_toolstem._mcp import FINANCE_URL, discover_toolstem_tools

EXPECTED_TOOLS = frozenset({
    "get_stock_snapshot",
    "get_company_metrics",
    "compare_companies",
})


async def create_finance_tools(
    *,
    url: str = FINANCE_URL,
    http_client: httpx.AsyncClient | None = None,
    headers: dict[str, str] | None = None,
) -> list[StructuredTool]:
    """Discover and return the 3 Toolstem Finance tools as LangChain tools.

    ``initialize`` and ``tools/list`` are free. Each ``tools/call`` costs
    0.01 USDC on Base mainnet — pass a paying ``http_client`` from
    :func:`~langchain_toolstem.create_x402_httpx_client` to enable paid calls.

    Parameters
    ----------
    url:
        MCP endpoint URL. Defaults to the production Finance endpoint.
    http_client:
        Optional paying ``httpx.AsyncClient``.
    headers:
        Extra headers for every request.

    Returns
    -------
    list[StructuredTool]
        LangChain tools ready for use with agents.
    """
    return await discover_toolstem_tools(url, http_client=http_client, headers=headers)
