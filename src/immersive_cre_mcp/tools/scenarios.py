"""Scenario catalogue and authoring."""
from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver import Context

from ..app import client, image_payload, tool

ScenarioType = Literal["offensive", "defensive"]
Difficulty = Literal["beginner", "intermediate", "advanced"]


@tool("read")
async def list_scenarios(
    ctx: Context,
    scenario_type: ScenarioType | None = None,
    difficulty: Difficulty | None = None,
    search: str = "",
    own_only: bool = False,
) -> list[dict[str, Any]]:
    """Scenario catalogue. Filter by type, difficulty, name/description text, or only this
    account's own scenarios (own_only excludes Immersive-authored public ones)."""
    rows = (await client(ctx).get("scenarios")).get("Scenarios") or []
    q = search.lower()
    return [
        {k: r.get(k) for k in ("ScenarioId", "Name", "ScenarioType", "Difficulty", "Description",
                               "CustomerId", "IsAuthoredByImmersive", "Status") if k in r}
        for r in rows
        if (not scenario_type or r.get("ScenarioType") == scenario_type)
        and (not difficulty or r.get("Difficulty") == difficulty)
        and (not own_only or r.get("CustomerId") != "public")
        and (not q or q in str(r.get("Name", "")).lower() or q in str(r.get("Description", "")).lower())
    ]


@tool("read")
async def get_scenario(ctx: Context, scenario_id: str, include_markdown: bool = True) -> dict[str, Any]:
    """Everything about a scenario: settings, TemplateId, systems, subnets, flags (with answers),
    documents, publishing status. include_markdown inlines the Student briefing and Admin walkthrough
    text as StudentMarkdown / AdminMarkdown."""
    c = client(ctx)
    data = await c.post("scenarios/getdetails", {"ScenarioId": scenario_id})
    s = dict(data.get("Scenario") or {})
    out = {"Scenario": s, **{k: v for k, v in data.items() if k not in ("Scenario", "result")}}
    md = s.get("Markdown") or {}
    if include_markdown and isinstance(md, dict):
        # Pre-signed URLs expire in ~30s, so fetch immediately.
        for key in ("Student", "Admin"):
            url = (md.get(key) or {}).get("URL")
            if url:
                try:
                    s[f"{key}Markdown"] = (await c.fetch_url(url)).decode("utf-8", "replace")
                except Exception as exc:  # noqa: BLE001 - report inline, don't fail the call
                    s[f"{key}Markdown"] = f"<failed to fetch: {exc}>"
    # The pre-signed URLs are long and expire in ~30s: keep only the ids.
    if isinstance(md, dict):
        s["Markdown"] = {k: {"ID": (v or {}).get("ID")} for k, v in md.items()}
    return out


@tool("write")
async def create_scenario(
    ctx: Context, name: str, description: str = "", source_scenario_id: str | None = None,
) -> dict[str, Any]:
    """Create a new scenario, optionally copying an existing one (source_scenario_id). Then use
    update_scenario to set its template/type/difficulty, and the flag/markdown tools to fill it."""
    return await client(ctx).post(
        "scenarios/create", {"Name": name, "Description": description, "SourceScenarioId": source_scenario_id},
    )


@tool("write")
async def update_scenario(
    ctx: Context,
    scenario_id: str,
    name: str | None = None,
    description: str | None = None,
    template_id: str | None = None,
    scenario_type: ScenarioType | None = None,
    difficulty: Difficulty | None = None,
    participant_system_id: str | None = None,
    key_takeaways: str | None = None,
    contains_malware: bool | None = None,
) -> dict[str, Any]:
    """Edit scenario settings. Unspecified fields keep their current values.
    participant_system_id is the system participants are given (e.g. their Kali box).
    key_takeaways is free text (markdown) shown to participants on completion."""
    c = client(ctx)
    cur = (await c.post("scenarios/getdetails", {"ScenarioId": scenario_id})).get("Scenario") or {}

    def keep(new: Any, key: str) -> Any:
        return new if new is not None else cur.get(key)

    return await c.post("scenarios/update", {
        "ScenarioId": scenario_id,
        "Name": keep(name, "Name"),
        "Description": keep(description, "Description"),
        "TemplateId": keep(template_id, "TemplateId"),
        "ScenarioType": keep(scenario_type, "ScenarioType"),
        "Difficulty": keep(difficulty, "Difficulty"),
        "ParticipantSystemId": keep(participant_system_id, "ParticipantSystemId"),
        "KeyTakeaways": keep(key_takeaways, "KeyTakeaways"),
        "ContainsMalware": keep(contains_malware, "ContainsMalware"),
    })


@tool("write")
async def set_scenario_suggested_labs(ctx: Context, scenario_id: str, lab_ids: list[str]) -> dict[str, Any]:
    """Set the immersive labs suggested alongside this scenario (ids from search_immersive_labs)."""
    return await client(ctx).post("scenarios/update", {"ScenarioId": scenario_id, "SuggestedLabIds": lab_ids})


@tool("read")
async def search_immersive_labs(ctx: Context, search: str) -> dict[str, Any]:
    """Search the immersive platform's lab catalogue (for suggested labs)."""
    return await client(ctx).post("scenarios/labs", {"searchTerm": search})


@tool("write")
async def set_scenario_image(ctx: Context, scenario_id: str, image_path: str) -> dict[str, Any]:
    """Upload a local image (bmp/jpg/png/gif/svg, under 2MB) as the scenario's card image."""
    image_type, image_data = image_payload(image_path)
    return await client(ctx).post(
        "scenarios/updateimg", {"ScenarioId": scenario_id, "ImageType": image_type, "ImageData": image_data},
    )


@tool("write")
async def publish_scenario(ctx: Context, scenario_id: str, unpublish: bool = False) -> dict[str, Any]:
    """Publish a scenario so participants can see it (or unpublish it). Returns the publishing status."""
    return await client(ctx).post("scenarios/publish", {"ScenarioId": scenario_id, "Unpublish": unpublish})


@tool("destructive")
async def delete_scenario(ctx: Context, scenario_id: str) -> dict[str, Any]:
    """Permanently delete a scenario (its template and labs are untouched)."""
    return await client(ctx).post("scenarios/delete", {"ScenarioId": scenario_id})
