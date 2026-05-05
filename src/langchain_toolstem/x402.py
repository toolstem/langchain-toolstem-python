"""x402 payment integration for Toolstem MCP servers.

Provides a paying ``httpx.AsyncClient`` that automatically handles HTTP 402
responses by signing EIP-3009 USDC ``transferWithAuthorization`` on Base
mainnet and retrying with the payment header.

Requires the ``x402`` optional dependency::

    pip install langchain-toolstem[x402]
"""

from __future__ import annotations

from typing import Any

import httpx


async def create_x402_httpx_client(
    private_key: str,
    *,
    max_payment_usd: float = 1.0,
    timeout: float = 30.0,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """Create an ``httpx.AsyncClient`` that auto-pays x402 USDC micropayments.

    Uses the ``x402`` Python SDK to intercept HTTP 402 responses, parse the
    ``payment-required`` header, sign an EIP-3009 USDC authorization on
    Base mainnet, and retry with the ``PAYMENT-SIGNATURE`` header.

    Parameters
    ----------
    private_key:
        Hex-encoded Ethereum private key (with or without ``0x`` prefix).
        Must hold USDC on Base mainnet.
    max_payment_usd:
        Safety cap per request in USD. Defaults to 1.00 USD.
    timeout:
        HTTP timeout in seconds.
    **kwargs:
        Additional keyword arguments forwarded to ``httpx.AsyncClient``.

    Returns
    -------
    httpx.AsyncClient
        A client whose requests automatically handle x402 payment flows.

    Raises
    ------
    ImportError
        If ``x402`` is not installed.

    Example
    -------
    >>> from langchain_toolstem import create_x402_httpx_client, create_finance_tools
    >>> client = await create_x402_httpx_client("0xYOUR_PRIVATE_KEY")
    >>> tools = await create_finance_tools(http_client=client)
    """
    try:
        from x402 import x402Client  # type: ignore[import-untyped]
        from x402.types import x402ClientConfig  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "x402 payment support requires the 'x402' package. "
            "Install it with: pip install 'langchain-toolstem[x402]'"
        ) from exc

    # Normalize private key
    pk = private_key if private_key.startswith("0x") else f"0x{private_key}"

    # Convert USD cap to atomic USDC (6 decimals)
    max_amount = int(max_payment_usd * 1_000_000)

    # Configure the x402 client for Base mainnet EVM payments
    config = x402ClientConfig(
        schemes=[
            {
                "scheme": "exact",
                "network_pattern": "eip155:*",
                "signer_config": {"private_key": pk},
            }
        ],
        policies={"max_amount": max_amount},
    )
    x402_client = x402Client.from_config(config)

    # Create base httpx client
    base_client = httpx.AsyncClient(timeout=timeout, **kwargs)

    # Wrap with x402 payment handling
    try:
        from x402.httpx import wrapHttpxWithPayment  # type: ignore[import-untyped]
        return wrapHttpxWithPayment(base_client, x402_client)  # type: ignore[no-any-return]
    except ImportError:
        # Fallback: manual 402 interception if the httpx wrapper isn't available
        return _ManualX402Client(
            base_client=base_client,
            x402_client=x402_client,
            timeout=timeout,
        )


class _ManualX402Client(httpx.AsyncClient):
    """Fallback wrapper that manually intercepts 402 responses.

    Used when ``x402.httpx.wrapHttpxWithPayment`` is not available in the
    installed x402 version.
    """

    def __init__(
        self,
        base_client: httpx.AsyncClient,
        x402_client: Any,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self._inner = base_client
        self._x402 = x402_client

    async def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        resp = await self._inner.send(request, **kwargs)
        if resp.status_code != 402:
            return resp

        # Parse payment-required header and create payment
        import base64
        import json

        pr_header = resp.headers.get("payment-required", "")
        if not pr_header:
            return resp

        try:
            payment_required = json.loads(base64.b64decode(pr_header))
        except Exception:
            return resp

        # Use x402 client to create payment payload
        payment = await self._x402.create_payment(payment_required)
        if not payment:
            return resp

        # Retry with payment header
        import json as json_mod
        retry_req = request.copy()
        retry_req.headers["X-PAYMENT"] = base64.b64encode(
            json_mod.dumps(payment).encode()
        ).decode()
        return await self._inner.send(retry_req, **kwargs)

    async def aclose(self) -> None:
        await self._inner.aclose()
        await super().aclose()
