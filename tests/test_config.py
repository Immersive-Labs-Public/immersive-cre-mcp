from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from immersive_cre_mcp.config import REGIONS, Settings


def make(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


@pytest.mark.parametrize("region", ["eu", "us"])
def test_region_fills_every_url(region: str) -> None:
    s = make(immersive_cre_region=region)
    for key, value in REGIONS[region].items():
        assert getattr(s, f"immersive_cre_{key}") == value


def test_explicit_url_overrides_region_default() -> None:
    s = make(immersive_cre_region="us", immersive_cre_base_url="https://example.test")
    assert s.immersive_cre_base_url == "https://example.test"
    assert s.immersive_cre_dashboard_url == REGIONS["us"]["dashboard_url"]


def test_unknown_region_rejected() -> None:
    with pytest.raises(ValidationError):
        make(immersive_cre_region="apac")


def test_auth_mode_defaults_to_auto_and_is_validated() -> None:
    assert make().immersive_cre_auth == "auto"
    assert make(immersive_cre_auth="cognito").immersive_cre_auth == "cognito"
    with pytest.raises(ValidationError):
        make(immersive_cre_auth="sso")


def test_configured_needs_username_and_password() -> None:
    assert make(immersive_cre_username="a", immersive_cre_password="b").configured
    assert not make(immersive_cre_username="a", immersive_cre_password="").configured
    assert not make(immersive_cre_username="", immersive_cre_password="b").configured


def test_token_cache_disabled_by_empty_string() -> None:
    assert make(immersive_cre_token_cache="").token_cache_path is None


def test_token_cache_is_per_region(tmp_path: Path) -> None:
    base = tmp_path / "token"
    assert make(immersive_cre_token_cache=str(base)).token_cache_path == base
    assert make(immersive_cre_token_cache=str(base), immersive_cre_region="us").token_cache_path == tmp_path / "token-us"


def test_token_cache_expands_user() -> None:
    path = make(immersive_cre_token_cache="~/cre-token").token_cache_path
    assert path == Path.home() / "cre-token"
