"""Shared HTTP client for Gmail and Plaid (plain REST over httpx, no vendor SDKs).

Tests swap `transport` for an httpx.MockTransport so nothing touches the network.
"""

from __future__ import annotations

import httpx

transport: httpx.BaseTransport | None = None
TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def client() -> httpx.Client:
    return httpx.Client(transport=transport, timeout=TIMEOUT)


class SourceError(Exception):
    """A failure talking to an outside service. `safe_message` is fit to show the user and to log."""

    def __init__(self, message: str, status: int = 502, code: str | None = None) -> None:
        super().__init__(message)
        self.safe_message = message
        self.status = status  # HTTP status the API should answer with
        self.code = code  # provider error code, e.g. Plaid's ITEM_LOGIN_REQUIRED


def json_or_empty(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
