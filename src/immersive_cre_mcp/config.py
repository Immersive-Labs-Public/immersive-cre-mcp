"""Settings, read from the environment (and `.env` in the working directory)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project-root .env (for editable installs launched from any cwd), then ./.env.
_PROJECT_ENV = Path(__file__).resolve().parents[2] / ".env"

# Per-region hosts. CRE (ranges API + dashboard) and the Immersive Labs platform that
# signs you in (IL web app, its API, and the ORY Hydra OAuth server) are both regional.
REGIONS: dict[str, dict[str, str]] = {
    "eu": {
        "base_url": "https://api4.eu.snaplabs.io",
        "dashboard_url": "https://dashboard.immersivelabs.eu.snaplabs.io",
        "il_url": "https://immersivelabs.online",
        "il_api_url": "https://api.immersivelabs.online",
        "hydra_url": "https://hydra.immersivelabs.online",
        # Hydra OAuth client the CRE dashboard uses; only a fallback, since the
        # ranges API hands us the full authorization URL on an unauthenticated call.
        "hydra_client_id": "8e5ca831-793c-4405-9228-f2a19e3182a8",
    },
    "us": {
        "base_url": "https://api4.snaplabs.io",
        "dashboard_url": "https://dashboard.immersivelabs.snaplabs.io",
        "il_url": "https://us.immersivelabs.com",
        "il_api_url": "https://api.us.immersivelabs.com",
        "hydra_url": "https://hydra.us.immersivelabs.com",
        "hydra_client_id": "26ef12e7-ae8e-42dc-9e0d-3b24cd5ab2dc",
    },
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(_PROJECT_ENV, ".env"), extra="ignore")

    # Picks the defaults below; any URL set explicitly wins over the region's.
    immersive_cre_region: Literal["eu", "us"] = "eu"
    immersive_cre_base_url: str = ""
    immersive_cre_dashboard_url: str = ""
    immersive_cre_il_url: str = ""
    immersive_cre_il_api_url: str = ""
    immersive_cre_hydra_url: str = ""
    immersive_cre_hydra_client_id: str = ""
    immersive_cre_username: str = ""
    immersive_cre_password: str = ""

    # Where the CRE `token` cookie is cached between server restarts.
    # Empty string disables the on-disk cache (token kept in memory only).
    immersive_cre_token_cache: str = str(Path.home() / ".cache" / "immersive-cre-mcp" / "token")
    # Only register read-only tools (no launches, edits or deletes).
    immersive_cre_read_only: bool = False
    # Expose `raw_request`, a passthrough to any ranges-API path (see docs/API.md).
    immersive_cre_enable_raw: bool = True

    @model_validator(mode="after")
    def _apply_region(self) -> Settings:
        for key, value in REGIONS[self.immersive_cre_region].items():
            field = f"immersive_cre_{key}"
            if not getattr(self, field):
                setattr(self, field, value)
        return self

    @property
    def configured(self) -> bool:
        return bool(self.immersive_cre_username and self.immersive_cre_password)

    @property
    def token_cache_path(self) -> Path | None:
        """Token cache file; non-EU regions get their own so switching never reuses a foreign cookie."""
        if not self.immersive_cre_token_cache:
            return None
        path = Path(self.immersive_cre_token_cache).expanduser()
        return path if self.immersive_cre_region == "eu" else path.with_name(f"{path.name}-{self.immersive_cre_region}")


settings = Settings()
