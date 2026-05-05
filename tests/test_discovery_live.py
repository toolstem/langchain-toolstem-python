"""Live integration tests: free discovery against mcp.toolstem.com.

These tests hit the real MCP endpoints but only use free operations
(initialize + tools/list). No wallet or USDC required.
"""

import pytest

from langchain_toolstem.finance import EXPECTED_TOOLS as FINANCE_EXPECTED
from langchain_toolstem.finance import create_finance_tools
from langchain_toolstem.sec import EXPECTED_TOOLS as SEC_EXPECTED
from langchain_toolstem.sec import create_sec_tools


@pytest.mark.asyncio
async def test_finance_discovery() -> None:
    """Finance endpoint returns exactly 3 expected tools."""
    tools = await create_finance_tools()
    names = {t.name for t in tools}
    assert names == FINANCE_EXPECTED, (
        f"Expected {sorted(FINANCE_EXPECTED)}, got {sorted(names)}"
    )


@pytest.mark.asyncio
async def test_sec_discovery() -> None:
    """SEC endpoint returns exactly 5 expected tools."""
    tools = await create_sec_tools()
    names = {t.name for t in tools}
    assert names == SEC_EXPECTED, (
        f"Expected {sorted(SEC_EXPECTED)}, got {sorted(names)}"
    )


@pytest.mark.asyncio
async def test_finance_tools_have_descriptions() -> None:
    """Every discovered finance tool has a non-empty description."""
    tools = await create_finance_tools()
    for tool in tools:
        assert tool.description, f"Tool {tool.name} has no description"
        assert len(tool.description) > 10, (
            f"Tool {tool.name} description too short: {tool.description!r}"
        )


@pytest.mark.asyncio
async def test_sec_tools_have_descriptions() -> None:
    """Every discovered SEC tool has a non-empty description."""
    tools = await create_sec_tools()
    for tool in tools:
        assert tool.description, f"Tool {tool.name} has no description"
        assert len(tool.description) > 10, (
            f"Tool {tool.name} description too short: {tool.description!r}"
        )
