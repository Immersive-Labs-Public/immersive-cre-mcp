"""Request-shaping logic in the scenario, template, lab and event tools."""
from __future__ import annotations

from typing import Any

import pytest

from immersive_cre_mcp.client import CreError
from immersive_cre_mcp.tools import events, labs, scenarios, templates
from tests.conftest import FakeClient

CATALOGUE = [
    {"ScenarioId": "1", "Name": "Phish Hunt", "ScenarioType": "defensive", "Difficulty": "beginner",
     "CustomerId": "public", "Extra": "dropped"},
    {"ScenarioId": "2", "Name": "AD Attack", "ScenarioType": "offensive", "Difficulty": "advanced",
     "CustomerId": "c1", "Description": "kerberoast the domain"},
]


async def test_list_scenarios_filters(ctx: Any, fake: FakeClient) -> None:
    fake.responses["scenarios"] = {"Scenarios": CATALOGUE}

    async def ids(**kw: Any) -> list[str]:
        return [r["ScenarioId"] for r in await scenarios.list_scenarios(ctx, **kw)]

    assert await ids() == ["1", "2"]
    assert await ids(scenario_type="offensive") == ["2"]
    assert await ids(difficulty="beginner") == ["1"]
    assert await ids(own_only=True) == ["2"]
    assert await ids(search="KERBEROAST") == ["2"]
    assert await ids(search="phish") == ["1"]
    assert "Extra" not in (await scenarios.list_scenarios(ctx))[0]


async def test_update_scenario_keeps_current_values(ctx: Any, fake: FakeClient) -> None:
    fake.responses["scenarios/getdetails"] = {"Scenario": {
        "Name": "Old", "Description": "d", "TemplateId": "t1", "ScenarioType": "offensive", "ContainsMalware": True}}
    await scenarios.update_scenario(ctx, scenario_id="s", name="New", contains_malware=False)
    assert fake.bodies("scenarios/update")[-1] == {
        "ScenarioId": "s", "Name": "New", "Description": "d", "TemplateId": "t1",
        "ScenarioType": "offensive", "ContainsMalware": False}


async def test_get_scenario_inlines_markdown_and_strips_urls(ctx: Any, fake: FakeClient) -> None:
    fake.responses["scenarios/getdetails"] = {"result": "success", "Systems": [], "Scenario": {
        "Name": "S", "Markdown": {"Student": {"ID": "m1", "URL": "https://s3/m1"}, "Admin": {"ID": "m2", "URL": "https://s3/m2"}}}}
    fake.urls["https://s3/m1"] = b"student text"  # m2 missing -> fetch error reported inline
    out = await scenarios.get_scenario(ctx, scenario_id="s")
    s = out["Scenario"]
    assert s["StudentMarkdown"] == "student text"
    assert s["AdminMarkdown"].startswith("<failed to fetch")
    assert s["Markdown"] == {"Student": {"ID": "m1"}, "Admin": {"ID": "m2"}}
    assert "result" not in out and out["Systems"] == []


async def test_list_templates_filters(ctx: Any, fake: FakeClient) -> None:
    fake.responses["templates"] = {"templates": [
        {"id": "a", "name": "Windows AD", "own": True}, {"id": "b", "name": "Linux", "description": "web", "own": False}]}
    assert [t["id"] for t in await templates.list_templates(ctx, own_only=True)] == ["a"]
    assert [t["id"] for t in await templates.list_templates(ctx, search="WEB")] == ["b"]


@pytest.mark.parametrize("kw", [{}, {"public": True, "share_with": ["x@y"]}])
async def test_share_template_needs_exactly_one_mode(ctx: Any, kw: dict[str, Any]) -> None:
    with pytest.raises(CreError, match="exactly one"):
        await templates.share_template(ctx, template_id="t", **kw)


async def test_share_template_bodies(ctx: Any, fake: FakeClient) -> None:
    await templates.share_template(ctx, template_id="t", public=False)
    await templates.share_template(ctx, template_id="t", share_with=["a@b"])
    assert fake.bodies("templates/share") == [
        {"templateId": "t", "isPublic": False}, {"templateId": "t", "shareWith": ["a@b"]}]


def test_lab_summary() -> None:
    out = labs.lab_summary({
        "VpcId": "vpc-1", "Name": "L", "Description": "",
        "Systems": [
            {"Name": "a", "State": "running", "NetworkInterfaces": [{"IpAddress": "10.0.0.1"}, {}]},
            {"Name": "b", "EC2State": "stopped"},
            {"Name": "c", "State": "running"},
        ],
        "Markdown": {"Student": {"ID": "x"}},
    })
    assert out["SystemStates"] == {"running": 2, "stopped": 1}
    assert out["Systems"][0]["IPs"] == ["10.0.0.1"]
    assert "Description" not in out
    assert out["HasStudentMarkdown"] is True and out["HasAdminMarkdown"] is False


async def test_launch_lab_resolves_template_from_scenario(ctx: Any, fake: FakeClient) -> None:
    fake.responses["scenarios/getdetails"] = {"Scenario": {"TemplateId": "t9"}}
    fake.responses["lab/launch"] = {"VpcId": "vpc-9"}
    out = await labs.launch_lab(ctx, name="L", scenario_id="s")
    assert out["VpcId"] == "vpc-9" and out["TemplateId"] == "t9"
    assert fake.bodies("lab/launch") == [{"LabId": "t9", "Name": "L", "Description": ""}]


async def test_launch_lab_errors(ctx: Any, fake: FakeClient) -> None:
    with pytest.raises(CreError, match="template_id or scenario_id"):
        await labs.launch_lab(ctx, name="L")
    fake.responses["scenarios/getdetails"] = {"Scenario": {}}
    with pytest.raises(CreError, match="no TemplateId"):
        await labs.launch_lab(ctx, name="L", scenario_id="s")
    assert not fake.bodies("lab/launch")


async def test_manage_event_team(ctx: Any, fake: FakeClient) -> None:
    with pytest.raises(CreError, match="name is required"):
        await events.manage_event_team(ctx, event_id="e", action="add")
    with pytest.raises(CreError, match="team_id is required"):
        await events.manage_event_team(ctx, event_id="e", action="delete")
    await events.manage_event_team(ctx, event_id="e", action="add", name="Red")
    await events.manage_event_team(ctx, event_id="e", action="delete", team_id="t1")
    assert fake.bodies("events/participants") == [
        {"AddTeam": True, "EventId": "e", "Name": "Red"},
        {"DeleteTeam": True, "EventId": "e", "TeamId": "t1"},
    ]


async def test_update_event_keeps_nested_values(ctx: Any, fake: FakeClient) -> None:
    fake.responses["events/getdetails"] = {"Event": {"Name": "E", "StartTime": 1, "EndTime": 2, "PrivateScoring": True}}
    await events.update_event(ctx, event_id="e", end_time=5)
    assert fake.bodies("events/update")[-1] == {
        "EventId": "e", "Name": "E", "StartTime": 1, "EndTime": 5, "PrivateScoring": True}
