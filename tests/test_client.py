from __future__ import annotations

import json
import stat
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx

from immersive_cre_mcp.client import CreClient, CreError
from immersive_cre_mcp.config import Settings

API = "https://api4.eu.snaplabs.io/ranges"
IL = "https://immersivelabs.online"
IL_API = "https://api.immersivelabs.online"
HYDRA = "https://hydra.immersivelabs.online"


def make_settings(**kw: object) -> Settings:
    base: dict[str, object] = {
        "immersive_cre_username": "user@example.com",
        "immersive_cre_password": "pw",
        "immersive_cre_token_cache": "",
    }
    return Settings(_env_file=None, **{**base, **kw})  # type: ignore[call-arg]


@pytest.fixture
async def cre() -> AsyncIterator[CreClient]:
    c = CreClient(make_settings())
    c._token = "tok"
    yield c
    await c.aclose()


# ── transport ────────────────────────────────────────────────────────────────
@respx.mock
async def test_get_sends_token_cookie_and_headers(cre: CreClient) -> None:
    route = respx.get(f"{API}/labs").respond(json={"result": "success", "labs": []})
    assert await cre.get("labs") == {"result": "success", "labs": []}
    req = route.calls.last.request
    assert "token=tok" in req.headers["cookie"]
    assert req.headers["x-referrer"].endswith("/labs")
    assert "Mozilla" in req.headers["user-agent"]


@respx.mock
@pytest.mark.parametrize("path", ["labs", "/labs", "ranges/labs", "/ranges/labs"])
async def test_path_normalised(cre: CreClient, path: str) -> None:
    route = respx.get(f"{API}/labs").respond(json={})
    await cre.get(path)
    assert route.called


@respx.mock
async def test_post_drops_none_values(cre: CreClient) -> None:
    route = respx.post(f"{API}/scenarios/create").respond(json={"result": "success"})
    await cre.post("scenarios/create", {"Name": "x", "Description": None, "Flag": False})
    assert json.loads(route.calls.last.request.content) == {"Name": "x", "Flag": False}


@respx.mock
async def test_error_result_raises(cre: CreClient) -> None:
    respx.post(f"{API}/scenarios/delete").respond(json={"result": "error", "message": "nope"})
    with pytest.raises(CreError, match="nope"):
        await cre.post("scenarios/delete", {})


@respx.mock
async def test_error_result_returned_when_unchecked(cre: CreClient) -> None:
    respx.post(f"{API}/x").respond(json={"result": "error", "message": "nope"})
    assert await cre.request("POST", "x", {}, check=False) == {"result": "error", "message": "nope"}


@respx.mock
async def test_http_error_raises_with_status(cre: CreClient) -> None:
    respx.get(f"{API}/labs").respond(500, text="boom")
    with pytest.raises(CreError, match=r"GET /ranges/labs -> 500: boom"):
        await cre.get("labs")


@respx.mock
async def test_non_json_and_non_dict_bodies_are_wrapped(cre: CreClient) -> None:
    respx.get(f"{API}/text").respond(text="hello")
    respx.get(f"{API}/list").respond(json=[1, 2])
    assert await cre.get("text") == {"text": "hello"}
    assert await cre.get("list") == {"data": [1, 2]}


async def test_unconfigured_client_refuses() -> None:
    c = CreClient(make_settings(immersive_cre_username="", immersive_cre_password=""))
    try:
        with pytest.raises(CreError, match="not configured"):
            await c.get("labs")
    finally:
        await c.aclose()


