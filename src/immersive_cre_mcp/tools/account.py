"""Account, users and the raw API escape hatch."""
from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver import Context

from ..app import client, tool
from ..config import settings


@tool("read")
async def get_account(ctx: Context) -> dict[str, Any]:
    """Current user and account: profile, limits (LabLimit, CurrentLabCount, CertLimit, UserLimit),
    features, abilities and platform."""
    d = await client(ctx).get("staticuserinfo")
    return {k: v for k, v in d.items() if k != "result"}


@tool("read")
async def list_users(ctx: Context, search: str = "", hide_managers: bool = False) -> list[dict[str, Any]]:
    """Users in the account (optionally filtered by name/email)."""
    body: dict[str, Any] = {"hideManagers": hide_managers}
    if search:
        body["searchTerm"] = search
    return (await client(ctx).post("users", body)).get("users") or []


@tool("read")
async def get_user(ctx: Context, user_id: str) -> dict[str, Any]:
    """One user's roles and range access."""
    return await client(ctx).post("v2/users/getUser", {"userId": user_id})


@tool("write")
async def invite_users(
    ctx: Context,
    emails: list[str],
    as_creator: bool = False,
    as_manager: bool = False,
    lab_permissions: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Invite users by email. as_creator lets them launch/build ranges; as_manager makes them
    account managers (managers get all labs, so lab_permissions is ignored). lab_permissions:
    [{"vpcId": "vpc-...", "permission": "view"|"edit"|"limited"}]. Existing users are skipped
    (see skippedUsers)."""
    return await client(ctx).post("users", {
        "emails": emails, "asCreators": as_creator, "asManagers": as_manager,
        "permissions": [] if as_manager else (lab_permissions or []),
    })


@tool("write")
async def update_user(
    ctx: Context,
    user_id: str,
    name: str | None = None,
    as_creator: bool | None = None,
    as_manager: bool | None = None,
    ranges: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Change a user's name, creator/manager roles, or range access (ranges: [{"vpcId", "permission"}]).
    Unspecified fields are omitted from the request; check with get_user afterwards."""
    return await client(ctx).post("v2/users/update", {
        "userId": user_id, "name": name, "asCreator": as_creator, "asManager": as_manager, "ranges": ranges,
    })


@tool("destructive")
async def remove_users(ctx: Context, user_ids: list[str]) -> dict[str, Any]:
    """Remove users from the account."""
    return await client(ctx).post("users", {"delete": True, "userIds": user_ids})


@tool("write")
async def reinvite_user(ctx: Context, user_id: str) -> dict[str, Any]:
    """Resend a user's invitation email."""
    return await client(ctx).post("users/reinvite", {"UserId": user_id})


async def raw_request(
    ctx: Context, path: str, method: Literal["GET", "POST"] = "POST", body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call any ranges-API endpoint directly (path relative to /ranges/, e.g. "lab/getdetails").
    For endpoints without a dedicated tool; all endpoints are listed in docs/API.md. Returns the raw
    response, including error results."""
    return await client(ctx).request(method, path, body if method == "POST" else None, check=False)


if settings.immersive_cre_enable_raw:
    tool("destructive")(raw_request)
