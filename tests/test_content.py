from __future__ import annotations

from typing import Any

import pytest

from immersive_cre_mcp.client import CreError
from immersive_cre_mcp.tools import content
from immersive_cre_mcp.tools.content import _inline_references
from tests.conftest import FakeClient


# ── reference-style link inlining ────────────────────────────────────────────
@pytest.mark.parametrize(("src", "expected"), [
    ("![a][img1]\n\n[img1]: <data:image/png;base64,AAA>", "![a](data:image/png;base64,AAA)\n"),
    ('See [Docs][] and [docs].\n\n[DOCS]: https://x.test "Title"',
     'See [Docs](https://x.test "Title") and [docs](https://x.test "Title").\n'),
    ("[x][sp]\n[sp]: <path with spaces.png>", "[x](<path with spaces.png>)"),
    ("[a](http://inline) [missing][nope]\n[b]: http://y.test", "[a](http://inline) [missing][nope]"),
    ("no refs here [x]", "no refs here [x]"),
])
def test_inline_references(src: str, expected: str) -> None:
    assert _inline_references(src) == expected


def test_inline_references_leaves_code_alone() -> None:
    src = "```\n[a][b]\n[b]: http://in-fence\n```\n`[a][b]` [a][b]\n\n[b]: http://y.test"
    assert _inline_references(src) == "```\n[a][b]\n[b]: http://in-fence\n```\n`[a][b]` [a](http://y.test)\n"


def test_inline_references_first_definition_wins() -> None:
    assert _inline_references("[a]\n[a]: http://one\n[a]: http://two") == "[a](http://one)"


# ── markdown tools ───────────────────────────────────────────────────────────
async def test_target_required(ctx: Any) -> None:
    with pytest.raises(CreError, match="pass one of"):
        await content.get_markdown(ctx)


async def test_get_markdown(ctx: Any, fake: FakeClient) -> None:
    fake.responses["scenarios/getdetails"] = {"Scenario": {"Markdown": {"Student": {"ID": "m1", "URL": "https://s3/m1"}}}}
    fake.urls["https://s3/m1"] = b"# Brief"
    assert await content.get_markdown(ctx, scenario_id="s") == {
        "exists": True, "kind": "student", "id": "m1", "markdown": "# Brief"}
    assert await content.get_markdown(ctx, kind="admin", scenario_id="s") == {"exists": False, "kind": "admin"}


async def test_set_markdown_requires_one_source(ctx: Any) -> None:
    with pytest.raises(CreError, match="exactly one"):
        await content.set_markdown(ctx, kind="student", scenario_id="s")
    with pytest.raises(CreError, match="exactly one"):
        await content.set_markdown(ctx, kind="student", markdown="x", file_path="y", scenario_id="s")


async def test_set_student_markdown_uploads_and_waits(ctx: Any, fake: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None: ...
    monkeypatch.setattr(content.asyncio, "sleep", no_sleep)
    fake.responses["docs/update"] = {"UrlData": {"url": "https://s3/up"}, "ID": "new"}
    fake.responses["lab/getdetails"] = [
        {"Markdown": {"Student": {"ID": "old"}}},
        {"Markdown": {"Student": {"ID": "new"}}},
    ]
    out = await content.set_markdown(ctx, kind="student", markdown="![a][i]\n[i]: http://img", vpc_id="vpc-1")
    assert out == {"kind": "student", "id": "new", "bytes": len(b"![a](http://img)"), "registered": True}
    assert fake.uploads == [({"url": "https://s3/up"}, "new", b"![a](http://img)")]
    body = fake.bodies("docs/update")[0]
    assert body == {"VpcId": "vpc-1", "StudentMarkdown": True, "AdminMarkdown": False}


async def test_set_admin_markdown_initialises_first(ctx: Any, fake: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None: ...
    monkeypatch.setattr(content.asyncio, "sleep", no_sleep)
    fake.responses["docs/update"] = {"UrlData": {"url": "u"}, "ID": "adm"}
    fake.responses["templates/getdetails"] = [{"Markdown": {}}, {"Markdown": {}}, {"Markdown": {"Admin": {"ID": "adm"}}}]
    out = await content.set_markdown(ctx, kind="admin", markdown="walkthrough", template_id="t")
    assert out["registered"] is True
    init, write = fake.bodies("docs/update")
    assert init == {"TemplateId": "t", "AdminMarkdown": True, "Init": True}
    assert write == {"TemplateId": "t", "StudentMarkdown": False, "AdminMarkdown": True}


async def test_set_markdown_reports_unregistered(ctx: Any, fake: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None: ...
    monkeypatch.setattr(content.asyncio, "sleep", no_sleep)
    fake.responses["docs/update"] = {"UrlData": {"url": "u"}, "ID": "new"}
    fake.responses["events/getdetails"] = {"Event": {"Markdown": {"Student": {"ID": "old"}}}}
    out = await content.set_markdown(ctx, kind="student", markdown="x", event_id="e")
    assert out["registered"] is False and "note" in out


async def test_set_markdown_without_upload_url(ctx: Any, fake: FakeClient) -> None:
    fake.responses["docs/update"] = {"result": "success"}
    with pytest.raises(CreError, match="no upload URL"):
        await content.set_markdown(ctx, kind="student", markdown="x", scenario_id="s")


# ── documents ────────────────────────────────────────────────────────────────
async def test_upload_document(ctx: Any, fake: FakeClient, tmp_path: Any) -> None:
    p = tmp_path / "notes.txt"
    p.write_bytes(b"hello")
    fake.responses["docs/update"] = {"UrlData": {"url": "u"}, "ID": "d1"}
    out = await content.upload_document(ctx, file_path=str(p), access="student", scenario_id="s")
    assert out == {"id": "d1", "name": "notes.txt", "access": "student", "bytes": 5}
    assert fake.uploads == [({"url": "u"}, "notes.txt", b"hello")]


async def test_download_document(ctx: Any, fake: FakeClient, tmp_path: Any) -> None:
    fake.responses["docs/download"] = {"url": "https://s3/d1"}
    fake.urls["https://s3/d1"] = b"data"
    assert await content.download_document(ctx, doc_id="d1", scenario_id="s") == {"bytes": 4, "content": "data"}
    out = await content.download_document(ctx, doc_id="d1", save_path=str(tmp_path / "o.bin"), scenario_id="s")
    assert (tmp_path / "o.bin").read_bytes() == b"data" and out["bytes"] == 4
