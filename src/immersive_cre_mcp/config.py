"""Settings, read from the environment (and `.env` in the working directory)."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project-root .env (for editable installs launched from any cwd), then ./.env.
_PROJECT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(_PROJECT_ENV, ".env"), extra="ignore")

    immersive_cre_base_url: str = "https://api4.eu.snaplabs.io"
    immersive_cre_dashboard_url: str = "https://dashboard.immersivelabs.eu.snaplabs.io"
    immersive_cre_username: str = ""
    immersive_cre_password: str = ""

    # Where the CRE `token` cookie is cached between server restarts.
    # Empty string disables the on-disk cache (token kept in memory only).
    immersive_cre_token_cache: str = str(Path.home() / ".cache" / "immersive-cre-mcp" / "token")
    # Only register read-only tools (no launches, edits or deletes).
    immersive_cre_read_only: bool = False
    # Expose `raw_request`, a passthrough to any ranges-API path (see docs/API.md).
    immersive_cre_enable_raw: bool = True

    @property
    def configured(self) -> bool:
        return bool(self.immersive_cre_username and self.immersive_cre_password)


settings = Settings()
