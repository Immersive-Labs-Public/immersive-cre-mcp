from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from immersive_cre_mcp import cognito
from immersive_cre_mcp.cognito import G, K, N, _hash_hex, _pad_hex

POOL = "eu-west-1_uVrFeROlb"
CLIENT = "78qh9j1upcfe3iovosrnoqu3m8"
IDP = "https://cognito-idp.eu-west-1.amazonaws.com/"


class FakeCognito:
    """The server half of Cognito's SRP, from a password verifier: a wrong client-side
    derivation produces a signature that doesn't verify."""

    def __init__(self, password: str = "pw", user_id: str = "52c584e4-uuid", challenge: str | None = None) -> None:
        self.user_id = user_id
        self.salt = secrets.token_hex(16)
        inner = hashlib.sha256(f"{POOL.split('_')[1]}{user_id}:{password}".encode()).hexdigest()
        self.v = pow(G, _hash_hex(_pad_hex(self.salt) + inner), N)
        self.b = secrets.randbelow(N)
        self.big_b = (K * self.v + pow(G, self.b, N)) % N
        self.secret_block = base64.b64encode(secrets.token_bytes(64)).decode()
        self.challenge = challenge
        self.big_a = 0
        self.targets: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        target = request.headers["x-amz-target"].rsplit(".", 1)[-1]
        self.targets.append(target)
        body: dict[str, Any] = json.loads(request.content)
        assert body["ClientId"] == CLIENT
        if target == "InitiateAuth":
            assert body["AuthFlow"] == "USER_SRP_AUTH"
            if body["AuthParameters"]["USERNAME"] != "support@example.com":
                return httpx.Response(400, json={"__type": "UserNotFoundException", "message": "User does not exist."})
            self.big_a = int(body["AuthParameters"]["SRP_A"], 16)
            return httpx.Response(200, json={"ChallengeName": "PASSWORD_VERIFIER", "ChallengeParameters": {
                "SALT": self.salt, "SRP_B": format(self.big_b, "x"), "SECRET_BLOCK": self.secret_block,
                "USERNAME": self.user_id, "USER_ID_FOR_SRP": self.user_id,
            }})
        resp = body["ChallengeResponses"]
        assert resp["USERNAME"] == self.user_id and resp["PASSWORD_CLAIM_SECRET_BLOCK"] == self.secret_block
        u = _hash_hex(_pad_hex(self.big_a) + _pad_hex(self.big_b))
        s = pow(self.big_a * pow(self.v, u, N), self.b, N)
        prk = hmac.new(bytes.fromhex(_pad_hex(u)), bytes.fromhex(_pad_hex(s)), hashlib.sha256).digest()
        key = hmac.new(prk, b"Caldera Derived Key\x01", hashlib.sha256).digest()[:16]
        msg = (POOL.split("_")[1] + self.user_id).encode() + base64.b64decode(self.secret_block) + resp["TIMESTAMP"].encode()
        expected = base64.b64encode(hmac.new(key, msg, hashlib.sha256).digest()).decode()
        if resp["PASSWORD_CLAIM_SIGNATURE"] != expected:
            return httpx.Response(400, json={"__type": "NotAuthorizedException", "message": "Incorrect username or password."})
        if self.challenge:
            return httpx.Response(200, json={"ChallengeName": self.challenge, "Session": "s"})
        return httpx.Response(200, json={"AuthenticationResult": {"IdToken": "id-token", "AccessToken": "a"}})


async def sign_in(password: str = "pw", username: str = "support@example.com") -> str:
    async with httpx.AsyncClient() as http:
        return await cognito.sign_in(http, POOL, CLIENT, username, password)


@respx.mock
async def test_srp_sign_in_returns_id_token() -> None:
    server = FakeCognito()
    respx.post(IDP).mock(side_effect=server)
    assert await sign_in() == "id-token"
    assert server.targets == ["InitiateAuth", "RespondToAuthChallenge"]


@respx.mock
async def test_wrong_password_is_not_authorized() -> None:
    respx.post(IDP).mock(side_effect=FakeCognito())
    with pytest.raises(cognito.CognitoError, match="Incorrect username or password") as exc:
        await sign_in(password="wrong")
    assert exc.value.code == "NotAuthorizedException"


@respx.mock
async def test_unknown_user_reports_cognito_error() -> None:
    respx.post(IDP).mock(side_effect=FakeCognito())
    with pytest.raises(cognito.CognitoError, match="User does not exist"):
        await sign_in(username="nobody@example.com")


@respx.mock
async def test_mfa_challenge_is_reported() -> None:
    respx.post(IDP).mock(side_effect=FakeCognito(challenge="SOFTWARE_TOKEN_MFA"))
    with pytest.raises(cognito.CognitoError, match="SOFTWARE_TOKEN_MFA"):
        await sign_in()


def test_timestamp_has_unpadded_day_and_english_names() -> None:
    assert cognito._timestamp(datetime(2026, 10, 5, 9, 3, 7, tzinfo=UTC)) == "Mon Oct 5 09:03:07 UTC 2026"
    assert cognito._timestamp(datetime(2026, 10, 26, 13, 5, 9, tzinfo=UTC)) == "Mon Oct 26 13:05:09 UTC 2026"


@pytest.mark.parametrize(("value", "padded"), [(0xF, "0f"), (0x7F, "7f"), (0x80, "0080"), ("abc", "0abc"), ("ff", "00ff")])
def test_pad_hex(value: int | str, padded: str) -> None:
    assert _pad_hex(value) == padded
