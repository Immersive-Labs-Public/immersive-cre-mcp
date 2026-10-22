"""Flags ("tasks") on scenarios and events.

The API only accepts the whole list (scenarios/updateflags, events/updateflags), so every edit
here is read-modify-write. Unknown fields on existing flags are preserved.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

from mcp.server.mcpserver import Context
from pydantic import BaseModel, Field

from ..app import client, find_key, tool
from ..client import CreClient, CreError


class DynamicConfig(BaseModel):
    """A flag whose answer is generated at launch by running a script on a system."""

    System: str = Field(description="IP address of the system the script runs on")
    ScriptType: Literal["powershell", "ssh"]
    Script: str = Field(description="Script whose output becomes the flag value")
    Credentials: dict[str, str] | None = Field(
        default=None, description='{"Username", "Password"}; omit to use the system\'s stored creds',
    )


def _owner(scenario_id: str | None, event_id: str | None) -> tuple[str, str]:
    if bool(scenario_id) == bool(event_id):
        raise CreError("pass exactly one of scenario_id or event_id")
    return ("scenario", scenario_id) if scenario_id else ("event", event_id)  # type: ignore[return-value]


async def _load(c: CreClient, kind: str, owner_id: str) -> list[dict[str, Any]]:
    if kind == "scenario":
        data = await c.post("scenarios/getdetails", {"ScenarioId": owner_id})
    else:
        data = await c.post("events/getdetails", {"EventId": owner_id})
    return list(find_key(data, "Flags") or [])


async def _save(c: CreClient, kind: str, owner_id: str, flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if kind == "scenario":
        await c.post("scenarios/updateflags", {"ScenarioId": owner_id, "Flags": flags})
    else:
        await c.post("events/updateflags", {"EventId": owner_id, "Flags": flags})
    return flags


def _index(flags: list[dict[str, Any]], flag_id: str) -> int:
    for i, f in enumerate(flags):
        if f.get("FlagId") == flag_id:
            return i
    raise CreError(f"no flag with FlagId {flag_id}")


def _apply(flag: dict[str, Any], *, name: str | None, points: int | None, correct_answers: list[str] | None,
           hint: str | None, tags: list[str] | None, dynamic_config: DynamicConfig | None) -> dict[str, Any]:
    if name is not None:
        flag["Name"] = name
    if points is not None:
        flag["Value"] = points
    if correct_answers is not None:
        flag["CorrectAnswers"] = correct_answers
    if hint is not None:
        flag["Hint"] = hint
    if tags is not None:
        flag["Tags"] = tags
    if dynamic_config is not None:
        flag["Dynamic"] = True
        flag["DynamicConfig"] = dynamic_config.model_dump(exclude_none=True)
    return flag


@tool("read")
async def list_flags(ctx: Context, scenario_id: str | None = None, event_id: str | None = None) -> list[dict[str, Any]]:
    """All flags on a scenario or event, in order, including CorrectAnswers, hints, MITRE tags and
    dynamic-flag config."""
    kind, oid = _owner(scenario_id, event_id)
    return await _load(client(ctx), kind, oid)


@tool("write")
async def add_flag(
    ctx: Context,
    name: str,
    correct_answers: list[str] | None = None,
    points: int = 10,
    hint: str | None = None,
    tags: list[str] | None = None,
    dynamic_config: DynamicConfig | None = None,
    position: int | None = None,
    scenario_id: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Add a flag to a scenario or event. correct_answers lists every accepted answer. tags are MITRE
    ATT&CK technique ids (e.g. "T1110"). Use dynamic_config instead of correct_answers for a flag
    generated at launch. position is the 0-based insert index (default: end). Returns the new flag."""
    if not correct_answers and dynamic_config is None:
        raise CreError("provide correct_answers, or dynamic_config for a dynamic flag")
    c = client(ctx)
    kind, oid = _owner(scenario_id, event_id)
    flags = await _load(c, kind, oid)
    flag = _apply({"FlagId": str(uuid.uuid4())}, name=name, points=points, correct_answers=correct_answers or [],
                  hint=hint, tags=tags, dynamic_config=dynamic_config)
    flags.insert(len(flags) if position is None else max(0, min(position, len(flags))), flag)
    await _save(c, kind, oid, flags)
    return flag


@tool("write")
async def update_flag(
    ctx: Context,
    flag_id: str,
    name: str | None = None,
    correct_answers: list[str] | None = None,
    points: int | None = None,
    hint: str | None = None,
    tags: list[str] | None = None,
    dynamic_config: DynamicConfig | None = None,
    make_static: bool = False,
    scenario_id: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Edit one flag; unspecified fields are unchanged. make_static removes a dynamic config
    (supply correct_answers too). Returns the updated flag."""
    c = client(ctx)
    kind, oid = _owner(scenario_id, event_id)
    flags = await _load(c, kind, oid)
    flag = flags[_index(flags, flag_id)]
    if make_static:
        flag.pop("DynamicConfig", None)
        flag["Dynamic"] = False
    _apply(flag, name=name, points=points, correct_answers=correct_answers, hint=hint, tags=tags,
           dynamic_config=dynamic_config)
    await _save(c, kind, oid, flags)
    return flag


@tool("destructive")
async def delete_flag(ctx: Context, flag_id: str, scenario_id: str | None = None, event_id: str | None = None) -> dict[str, Any]:
    """Remove a flag from a scenario or event."""
    c = client(ctx)
    kind, oid = _owner(scenario_id, event_id)
    flags = await _load(c, kind, oid)
    removed = flags.pop(_index(flags, flag_id))
    await _save(c, kind, oid, flags)
    return {"removed": removed, "remaining": len(flags)}


@tool("write")
async def reorder_flags(
    ctx: Context, flag_ids: list[str], scenario_id: str | None = None, event_id: str | None = None,
) -> list[dict[str, Any]]:
    """Set flag order. flag_ids must contain every existing FlagId exactly once."""
    c = client(ctx)
    kind, oid = _owner(scenario_id, event_id)
    flags = await _load(c, kind, oid)
    by_id = {str(f.get("FlagId")): f for f in flags}
    if sorted(flag_ids) != sorted(by_id):
        raise CreError(f"flag_ids must be a permutation of the {len(by_id)} existing FlagIds")
    return await _save(c, kind, oid, [by_id[i] for i in flag_ids])


@tool("destructive")
async def replace_flags(
    ctx: Context, flags: list[dict[str, Any]], scenario_id: str | None = None, event_id: str | None = None,
) -> list[dict[str, Any]]:
    """Replace the entire flag list (bulk import / copy between scenarios). Each flag:
    {Name, Value, CorrectAnswers[], Hint?, Tags?, Dynamic?, DynamicConfig?, FlagId?}; a missing
    FlagId is generated. Existing flags not in the list are deleted."""
    c = client(ctx)
    kind, oid = _owner(scenario_id, event_id)
    out = [{"FlagId": str(uuid.uuid4()), **f} if not f.get("FlagId") else dict(f) for f in flags]
    return await _save(c, kind, oid, out)
