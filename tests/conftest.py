"""Shared fixtures.

Settings are read at import time from the environment and the project `.env`, which may hold
real credentials. Environment variables win over `.env`, so pin every setting here before the
package is imported: tests never see real credentials or touch the user's token cache.
"""
from __future__ import annotations

import os

_TEST_ENV = {
    "IMMERSIVE_CRE_REGION": "eu",
    "IMMERSIVE_CRE_BASE_URL": "",
    "IMMERSIVE_CRE_DASHBOARD_URL": "",
    "IMMERSIVE_CRE_IL_URL": "",
    "IMMERSIVE_CRE_IL_API_URL": "",
    "IMMERSIVE_CRE_HYDRA_URL": "",
    "IMMERSIVE_CRE_HYDRA_CLIENT_ID": "",
    "IMMERSIVE_CRE_COGNITO_API_URL": "",
    "IMMERSIVE_CRE_COGNITO_USER_POOL_ID": "",
    "IMMERSIVE_CRE_COGNITO_CLIENT_ID": "",
    "IMMERSIVE_CRE_AUTH": "auto",
    "IMMERSIVE_CRE_USERNAME": "tester@example.com",
    "IMMERSIVE_CRE_PASSWORD": "not-a-real-password",
    "IMMERSIVE_CRE_TOKEN_CACHE": "",
    "IMMERSIVE_CRE_READ_ONLY": "false",
    "IMMERSIVE_CRE_ENABLE_RAW": "true",
}
os.environ.update(_TEST_ENV)

from collections.abc import Callable  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402

Response = Any | Callable[[dict[str, Any] | None], Any]


class FakeClient:
    """Stands in for CreClient in tool tests. `responses` maps an API path to a value, a callable
    taking the request body, or a list of either (consumed in order). Every call is recorded."""

    def __init__(self, responses: dict[str, Response | list[Response]] | None = None) -> None:
        self.responses: dict[str, Any] = dict(responses or {})
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.uploads: list[tuple[dict[str, Any], str, bytes]] = []
        self.urls: dict[str, bytes] = {}

    def _respond(self, path: str, body: dict[str, Any] | None) -> Any:
        if path not in self.responses:
            return {"result": "success"}
        r = self.responses[path]
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        return r(body) if callable(r) else r

    async def get(self, path: str) -> Any:
        self.calls.append(("GET", path, None))
        return self._respond(path, None)

    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        body = {k: v for k, v in (body or {}).items() if v is not None}
        self.calls.append(("POST", path, body))
        return self._respond(path, body)

    async def request(self, method: str, path: str, body: dict[str, Any] | None = None, *, check: bool = True) -> Any:
        self.calls.append((method, path, body))
        return self._respond(path, body)

    async def fetch_url(self, url: str) -> bytes:
        return self.urls[url]

    async def upload_presigned_post(self, url_data: dict[str, Any], filename: str, content: bytes) -> None:
        self.uploads.append((url_data, filename, content))

    def bodies(self, path: str) -> list[dict[str, Any] | None]:
        return [b for _, p, b in self.calls if p == path]


@pytest.fixture
def fake() -> FakeClient:
    return FakeClient()


@pytest.fixture
def ctx(fake: FakeClient) -> Any:
    """Minimal stand-in for an MCP Context whose lifespan context is the fake client."""
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=fake))
