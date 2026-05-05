# Changelog

## 0.1.0 (2026-05-05)

Initial release.

- MCP discovery via Streamable HTTP (JSON-RPC over POST)
- Finance tools: `get_stock_snapshot`, `get_company_metrics`, `compare_companies`
- SEC EDGAR tools: `get_company_filings_summary`, `get_insider_signal`, `get_institutional_signal`, `get_material_events_digest`, `compare_disclosure_signals`
- x402 USDC micropayments via `x402` Python SDK (optional dependency)
- LangChain `StructuredTool` integration with full Pydantic schemas
- Async-first API with sync fallback
- PyPI Trusted Publishing (OIDC) CI/CD
