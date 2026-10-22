"""Plaid (bank and card transactions). NOTHING HERE IS BUILT YET. Every function raises Missing.

Plan:
  - Plaid Link in the frontend -> public_token -> /item/public_token/exchange -> access_token (store encrypted).
  - /transactions/sync cursor loop while has_more; re-run on the SYNC_UPDATES_AVAILABLE webhook.
  - Use our own recurring detection (pipeline/recurring.py). Plaid's /transactions/recurring/get is a paid add-on.
  - Start in Sandbox (test user "user_transactions_dynamic"), then the free Trial plan (10 real bank accounts).
"""

from __future__ import annotations

from ..missing import missing


def create_link_token(user_id: str) -> str:
    missing("plaid-link")


def exchange_public_token(user_id: str, public_token: str) -> None:
    missing("plaid-link")


def sync_transactions(user_id: str) -> list:
    missing("plaid-sync")


def handle_webhook(payload: dict) -> None:
    missing("plaid-sync")
