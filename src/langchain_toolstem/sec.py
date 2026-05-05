"""SEC EDGAR MCP tools: ``get_company_filings_summary``,
``get_insider_signal``, ``get_institutional_signal``,
``get_material_events_digest``, ``compare_disclosure_signals``.

Discover and return LangChain tools connected to the Toolstem SEC MCP
server at ``https://mcp.toolstem.com/mcp/sec``.
"""

from __future__ import annotations

import httpx
from langchain_core.tools import StructuredTool

from langchain_toolstem._mcp import SEC_URL, discover_toolstem_tools

EXPECTED_TOOLS = frozenset({
    "get_company_filings_summary",
    "get_insider_signal",
    "get_institutional_signal",
    "get_material_events_digest",
    "compare_disclosure_signals",
})


async def create_sec_tools(
    *,
    url: str = SEC_URL,
    http_client: httpx.AsyncClient | None = None,
    headers: dict[str, str] | None = None,
) -> list[StructuredTool]:
    """Discover and return the 5 Toolstem SEC EDGAR tools as LangChain tools.

    ``initialize`` and ``tools/list`` are free. Each ``tools/call`` costs
    0.01 USDC on Base mainnet — pass a paying ``http_client`` from
    :func:`~langchain_toolstem.create_x402_httpx_client` to enable paid calls.

    Parameters
    ----------
    url:
        MCP endpoint URL. Defaults to the production SEC endpoint.
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
