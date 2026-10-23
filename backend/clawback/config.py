"""Settings, read from environment variables. Copy .env.example to .env and fill it in.

backend/.env is loaded on import. Variables already set in the environment win. CLAWBACK_DOTENV=0 skips the file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

PLAID_URLS = {"sandbox": "https://sandbox.plaid.com", "production": "https://production.plaid.com"}


def load_dotenv(path: Path) -> None:
    """Minimal .env reader: KEY=value lines and # comments. Never overrides a variable that is already set."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip().removeprefix("export ").strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        os.environ.setdefault(key, value)


if os.environ.get("CLAWBACK_DOTENV", "1") != "0":
    load_dotenv(BACKEND_DIR / ".env")


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _int_env(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


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

    # Saved connections (tokens, cursor, account names). Plaintext on this machine: MISSING [token-encryption].
    connections_path: Path = field(
        default_factory=lambda: Path(_env("CLAWBACK_CONNECTIONS_FILE") or BACKEND_DIR / ".local" / "connections.json")
    )

    # MISSING: not used by the code yet.
    supabase_url: str | None = field(default_factory=lambda: _env("SUPABASE_URL"))
    supabase_service_key: str | None = field(default_factory=lambda: _env("SUPABASE_SERVICE_KEY"))

    frontend_origin: str = field(default_factory=lambda: _env("FRONTEND_ORIGIN") or "http://localhost:3000")
    autoseed_demo: bool = field(default_factory=lambda: (_env("CLAWBACK_AUTOSEED") or "1") == "1")

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
            "email": self.email_configured(),  # Nylas, read-only; webhooks and drafts are still MISSING
            "plaid": self.plaid_configured(),  # Link + /transactions/sync; webhook still MISSING
            "supabase": False,  # MISSING: still using the in-memory store
        }


settings = Settings()
