from __future__ import annotations

import copy
from typing import Any

import pytest

from immersive_cre_mcp.client import CreError
from immersive_cre_mcp.tools import flags as f
from tests.conftest import FakeClient

EXISTING = [
    {"FlagId": "f1", "Name": "One", "Value": 10, "CorrectAnswers": ["a"], "Custom": "kept"},
    {"FlagId": "f2", "Name": "Two", "Value": 20, "CorrectAnswers": ["b"]},
]


@pytest.fixture
def fake() -> FakeClient:
    flags = copy.deepcopy(EXISTING)
    return FakeClient({
        "scenarios/getdetails": {"Scenario": {"Flags": flags}},
        "events/getdetails": {"Event": {"Flags": copy.deepcopy(flags)}},
    })


def saved(fake: FakeClient, path: str = "scenarios/updateflags") -> list[dict[str, Any]]:
    body = fake.bodies(path)[-1]
    assert body is not None
    return body["Flags"]


@pytest.mark.parametrize("ids", [{}, {"scenario_id": "s", "event_id": "e"}])
async def test_owner_must_be_exactly_one(ctx: Any, ids: dict[str, str]) -> None:
    with pytest.raises(CreError, match="exactly one"):
        await f.list_flags(ctx, **ids)


async def test_list_flags_scenario_and_event(ctx: Any, fake: FakeClient) -> None:
    assert [x["FlagId"] for x in await f.list_flags(ctx, scenario_id="s")] == ["f1", "f2"]
    assert len(await f.list_flags(ctx, event_id="e")) == 2
    assert fake.bodies("events/getdetails") == [{"EventId": "e"}]


async def test_add_flag_appends_full_list(ctx: Any, fake: FakeClient) -> None:
    new = await f.add_flag(ctx, name="Three", correct_answers=["c", "C"], tags=["T1110"], scenario_id="s")
    assert new["Name"] == "Three" and new["Value"] == 10 and new["Tags"] == ["T1110"]
    assert new["FlagId"] not in ("f1", "f2")
    out = saved(fake)
    assert [x["FlagId"] for x in out] == ["f1", "f2", new["FlagId"]]
    assert out[0]["Custom"] == "kept"
    assert fake.bodies("scenarios/updateflags")[-1]["ScenarioId"] == "s"  # type: ignore[index]


@pytest.mark.parametrize(("position", "index"), [(0, 0), (1, 1), (-5, 0), (99, 2)])
async def test_add_flag_position_is_clamped(ctx: Any, fake: FakeClient, position: int, index: int) -> None:
    new = await f.add_flag(ctx, name="N", correct_answers=["x"], position=position, scenario_id="s")
    assert saved(fake)[index]["FlagId"] == new["FlagId"]


async def test_add_flag_requires_answers_or_dynamic(ctx: Any, fake: FakeClient) -> None:
    with pytest.raises(CreError, match="correct_answers"):
        await f.add_flag(ctx, name="N", scenario_id="s")
    assert not fake.bodies("scenarios/updateflags")


async def test_add_dynamic_flag(ctx: Any, fake: FakeClient) -> None:
    dyn = f.DynamicConfig(System="10.0.0.5", ScriptType="ssh", Script="cat /flag")
    new = await f.add_flag(ctx, name="Dyn", dynamic_config=dyn, event_id="e")
    assert new["Dynamic"] is True
    assert new["DynamicConfig"] == {"System": "10.0.0.5", "ScriptType": "ssh", "Script": "cat /flag"}
    assert new["CorrectAnswers"] == []
    assert saved(fake, "events/updateflags")[-1] == new


async def test_update_flag_changes_only_given_fields(ctx: Any, fake: FakeClient) -> None:
    out = await f.update_flag(ctx, flag_id="f1", points=50, hint="look closer", scenario_id="s")
    assert out == {**EXISTING[0], "Value": 50, "Hint": "look closer"}
    assert saved(fake)[1] == EXISTING[1]


async def test_update_flag_make_static(ctx: Any) -> None:
    fake = FakeClient({"scenarios/getdetails": {"Scenario": {"Flags": [
        {"FlagId": "d", "Dynamic": True, "DynamicConfig": {"Script": "x"}}]}}})
    ctx.request_context.lifespan_context = fake
    out = await f.update_flag(ctx, flag_id="d", make_static=True, correct_answers=["y"], scenario_id="s")
    assert out == {"FlagId": "d", "Dynamic": False, "CorrectAnswers": ["y"]}


async def test_unknown_flag_id(ctx: Any) -> None:
    with pytest.raises(CreError, match="no flag with FlagId nope"):
        await f.update_flag(ctx, flag_id="nope", scenario_id="s")
    with pytest.raises(CreError, match="no flag"):
        await f.delete_flag(ctx, flag_id="nope", scenario_id="s")


async def test_delete_flag(ctx: Any, fake: FakeClient) -> None:
    out = await f.delete_flag(ctx, flag_id="f1", scenario_id="s")
    assert out == {"removed": EXISTING[0], "remaining": 1}
    assert [x["FlagId"] for x in saved(fake)] == ["f2"]


async def test_reorder_flags(ctx: Any, fake: FakeClient) -> None:
    out = await f.reorder_flags(ctx, flag_ids=["f2", "f1"], scenario_id="s")
    assert [x["FlagId"] for x in out] == ["f2", "f1"]
    assert saved(fake) == out


@pytest.mark.parametrize("ids", [["f1"], ["f1", "f1"], ["f1", "f2", "f3"], ["f1", "x"]])
async def test_reorder_flags_requires_permutation(ctx: Any, fake: FakeClient, ids: list[str]) -> None:
    with pytest.raises(CreError, match="permutation"):
        await f.reorder_flags(ctx, flag_ids=ids, scenario_id="s")
    assert not fake.bodies("scenarios/updateflags")


async def test_reorder_flags_tolerates_flag_without_id(ctx: Any) -> None:
    ctx.request_context.lifespan_context = FakeClient({"scenarios/getdetails": {"Flags": [{"FlagId": "a"}, {"Name": "?"}]}})
    with pytest.raises(CreError, match="permutation"):
        await f.reorder_flags(ctx, flag_ids=["a"], scenario_id="s")


async def test_replace_flags_generates_missing_ids(ctx: Any, fake: FakeClient) -> None:
    out = await f.replace_flags(ctx, flags=[{"Name": "A"}, {"FlagId": "keep", "Name": "B"}], scenario_id="s")
    assert out[0]["FlagId"] and out[0]["Name"] == "A"
    assert out[1] == {"FlagId": "keep", "Name": "B"}
    assert saved(fake) == out
