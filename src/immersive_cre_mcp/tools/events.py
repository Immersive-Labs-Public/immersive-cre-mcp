"""Events: scheduled multi-team exercises (flags are managed with the flag tools via event_id)."""
from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver import Context

from ..app import client, find_key, image_payload, tool
from ..client import CreError


@tool("read")
async def list_events(ctx: Context) -> list[dict[str, Any]]:
    """Events in the account."""
    return (await client(ctx).get("events")).get("Events") or []


@tool("read")
async def get_event(ctx: Context, event_id: str) -> dict[str, Any]:
    """Full event: schedule, template, scoring settings, flags, markdown and documents (raw API data)."""
    return await client(ctx).post("events/getdetails", {"EventId": event_id})


@tool("read")
async def list_event_teams(ctx: Context, event_id: str, page: int = 1, page_size: int = 20, search: str = "") -> dict[str, Any]:
    """Teams in an event with their participants and labs (paged)."""
    path = f"events/{event_id}/teams?page={page}&pageSize={page_size}"
    if search:
        path += f"&search={search}"
    return await client(ctx).get(path)


@tool("write")
async def create_event(
    ctx: Context,
    name: str,
    start_time: int,
    end_time: int,
    description: str = "",
    lab_cleanup_delay: int | None = None,
    source_event_id: str | None = None,
) -> dict[str, Any]:
    """Create an event. Times are epoch milliseconds. lab_cleanup_delay: how long after end_time
    team labs are removed. source_event_id copies an existing event. Then update_event to set
    the template, and add teams/participants."""
    return await client(ctx).post("events/create", {
        "Name": name, "Description": description, "StartTime": start_time, "EndTime": end_time,
        "LabCleanupDelay": lab_cleanup_delay, "SourceEventId": source_event_id,
    })


@tool("write")
async def update_event(
    ctx: Context,
    event_id: str,
    name: str | None = None,
    description: str | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
    template_id: str | None = None,
    lab_cleanup_delay: int | None = None,
    private_scoring: bool | None = None,
) -> dict[str, Any]:
    """Edit event settings (times in epoch ms). Unspecified fields keep their current values.
    private_scoring hides other teams' scores from participants."""
    c = client(ctx)
    cur = await c.post("events/getdetails", {"EventId": event_id})

    def keep(new: Any, key: str) -> Any:
        return new if new is not None else find_key(cur, key)

    return await c.post("events/update", {
        "EventId": event_id,
        "Name": keep(name, "Name"),
        "Description": keep(description, "Description"),
        "StartTime": keep(start_time, "StartTime"),
        "EndTime": keep(end_time, "EndTime"),
        "TemplateId": keep(template_id, "TemplateId"),
        "LabCleanupDelay": keep(lab_cleanup_delay, "LabCleanupDelay"),
        "PrivateScoring": keep(private_scoring, "PrivateScoring"),
    })


@tool("write")
async def set_event_image(ctx: Context, event_id: str, image_path: str) -> dict[str, Any]:
    """Upload a local image (bmp/jpg/png/gif/svg, under 2MB) as the event image."""
    image_type, image_data = image_payload(image_path)
    return await client(ctx).post("events/updateimg", {"EventId": event_id, "ImageType": image_type, "ImageData": image_data})


@tool("destructive")
async def delete_event(ctx: Context, event_id: str) -> dict[str, Any]:
    """Permanently delete an event."""
    return await client(ctx).post("events/delete", {"EventId": event_id})


@tool("write")
async def manage_event_team(
    ctx: Context,
    event_id: str,
    action: Literal["add", "rename", "delete"],
    name: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    """Add a team (name), rename one (team_id + name) or delete one (team_id)."""
    if action == "add":
        if not name:
            raise CreError("name is required")
        body = {"AddTeam": True, "EventId": event_id, "Name": name}
    elif not team_id:
        raise CreError("team_id is required")
    elif action == "rename":
        body = {"UpdateTeam": True, "EventId": event_id, "TeamId": team_id, "Name": name}
    else:
        body = {"DeleteTeam": True, "EventId": event_id, "TeamId": team_id}
    return await client(ctx).post("events/participants", body)


@tool("write")
async def manage_event_participant(
    ctx: Context,
    event_id: str,
    action: Literal["add", "move", "remove"],
    team_id: str,
    user_id: str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """Add a participant to a team (user_id of an existing user, or email to invite), move them to
    team_id, or remove them from team_id."""
    if action == "add":
        body = {"AddParticipant": True, "EventId": event_id, "TeamId": team_id, "UserId": user_id, "Email": email}
    elif action == "move":
        body = {"UpdateParticipant": True, "EventId": event_id, "TeamId": team_id, "UserId": user_id}
    else:
        body = {"DeleteParticipant": True, "EventId": event_id, "TeamId": team_id, "UserId": user_id}
    return await client(ctx).post("events/participants", body)


@tool("write")
async def launch_event_lab(ctx: Context, team_id: str, relaunch_from_latest: bool = False) -> dict[str, Any]:
    """Launch (or relaunch from the latest template version) a team's lab for an event."""
    body: dict[str, Any] = {"TeamId": team_id}
    if relaunch_from_latest:
        body["RelaunchFromLatest"] = True
    return await client(ctx).post("lab/eventlaunch", body)


@tool("read")
async def get_event_scores(ctx: Context, event_id: str, admin: bool = True) -> dict[str, Any]:
    """Event scoreboard. admin=true includes every team's flag submissions."""
    return await client(ctx).post("lab/scoring", {"EventId": event_id, "Admin": admin})


@tool("write")
async def submit_flag(ctx: Context, event_id: str, flag: str) -> dict[str, Any]:
    """Submit a flag answer as the current user in an event (useful to test flags end to end)."""
    return await client(ctx).post("lab/scoring", {"EventId": event_id, "Flag": flag})