@respx.mock
async def test_relogin_on_401(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "token"
    c = CreClient(make_settings(immersive_cre_token_cache=str(cache)))
    c._token = "stale"

    async def fake_oauth() -> str:
        return "fresh"

    monkeypatch.setattr(c, "_oauth_login", fake_oauth)
    route = respx.get(f"{API}/labs").mock(side_effect=[
        httpx.Response(401, json={}), httpx.Response(200, json={"labs": []}),
    ])
    try:
        assert await c.get("labs") == {"labs": []}
    finally:
        await c.aclose()
    assert "token=fresh" in route.calls.last.request.headers["cookie"]
    assert c._token == "fresh"
    assert cache.read_text() == "fresh"
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600


@respx.mock
async def test_uses_cached_token_from_disk(tmp_path: Path) -> None:
    cache = tmp_path / "token"
    cache.write_text("from-disk\n")
    c = CreClient(make_settings(immersive_cre_token_cache=str(cache)))
    route = respx.get(f"{API}/labs").respond(json={})
    try:
        await c.get("labs")
    finally:
        await c.aclose()
    assert "token=from-disk" in route.calls.last.request.headers["cookie"]


# ── OAuth login chain ────────────────────────────────────────────────────────
def mock_oauth_chain(token: str = "minted") -> dict[str, respx.Route]:
    def hydra(request: httpx.Request) -> httpx.Response:
        q = request.url.params
        if "login_verifier" in q:
            return httpx.Response(302, headers={"Location": f"{IL}/oidc/consent?consent_challenge=CC"})
        if "consent_verifier" in q:
            return httpx.Response(302, headers={"Location": f"{API}/authorizationChallengeCallback?code=abc"})
        return httpx.Response(302, headers={"Location": f"{IL}/signin?login_challenge=LC"})

    def graphql(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["operationName"] == "OIDCAcceptLogin":
            assert body["variables"] == {"challenge": "LC"}
            return httpx.Response(200, json={"data": {"oidcAcceptLoginRequest": {
                "redirectTo": f"{HYDRA}/oauth2/auth?login_verifier=V"}}})
        assert body["variables"] == {"challenge": "CC"}
        return httpx.Response(200, json={"data": {"oidcAcceptConsentRequest": {
            "redirectTo": f"{HYDRA}/oauth2/auth?consent_verifier=W"}}})

    def staticuserinfo(request: httpx.Request) -> httpx.Response:
        if f"token={token}" in request.headers.get("cookie", ""):
            return httpx.Response(200, json={"result": "success", "User": "me"})
        return httpx.Response(401, json={"authorizationUrl": f"{HYDRA}/oauth2/auth?client_id=cid"})

    return {
        "session": respx.post(f"{IL_API}/v1/immersive_auth/sessions").respond(json={}),
        "staticuserinfo": respx.get(f"{API}/staticuserinfo").mock(side_effect=staticuserinfo),
        "hydra": respx.get(url__startswith=f"{HYDRA}/oauth2/auth").mock(side_effect=hydra),
        "signin": respx.get(url__startswith=f"{IL}/signin").respond(200),
        "consent": respx.get(url__startswith=f"{IL}/oidc/consent").respond(200),
        "graphql": respx.post(url__startswith=f"{IL_API}/v1/graphql").mock(side_effect=graphql),
        "callback": respx.get(url__startswith=f"{API}/authorizationChallengeCallback").respond(
            200, headers={"Set-Cookie": f"token={token}; Path=/"}),
    }


@respx.mock
async def test_full_login_chain_mints_token() -> None:
    routes = mock_oauth_chain()
    c = CreClient(make_settings())
    try:
        assert await c.get("staticuserinfo") == {"result": "success", "User": "me"}
    finally:
        await c.aclose()
    assert c._token == "minted"
    creds = json.loads(routes["session"].calls.last.request.content)
    assert creds == {"account": {"email": "user@example.com", "password": "pw"}}
    assert routes["graphql"].call_count == 2
    assert routes["callback"].called


@respx.mock
async def test_login_failure_surfaces_status() -> None:
    respx.post(f"{IL_API}/v1/immersive_auth/sessions").respond(401, text="bad creds")
    c = CreClient(make_settings())
    try:
        with pytest.raises(CreError, match=r"IL sign-in failed.*401"):
            await c.get("labs")
    finally:
        await c.aclose()


@respx.mock
async def test_login_chain_without_token_cookie_fails() -> None:
    routes = mock_oauth_chain()
    routes["callback"].respond(200)
    c = CreClient(make_settings())
    try:
        with pytest.raises(CreError, match="without a CRE token"):
            await c.get("labs")
    finally:
        await c.aclose()


@respx.mock
async def test_authorization_url_falls_back_to_region_client_id(cre: CreClient) -> None:
    respx.get(f"{API}/staticuserinfo").respond(200, json={})
    async with httpx.AsyncClient() as http:
        url = await cre._authorization_url(http)
    assert url.startswith(f"{HYDRA}/oauth2/auth?client_id=8e5ca831-")
    assert "redirect_uri=https://api4.eu.snaplabs.io/ranges/authorizationChallengeCallback" in url


@respx.mock
async def test_authorization_url_without_client_id_fails() -> None:
    c = CreClient(make_settings(immersive_cre_base_url="https://custom.test", immersive_cre_hydra_client_id=""))
    # An explicitly empty client id is refilled from the region; clear it after construction.
    c.settings.immersive_cre_hydra_client_id = ""
    respx.get("https://custom.test/ranges/staticuserinfo").respond(200, text="not json")
    try:
        async with httpx.AsyncClient() as http:
            with pytest.raises(CreError, match="IMMERSIVE_CRE_HYDRA_CLIENT_ID"):
                await c._authorization_url(http)
    finally:
        await c.aclose()


# ── S3 helpers ───────────────────────────────────────────────────────────────
@respx.mock
async def test_upload_presigned_post_sends_fields_and_file(cre: CreClient) -> None:
    route = respx.post("https://bucket.s3.test/").respond(204)
    await cre.upload_presigned_post({"url": "https://bucket.s3.test/", "fields": {"key": "k1"}}, "a.md", b"# hi")
    body = route.calls.last.request.content
    assert b'name="key"' in body and b"k1" in body
    assert b'filename="a.md"' in body and b"# hi" in body


@respx.mock
async def test_s3_failures_raise(cre: CreClient) -> None:
    respx.post("https://bucket.s3.test/").respond(403, text="denied")
    respx.get("https://bucket.s3.test/obj").respond(404, text="gone")
    with pytest.raises(CreError, match="S3 upload failed: 403"):
        await cre.upload_presigned_post({"url": "https://bucket.s3.test/"}, "a", b"")
    with pytest.raises(CreError, match="download failed: 404"):
        await cre.fetch_url("https://bucket.s3.test/obj")
