"""Async transport for the Immersive Labs Cyber Ranges (CRE) API.

This is the public API the CRE web dashboard calls (any registered account can
use it), but it isn't formally documented or versioned - see docs/API.md. The dashboard's
own API layer is two helpers, `GET /ranges/<path>` and `POST /ranges/<path>`
with a JSON body; this client mirrors that, plus auth and S3 uploads.

Auth: no API tokens. We walk the Immersive Labs platform login through the
ORY Hydra OAuth flow, which ends with a `token` cookie on the CRE API host.
Every host is regional (EU/US) - see config.REGIONS:

  1. POST  <IL API>/v1/immersive_auth/sessions   (email+password)
  2. GET   <hydra>/oauth2/auth?...  (the ranges API's 401 `authorizationUrl`)
                                     -> /signin?login_challenge=<X>
  3. POST  IL graphql OIDCAcceptLogin(X)    -> redirectTo (hydra ?login_verifier=)
  4. GET   redirectTo                        -> /oidc/consent?consent_challenge=<Y>
  5. POST  IL graphql OIDCAcceptConsent(Y)  -> redirectTo (hydra ?consent_verifier=)
  6. GET   redirectTo -> CRE authorizationChallengeCallback?code=... (sets `token`)

The token is cached (memory + optional file) and re-minted on 401/403.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from mcp.server.mcpserver.exceptions import ToolError

from .config import Settings
from .config import settings as default_settings

log = logging.getLogger("immersive_cre_mcp.client")

GRAPHQL_API_VERSION = "2026-04-27"
# The IL edge/WAF bounces unrecognised UAs to a bot page that breaks the OAuth chain.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)


class CreError(ToolError):
    """A ranges-API failure. Subclasses ToolError so MCP relays the message to the model."""


class CreClient:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings
        self.base = settings.immersive_cre_base_url.rstrip("/")
        self.dashboard = settings.immersive_cre_dashboard_url.rstrip("/")
        self.il = settings.immersive_cre_il_url.rstrip("/")
        self.il_api = settings.immersive_cre_il_api_url.rstrip("/")
        self._token: str | None = None
        self._login_lock = asyncio.Lock()
        self._http = httpx.AsyncClient(
            base_url=f"{self.base}/ranges/",
            timeout=60.0,
            headers={
                "User-Agent": BROWSER_UA,
                "Accept": "application/json, text/plain, */*",
                "X-Referrer": f"{self.dashboard}/labs",
            },
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # API -------------------------------------------------------------------------
    async def get(self, path: str) -> dict[str, Any]:
        return await self.request("GET", path)

    async def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST /ranges/<path>. Drops None-valued keys (the dashboard sends `undefined`)."""
        return await self.request("POST", path, {k: v for k, v in (body or {}).items() if v is not None})

    async def request(
        self, method: str, path: str, body: dict[str, Any] | None = None, *, check: bool = True,
    ) -> dict[str, Any]:
        """One ranges-API call (path relative to /ranges/), with a single re-login on 401/403.
        With check=True, a `"result": "error"`-style body raises CreError."""
        if not self.settings.configured:
            raise CreError("CRE is not configured (set IMMERSIVE_CRE_USERNAME / IMMERSIVE_CRE_PASSWORD)")
        path = path.lstrip("/").removeprefix("ranges/")
        token = self._token or self._load_cached_token() or await self._login()
        resp = await self._send(method, path, body, token)
        if resp.status_code in (401, 403):
            log.info("cre %s on %s %s - re-logging in", resp.status_code, method, path)
            resp = await self._send(method, path, body, await self._login(stale=token))
        if resp.status_code >= 400:
            raise CreError(f"{method} /ranges/{path} -> {resp.status_code}: {resp.text[:500]}")
        try:
            data = resp.json()
        except ValueError:
            return {"text": resp.text}
        if not isinstance(data, dict):
            return {"data": data}
        if check and data.get("result") not in (None, "success"):
            raise CreError(f"/ranges/{path}: {str(data.get('message') or data)[:500]}")
        return data

    async def _send(self, method: str, path: str, body: dict[str, Any] | None, token: str) -> httpx.Response:
        return await self._http.request(
            method, path, json=body if method.upper() != "GET" else None, headers={"Cookie": f"token={token}"},
        )

    # S3 helpers ----------------------------------------------------------------------
    async def fetch_url(self, url: str) -> bytes:
        """Fetch a pre-signed S3 URL (markdown, documents). They expire quickly - call straight away."""
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
            r = await http.get(url)
            if r.status_code >= 400:
                raise CreError(f"download failed: {r.status_code} {r.text[:200]}")
            return r.content

    async def upload_presigned_post(self, url_data: dict[str, Any], filename: str, content: bytes) -> None:
        """Upload to a pre-signed S3 POST ({url, fields}) as returned by docs/update."""
        async with httpx.AsyncClient(timeout=300.0) as http:
            r = await http.post(
                url_data["url"], data=dict(url_data.get("fields") or {}), files={"file": (filename, content)},
            )
            if r.status_code >= 400:
                raise CreError(f"S3 upload failed: {r.status_code} {r.text[:300]}")

    # auth ------------------------------------------------------------------------------
    async def _login(self, stale: str | None = None) -> str:
        async with self._login_lock:
            # Another task may have refreshed the token while we waited.
            if self._token and self._token != stale:
                return self._token
            token = await self._oauth_login()
            self._token = token
            self._save_cached_token(token)
            log.info("cre login OK")
            return token

    async def _oauth_login(self) -> str:
        """Walk IL sign-in -> hydra -> CRE callback; return the token cookie."""
        s = self.settings
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True,
            headers={"User-Agent": BROWSER_UA, "Accept": "application/json, text/plain, */*"},
        ) as http:
            r = await http.post(
                f"{self.il_api}/v1/immersive_auth/sessions",
                json={"account": {"email": s.immersive_cre_username, "password": s.immersive_cre_password}},
                headers={"Origin": self.il, "Referer": f"{self.il}/signin"},
            )
            if r.status_code >= 400:
                raise CreError(f"IL sign-in failed ({self.il_api}): {r.status_code} {r.text[:200]}")

            r = await http.get(await self._authorization_url(http), headers={"Referer": f"{self.dashboard}/"})
            login_challenge = _query_param(r, "login_challenge")
            redirect = await self._accept_challenge(http, "OIDCAcceptLogin", "oidcAcceptLoginRequest", "loginChallenge", login_challenge)
            r = await http.get(redirect, headers={"Referer": f"{self.il}/"})
            consent_challenge = _query_param(r, "consent_challenge")
            redirect = await self._accept_challenge(http, "OIDCAcceptConsent", "oidcAcceptConsentRequest", "consentChallenge", consent_challenge)
            r = await http.get(redirect, headers={"Referer": f"{self.il}/"})
            token = http.cookies.get("token")
            if not token:
                raise CreError(f"OAuth chain finished without a CRE token (landed on {r.url})")
            return token

    async def _authorization_url(self, http: httpx.AsyncClient) -> str:
        """The Hydra URL that starts the OAuth flow. Like the dashboard, take it from the
        ranges API's 401 (it knows its own client id and callback); else build it."""
        r = await http.get(
            f"{self.base}/ranges/staticuserinfo",
            headers={"X-Referrer": f"{self.dashboard}/labs"}, follow_redirects=False,
        )
        try:
            url = (r.json() or {}).get("authorizationUrl") if r.status_code == 401 else None
        except ValueError:
            url = None
        if url:
            return url
        s = self.settings
        if not s.immersive_cre_hydra_client_id:
            raise CreError(
                f"{self.base} didn't return an authorizationUrl ({r.status_code}) and no "
                "IMMERSIVE_CRE_HYDRA_CLIENT_ID is set for this region"
            )
        callback = f"{self.base}/ranges/authorizationChallengeCallback"
        return (
            f"{s.immersive_cre_hydra_url.rstrip('/')}/oauth2/auth?client_id={s.immersive_cre_hydra_client_id}"
            f"&scope=offline_access%20openid&response_type=code&redirect_uri={callback}"
            f"&state={self.dashboard}/labs&max_age=43200"
        )

    async def _accept_challenge(self, http: httpx.AsyncClient, op: str, field_name: str, arg: str, challenge: str) -> str:
        query = f"mutation {op}($challenge: String!) {{ {field_name}({arg}: $challenge) {{ redirectTo }} }}"
        r = await http.post(
            f"{self.il_api}/v1/graphql?r={op}&api_version={GRAPHQL_API_VERSION}",
            json={"operationName": op, "variables": {"challenge": challenge}, "query": query},
            headers={"Origin": self.il, "Referer": f"{self.il}/"},
        )
        if r.status_code >= 400:
            raise CreError(f"{op} -> {r.status_code} {r.text[:200]}")
        redirect = ((r.json().get("data") or {}).get(field_name) or {}).get("redirectTo")
        if not redirect:
            raise CreError(f"{op} response missing redirectTo: {r.text[:200]}")
        return redirect

    def _cache_path(self) -> Path | None:
        return self.settings.token_cache_path

    def _load_cached_token(self) -> str | None:
        path = self._cache_path()
        if not path or not path.exists():
            return None
        try:
            self._token = path.read_text().strip() or None
        except OSError:
            return None
        return self._token

    def _save_cached_token(self, token: str) -> None:
        path = self._cache_path()
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(token)
        except OSError as exc:
            log.warning("could not cache token at %s: %s", path, exc)


def _query_param(resp: httpx.Response, name: str) -> str:
    value = parse_qs(urlparse(str(resp.url)).query).get(name, [""])[0]
    if not value:
        raise CreError(f"hydra didn't return a {name}; landed on {resp.url}")
    return value

