"""AWS Cognito sign-in for standalone CRE accounts (not Immersive Labs platform users).

The standalone dashboard signs in with amazon-cognito-identity-js, which uses SRP: the password
never leaves the client, only a proof of it. This mirrors that flow over plain HTTP:

  1. InitiateAuth USER_SRP_AUTH (SRP_A)           -> PASSWORD_VERIFIER (SALT, SRP_B, SECRET_BLOCK)
  2. RespondToAuthChallenge (PASSWORD_CLAIM_*)    -> AuthenticationResult.IdToken

The ID token goes, as is, in the `Authorization` header of every /main API call.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Any

import httpx

# RFC 5054 3072-bit group, as used by Cognito.
N = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AAAC42DAD33170D04507A33A85521ABDF1CBA64ECFB850458DBEF0A8AEA71575D060C7DB3970F85A6E1E4C7"
    "ABF5AE8CDB0933D71E8C94E04A25619DCEE3D2261AD2EE6BF12FFA06D98A0864D87602733EC86A64521F2B18177B200C"
    "BBE117577A615D6C770988C0BAD946E208E24FA074E5AB3143DB5BFCE0FD108E4B82D120A93AD2CAFFFFFFFFFFFFFFFF",
    16,
)
G = 2
_INFO = b"Caldera Derived Key\x01"
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class CognitoError(Exception):
    """Sign-in failed. `code` is Cognito's error type (e.g. NotAuthorizedException) or challenge name."""

    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code


def _pad_hex(value: int | str) -> str:
    """Hex as Cognito hashes it: even length, with a leading 00 if the top bit is set."""
    h = value if isinstance(value, str) else format(value, "x")
    if len(h) % 2:
        return "0" + h
    return "00" + h if h[0] in "89abcdefABCDEF" else h


def _hash_hex(hex_str: str) -> int:
    return int(hashlib.sha256(bytes.fromhex(hex_str)).hexdigest(), 16)


K = _hash_hex(_pad_hex(N) + _pad_hex(G))


def _timestamp(now: datetime | None = None) -> str:
    """e.g. "Mon Oct 6 13:05:09 UTC 2026" (no zero-padded day), built without the locale."""
    t = now or datetime.now(UTC)
    return f"{_DAYS[t.weekday()]} {_MONTHS[t.month - 1]} {t.day} {t:%H:%M:%S} UTC {t.year}"


def password_key(pool_id: str, user_id: str, password: str, a: int, big_a: int, big_b: int, salt: str) -> bytes:
    """The 16-byte HKDF key both sides derive from the SRP shared secret."""
    u = _hash_hex(_pad_hex(big_a) + _pad_hex(big_b))
    if u == 0:
        raise CognitoError("SRP: u is zero")
    inner = hashlib.sha256(f"{pool_id.split('_', 1)[1]}{user_id}:{password}".encode()).hexdigest()
    x = _hash_hex(_pad_hex(salt) + inner)
    s = pow(big_b - K * pow(G, x, N), a + u * x, N)
    prk = hmac.new(bytes.fromhex(_pad_hex(u)), bytes.fromhex(_pad_hex(s)), hashlib.sha256).digest()
    return hmac.new(prk, _INFO, hashlib.sha256).digest()[:16]


async def _call(http: httpx.AsyncClient, url: str, target: str, body: dict[str, Any]) -> dict[str, Any]:
    r = await http.post(url, json=body, headers={
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": f"AWSCognitoIdentityProviderService.{target}",
    })
    try:
        data: dict[str, Any] = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400:
        code = str(data.get("__type", "")).rsplit("#", 1)[-1]
        raise CognitoError(f"{target}: {data.get('message') or r.text[:200]} ({code or r.status_code})", code)
    return data


async def sign_in(http: httpx.AsyncClient, pool_id: str, client_id: str, username: str, password: str) -> str:
    """SRP sign-in; returns the Cognito ID token."""
    url = f"https://cognito-idp.{pool_id.split('_', 1)[0]}.amazonaws.com/"
    a = secrets.randbelow(N - 1) + 1
    big_a = pow(G, a, N)
    resp = await _call(http, url, "InitiateAuth", {
        "AuthFlow": "USER_SRP_AUTH", "ClientId": client_id,
        "AuthParameters": {"USERNAME": username, "SRP_A": format(big_a, "x")},
    })
    if resp.get("ChallengeName") != "PASSWORD_VERIFIER":
        raise CognitoError(f"unexpected Cognito challenge {resp.get('ChallengeName')!r}", str(resp.get("ChallengeName")))
    params = resp["ChallengeParameters"]
    user_id = params["USER_ID_FOR_SRP"]
    big_b = int(params["SRP_B"], 16)
    if big_b % N == 0:
        raise CognitoError("SRP: invalid server B")
    key = password_key(pool_id, user_id, password, a, big_a, big_b, params["SALT"])
    timestamp = _timestamp()
    msg = pool_id.split("_", 1)[1].encode() + user_id.encode() + base64.b64decode(params["SECRET_BLOCK"]) + timestamp.encode()
    resp = await _call(http, url, "RespondToAuthChallenge", {
        "ChallengeName": "PASSWORD_VERIFIER", "ClientId": client_id,
        "ChallengeResponses": {
            "USERNAME": user_id,
            "PASSWORD_CLAIM_SECRET_BLOCK": params["SECRET_BLOCK"],
            "TIMESTAMP": timestamp,
            "PASSWORD_CLAIM_SIGNATURE": base64.b64encode(hmac.new(key, msg, hashlib.sha256).digest()).decode(),
        },
    })
    token = (resp.get("AuthenticationResult") or {}).get("IdToken")
    if not token:
        # MFA or a forced password change: finish those once in the CRE dashboard.
        challenge = resp.get("ChallengeName") or "no token"
        raise CognitoError(f"Cognito wants {challenge}; complete it in the CRE dashboard first", str(challenge))
    return str(token)
