"""Gmail. NOTHING HERE IS BUILT YET. Every function raises Missing.

Plan (details in docs/ARCHITECTURE.md):
  - OAuth with gmail.readonly (read) + gmail.compose (drafts). Both are restricted scopes: the app stays in
    Google "Testing" mode with at most 100 test users, and their tokens expire 7 days after consent.
  - Push: users.watch -> Pub/Sub topic (grant publish to gmail-api-push@system.gserviceaccount.com).
    Each push carries only {emailAddress, historyId}; call history.list from the last stored historyId.
    Renew the watch daily, and also poll history.list now and then because pushes can be lost.
  - Drafts: drafts.create with a raw RFC 2822 message. Never call messages.send.
  - Store extracted facts, not raw email bodies.
"""

from __future__ import annotations

from ..missing import missing


def oauth_start_url(user_id: str) -> str:
    missing("gmail-oauth")


def handle_oauth_callback(user_id: str, code: str) -> None:
    missing("gmail-oauth")


def start_watch(user_id: str) -> None:
    missing("gmail-push")


def handle_push(payload: dict) -> None:
    missing("gmail-push")


def fetch_new_messages(user_id: str, start_history_id: str) -> list:
    missing("gmail-push")


def create_draft(user_id: str, to: str, subject: str, body: str) -> str:
    missing("gmail-drafts")
