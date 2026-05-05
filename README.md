# langchain-toolstem

LangChain tools wrapping [Toolstem](https://toolstem.com) MCP servers (Finance + SEC EDGAR) with [x402](https://x402.org) USDC micropayments — Python edition.

| Surface | Tools | Endpoint |
|---------|-------|----------|
| **Finance** | `get_stock_snapshot`, `get_company_metrics`, `compare_companies` | `https://mcp.toolstem.com/mcp/finance` |
| **SEC EDGAR** | `get_company_filings_summary`, `get_insider_signal`, `get_institutional_signal`, `get_material_events_digest`, `compare_disclosure_signals` | `https://mcp.toolstem.com/mcp/sec` |

**`initialize` and `tools/list` are free.** Each `tools/call` costs **$0.01 USDC** on Base mainnet.

> TypeScript sibling: [langchain-toolstem](https://github.com/toolstem/langchain-toolstem)

## Install

```bash
pip install langchain-toolstem
```

With x402 payment support:

```bash
pip install 'langchain-toolstem[x402]'
```

## Quick Start

### Free Discovery (no wallet needed)

```python
from langchain_toolstem import create_finance_tools, create_sec_tools

# List available tools — free, no payment required
finance_tools = await create_finance_tools()
sec_tools = await create_sec_tools()

for t in finance_tools + sec_tools:
    print(f"{t.name}: {t.description[:80]}")
```

### Paid Tool Calls (with wallet)

```python
from langchain_toolstem import create_finance_tools, create_x402_httpx_client

# Create a paying HTTP client (needs USDC on Base mainnet)
client = await create_x402_httpx_client("0xYOUR_PRIVATE_KEY")

# Tools automatically pay 0.01 USDC per call
tools = await create_finance_tools(http_client=client)
result = await tools[0].ainvoke({"symbol": "AAPL"})
print(result)
```

### With LangGraph Agent

```python
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from langchain_toolstem import create_finance_tools, create_x402_httpx_client

client = await create_x402_httpx_client(os.environ["X402_PRIVATE_KEY"])
tools = await create_finance_tools(http_client=client)

agent = create_react_agent(ChatOpenAI(model="gpt-4o"), tools)
result = await agent.ainvoke({
    "messages": [{"role": "user", "content": "Analyze NVDA stock"}]
})
```

## API Reference

### `create_finance_tools(**kwargs) -> list[StructuredTool]`

Discover and return the 3 Finance tools.

### `create_sec_tools(**kwargs) -> list[StructuredTool]`

Discover and return the 5 SEC EDGAR tools.

### `create_x402_httpx_client(private_key, *, max_payment_usd=1.0) -> httpx.AsyncClient`

Create an `httpx.AsyncClient` that auto-pays x402 USDC micropayments on HTTP 402.

### `discover_toolstem_tools(url, **kwargs) -> list[StructuredTool]`

Low-level: connect to any Toolstem MCP endpoint and return LangChain tools.

**Common kwargs for all functions:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `http_client` | `httpx.AsyncClient` | `None` | Paying client from `create_x402_httpx_client` |
| `headers` | `dict[str, str]` | `None` | Extra headers for every request |
| `url` | `str` | endpoint default | Override the MCP endpoint URL |

## Network Details

| Field | Value |
|-------|-------|
| Chain | Base mainnet (`eip155:8453`) |
| Token | USDC |
| Contract | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| Price per call | $0.01 |
| Wallets | Any EVM wallet (Coinbase Smart Wallet, MetaMask, etc.) |

## Walletless Playground

Try the tools without a wallet at [toolstem.com/playground](https://toolstem.com/playground) — real, cached responses, no payment required.

## Development

```bash
git clone https://github.com/toolstem/langchain-toolstem-python
cd langchain-toolstem-python
pip install -e '.[dev]'
pytest
```

## Publishing to PyPI

This package uses **PyPI Trusted Publishing** (OIDC) — no API tokens needed.

### One-time setup:

1. Go to [pypi.org/manage/account/publishing](https://pypi.org/manage/account/publishing/)
2. Add a new **pending publisher**:
   - PyPI project name: `langchain-toolstem`
   - Owner: `toolstem`
   - Repository: `langchain-toolstem-python`
   - Workflow: `publish.yml`
   - Environment: `pypi`
3. Tag a release: `git tag v0.1.0 && git push origin v0.1.0`
4. GitHub Actions will build and publish automatically.

## License

MIT
