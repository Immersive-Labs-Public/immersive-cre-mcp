from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from immersive_cre_mcp import tools  # noqa: F401 - registers tools
from immersive_cre_mcp.app import find_key, image_payload, mcp, pick, read_local_file, write_local_file
from immersive_cre_mcp.client import CreError


# ── helpers ──────────────────────────────────────────────────────────────────
def test_find_key_top_level_and_nested() -> None:
    assert find_key({"Flags": [1]}, "Flags") == [1]
    assert find_key({"Scenario": {"Flags": [2]}}, "Flags") == [2]
    assert find_key({"a": {"b": {"Flags": [3]}}}, "Flags") == [3]


def test_find_key_stops_at_depth_and_non_dicts() -> None:
    assert find_key({"a": {"b": {"c": {"Flags": 1}}}}, "Flags") is None
    assert find_key([{"Flags": 1}], "Flags") is None
    assert find_key(None, "Flags") is None


def test_pick_skips_missing_and_empty() -> None:
    d = {"a": 1, "b": None, "c": "", "d": [], "e": 0, "f": False}
    assert pick(d, "a", "b", "c", "d", "e", "f", "z") == {"a": 1, "e": 0, "f": False}


def test_read_local_file(tmp_path: Path) -> None:
    p = tmp_path / "f.txt"
    p.write_bytes(b"12345")
    assert read_local_file(str(p)) == b"12345"
    with pytest.raises(CreError, match="limit is 4"):
        read_local_file(str(p), max_bytes=4)
    with pytest.raises(CreError, match="file not found"):
        read_local_file(str(tmp_path / "missing"))


def test_write_local_file_creates_parents_with_mode(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "key.pem"
    out = write_local_file(str(target), "secret", mode=0o600)
    assert Path(out) == target.resolve()
    assert target.read_text() == "secret"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_image_payload(tmp_path: Path) -> None:
    img = tmp_path / "card.PNG"
    img.write_bytes(b"\x89PNG")
    assert image_payload(str(img)) == ("png", base64.b64encode(b"\x89PNG").decode())
    bad = tmp_path / "card.webp"
    bad.write_bytes(b"x")
    with pytest.raises(CreError, match="image must be"):
        image_payload(str(bad))


# ── tool registration ────────────────────────────────────────────────────────
async def test_tools_registered_with_descriptions_and_annotations() -> None:
    listed = await mcp.list_tools()
    by_name = {t.name: t for t in listed}
    assert len(by_name) > 50
    for t in listed:
        assert t.description, f"{t.name} has no description"
        assert t.annotations is not None, f"{t.name} has no annotations"
    assert by_name["get_account"].annotations.read_only_hint is True
    assert by_name["add_flag"].annotations.read_only_hint is False
    assert by_name["add_flag"].annotations.destructive_hint is False
    assert by_name["raw_request"].annotations.destructive_hint is True
    for name, t in by_name.items():
        if name.startswith("delete_"):
            assert t.annotations.destructive_hint is True, name


def _list_tools_subprocess(**env: str) -> list[dict[str, object]]:
    script = (
        "import asyncio, json\n"
        "from immersive_cre_mcp import tools\n"
        "from immersive_cre_mcp.app import mcp\n"
        "ts = asyncio.run(mcp.list_tools())\n"
        "print(json.dumps([{'name': t.name, 'ro': t.annotations.read_only_hint} for t in ts]))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", script], env={**os.environ, **env}, capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def test_read_only_mode_exposes_only_read_tools() -> None:
    full = _list_tools_subprocess()
    ro = _list_tools_subprocess(IMMERSIVE_CRE_READ_ONLY="true")
    assert ro and all(t["ro"] for t in ro)
    assert {t["name"] for t in ro} == {t["name"] for t in full if t["ro"]}


def test_raw_request_can_be_disabled() -> None:
    names = {t["name"] for t in _list_tools_subprocess(IMMERSIVE_CRE_ENABLE_RAW="false")}
    assert "raw_request" not in names
    assert "get_account" in names
