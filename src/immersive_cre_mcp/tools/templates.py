"""Lab templates."""
from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import Context

from ..app import client, tool
from ..client import CreError


@tool("read")
async def list_templates(ctx: Context, search: str = "", own_only: bool = False) -> list[dict[str, Any]]:
    """Lab templates visible to this account (own, shared with it, and public). `id` is what
    launch_lab and update_scenario(template_id=...) take."""
    q = search.lower()
    return [
        t for t in (await client(ctx).get("templates")).get("templates") or []
        if (not own_only or t.get("own"))
        and (not q or q in str(t.get("name", "")).lower() or q in str(t.get("description", "")).lower())
    ]


@tool("read")
async def get_template(ctx: Context, template_id: str) -> dict[str, Any]:
    """Full template definition: systems, subnets, sharing, markdown and documents (raw API data)."""
    return await client(ctx).post("templates/getdetails", {"TemplateId": template_id})


@tool("write")
async def create_template_from_lab(ctx: Context, vpc_id: str, name: str, description: str = "") -> dict[str, Any]:
    """Save a lab's current state (systems, network, apps) as a new template. Takes a while
    server-side; the template shows as `pending` in list_templates until ready."""
    return await client(ctx).post("templates/new", {"VpcId": vpc_id, "TemplateName": name, "TemplateDesc": description})


@tool("write")
async def edit_template(ctx: Context, template_id: str, name: str, description: str) -> dict[str, Any]:
    """Rename a template / change its description."""
    return await client(ctx).post("templates/edit", {"templateId": template_id, "name": name, "description": description})


@tool("write")
async def share_template(
    ctx: Context, template_id: str, public: bool | None = None, share_with: list[str] | None = None,
) -> dict[str, Any]:
    """Share a template, either publicly (public=true / false to make private) or with specific
    accounts by email (share_with)."""
    if (public is None) == (share_with is None):
        raise CreError("pass exactly one of public or share_with")
    body: dict[str, Any] = {"templateId": template_id}
    if share_with is not None:
        body["shareWith"] = share_with
    else:
        body["isPublic"] = public
    return await client(ctx).post("templates/share", body)


@tool("write")
async def revoke_template_share(ctx: Context, template_id: str, email: str) -> dict[str, Any]:
    """Stop sharing a template with one account."""
    return await client(ctx).post("templates/share/revoke", {"templateId": template_id, "email": email})


@tool("destructive")
async def delete_template(ctx: Context, template_id: str) -> dict[str, Any]:
    """Permanently delete a template."""
    return await client(ctx).post("templates/delete", {"templateId": template_id})
