"""Settings, read from environment variables. Copy .env.example to .env and fill it in.

backend/.env is loaded on import. Variables already set in the environment win. CLAWBACK_DOTENV=0 skips the file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

PLAID_URLS = {"sandbox": "https://sandbox.plaid.com", "production": "https://production.plaid.com"}


def load_env_file(path: Path) -> None:
    """Load KEY=value lines from a .env file. Variables already set in the environment win, even empty ones
    (so `NEBIUS_API_KEY=` in the shell turns that key off). utf-8-sig: Notepad may save a byte-order mark."""
    load_dotenv(path, override=False, encoding="utf-8-sig")


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _int_env(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(_env(name) or default)
    except ValueError:
        return default


SESSION_MODES = ("visitor", "single")


@dataclass
class Settings:
    nebius_api_key: str | None = field(default_factory=lambda: _env("NEBIUS_API_KEY"))
    nebius_base_url: str = field(
        default_factory=lambda: _env("NEBIUS_BASE_URL") or "https://api.tokenfactory.nebius.com/v1/"
    )
    tavily_api_key: str | None = field(default_factory=lambda: _env("TAVILY_API_KEY"))

    # Email from any provider through Nylas v3 Hosted OAuth. See clawback/sources/nylas.py.
    nylas_client_id: str | None = field(default_factory=lambda: _env("NYLAS_CLIENT_ID"))
    nylas_api_key: str | None = field(default_factory=lambda: _env("NYLAS_API_KEY"))
    nylas_api_uri: str = field(
        default_factory=lambda: (_env("NYLAS_API_URI") or "https://api.us.nylas.com").rstrip("/")
    )
    email_redirect_uri: str = field(
        default_factory=lambda: _env("EMAIL_REDIRECT_URI") or "http://localhost:8000/api/connect/email/callback"
    )
    email_max_messages: int = field(default_factory=lambda: _int_env("EMAIL_MAX_MESSAGES", 150))

    # Plaid, bank and card transactions. See clawback/sources/plaid.py.
    plaid_client_id: str | None = field(default_factory=lambda: _env("PLAID_CLIENT_ID"))
    plaid_secret: str | None = field(default_factory=lambda: _env("PLAID_SECRET"))
    plaid_env: str = field(default_factory=lambda: (_env("PLAID_ENV") or "sandbox").lower())

    # Webhooks. NYLAS_WEBHOOK_SECRET is the webhook_secret Nylas returns when the webhook is created.
    # PUBLIC_API_URL (e.g. https://api.example.com) is this backend's public address; with it set, Plaid Link
    # tokens carry {PUBLIC_API_URL}/api/ingest/plaid/webhook so Plaid can call back.
    nylas_webhook_secret: str | None = field(default_factory=lambda: _env("NYLAS_WEBHOOK_SECRET"))
    public_api_url: str | None = field(default_factory=lambda: (_env("PUBLIC_API_URL") or "").rstrip("/") or None)

    # Storage: one SQLite file (see clawback/db.py and store.py). backend/.local/ is git-ignored.
    db_path: Path = field(
        default_factory=lambda: Path(_env("CLAWBACK_DB_PATH") or BACKEND_DIR / ".local" / "clawback.db")
    )
    # Encrypts saved tokens and each user's stored data (clawback/crypto.py). A Fernet key; without it, local dev
    # generates one into secret_key_path. Hosted deploys must set it, or a fresh disk loses every saved connection.
    secret_key: str | None = field(default_factory=lambda: _env("CLAWBACK_SECRET_KEY"))
    secret_key_path: Path = field(default_factory=lambda: BACKEND_DIR / ".local" / "secret.key")
    # The old plaintext connections file. Only read once, to move its connections into the database.
    connections_path: Path = field(
        default_factory=lambda: Path(_env("CLAWBACK_CONNECTIONS_FILE") or BACKEND_DIR / ".local" / "connections.json")
    )
    # Cancel pages found per merchant (public URLs and steps only, shared by every user). See pipeline/cancel_lookup.py.
    cancel_cache_path: Path = field(
        default_factory=lambda: Path(_env("CLAWBACK_CANCEL_CACHE") or BACKEND_DIR / ".local" / "cancel_pages.json")
    )

    # Sessions (clawback/sessions.py). "visitor": each browser gets its own demo session, sent as the
    # X-ClawBack-Session header (the hosted default). "single": everyone is the one local user "demo" (old behaviour).
    sessions: str = field(default_factory=lambda: (_env("CLAWBACK_SESSIONS") or "visitor").lower())
    session_idle_days: int = field(default_factory=lambda: _int_env("CLAWBACK_SESSION_IDLE_DAYS", 14))
    sessions_per_ip_hour: int = field(default_factory=lambda: _int_env("CLAWBACK_SESSIONS_PER_IP_HOUR", 20))
    # Daily model spend caps in USD (UTC days). 0 or less turns a cap off.
    session_daily_usd: float = field(default_factory=lambda: _float_env("CLAWBACK_SESSION_DAILY_USD", 0.25))
    global_daily_usd: float = field(default_factory=lambda: _float_env("CLAWBACK_GLOBAL_DAILY_USD", 5.0))

    # The frontend's address. A comma-separated list is allowed (all may call the API); the first one is where
    # the email sign-in returns to. FRONTEND_ORIGIN_REGEX also allows matching origins, e.g. Vercel previews:
    # https://clawback-[a-z0-9-]+\.vercel\.app
    frontend_origin: str = field(default_factory=lambda: _env("FRONTEND_ORIGIN") or "http://localhost:3000")
    frontend_origin_regex: str | None = field(default_factory=lambda: _env("FRONTEND_ORIGIN_REGEX"))
    autoseed_demo: bool = field(default_factory=lambda: (_env("CLAWBACK_AUTOSEED") or "1") == "1")
    # Gmail add-on, for filming: "Netflix=you@example.com;Best Buy=..." flags mail from those addresses as that
    # merchant, in place of its own domains (pipeline/email_flags.py).
    demo_senders: str = field(default_factory=lambda: _env("CLAWBACK_DEMO_SENDERS") or "")

    @property
    def single_user(self) -> bool:
        return self.sessions == "single"

    @property
    def frontend_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.frontend_origin.split(",") if o.strip()] or ["http://localhost:3000"]

    @property
    def return_origin(self) -> str:
        """Where the email sign-in sends the browser back to: the first FRONTEND_ORIGIN."""
        return self.frontend_origins[0]

    def email_configured(self) -> bool:
        return bool(self.nylas_client_id and self.nylas_api_key)

    def plaid_configured(self) -> bool:
        return bool(self.plaid_client_id and self.plaid_secret and self.plaid_env in PLAID_URLS)

    @property
    def plaid_base_url(self) -> str:
        return PLAID_URLS.get(self.plaid_env, PLAID_URLS["sandbox"])

    def integrations(self) -> dict[str, bool]:
        """Which outside services have credentials. False means that path is MISSING at runtime."""
        return {
            "nebius_token_factory": bool(self.nebius_api_key),
            "tavily": bool(self.tavily_api_key),
            "email": self.email_configured(),  # Nylas: read mail and save drafts (never send)
            "plaid": self.plaid_configured(),  # Link + /transactions/sync + liabilities
            "email_webhooks": bool(self.email_configured() and self.nylas_webhook_secret),
            "plaid_webhooks": bool(self.plaid_configured() and self.public_api_url),
            "database": True,  # SQLite, clawback/db.py
        }


if os.environ.get("CLAWBACK_DOTENV", "1") != "0":
    load_env_file(BACKEND_DIR / ".env")
settings = Settings()
