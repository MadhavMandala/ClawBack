"""Settings, read from environment variables. Copy .env.example to .env and fill it in."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def load_env_file(path: Path) -> None:
    """Load KEY=value lines from a .env file. Variables already set in the shell win."""
    load_dotenv(path, override=False)


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    nebius_api_key: str | None = field(default_factory=lambda: _env("NEBIUS_API_KEY"))
    nebius_base_url: str = field(
        default_factory=lambda: _env("NEBIUS_BASE_URL") or "https://api.tokenfactory.nebius.com/v1/"
    )
    tavily_api_key: str | None = field(default_factory=lambda: _env("TAVILY_API_KEY"))

    # MISSING: none of these are used yet. See clawback/sources/gmail.py and plaid.py.
    google_client_id: str | None = field(default_factory=lambda: _env("GOOGLE_CLIENT_ID"))
    google_client_secret: str | None = field(default_factory=lambda: _env("GOOGLE_CLIENT_SECRET"))
    google_pubsub_topic: str | None = field(default_factory=lambda: _env("GOOGLE_PUBSUB_TOPIC"))
    plaid_client_id: str | None = field(default_factory=lambda: _env("PLAID_CLIENT_ID"))
    plaid_secret: str | None = field(default_factory=lambda: _env("PLAID_SECRET"))
    supabase_url: str | None = field(default_factory=lambda: _env("SUPABASE_URL"))
    supabase_service_key: str | None = field(default_factory=lambda: _env("SUPABASE_SERVICE_KEY"))

    frontend_origin: str = field(default_factory=lambda: _env("FRONTEND_ORIGIN") or "http://localhost:3000")
    autoseed_demo: bool = field(default_factory=lambda: (_env("CLAWBACK_AUTOSEED") or "1") == "1")

    def integrations(self) -> dict[str, bool]:
        """Which outside services have credentials. False means that path is MISSING at runtime."""
        return {
            "nebius_token_factory": bool(self.nebius_api_key),
            "tavily": bool(self.tavily_api_key),
            "gmail": False,  # MISSING: OAuth + Pub/Sub not built, even if keys are set
            "plaid": False,  # MISSING: Plaid Link + sync not built, even if keys are set
            "supabase": False,  # MISSING: still using the in-memory store
        }


load_env_file(Path(__file__).resolve().parents[1] / ".env")
settings = Settings()
