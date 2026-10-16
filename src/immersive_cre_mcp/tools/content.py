"""Markdown (participant briefing / admin walkthrough) and attached documents.

Content belongs to a scenario, lab, event or template. Uploads go through docs/update, which
returns a pre-signed S3 POST; the file is then posted straight to S3.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import Context

from ..app import client, find_key, read_local_file, tool, write_local_file
from ..client import CreClient, CreError

MarkdownKind = Literal["student", "admin"]


def _target(scenario_id: str | None, vpc_id: str | None, event_id: str | None, template_id: str | None) -> dict[str, Any]:
    t = {"VpcId": vpc_id, "EventId": event_id, "ScenarioId": scenario_id, "TemplateId": template_id}
    if not any(t.values()):
        raise CreError("pass one of scenario_id, vpc_id, event_id or template_id")
    return t


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_REF_DEF = re.compile(
    r"^ {0,3}\[((?:[^\[\]\\]|\\.)+)\]:[ \t]*(<[^<>\n]*>|\S+)"
    r"""(?:[ \t]+("[^"\n]*"|'[^'\n]*'|\([^()\n]*\)))?[ \t]*$"""
)
# Inline code spans pass through untouched; otherwise [text][label], [text][] or [label].
_REF_USE = re.compile(r"(`+)[^`]*?\1|(!?)\[((?:[^\[\]\\]|\\.)*)\](?:\[((?:[^\[\]\\]|\\.)*)\]|(?![\[(:]))")


def _ref_label(label: str) -> str:
    return " ".join(label.split()).casefold()


def _inline_references(text: str) -> str:
    """Rewrite reference-style links/images to inline form. The dashboard's Toast UI editor runs
    with referenceDefinition off, so `![a][img1]` + `[img1]: <data:...>` renders the definition
    as raw text (e.g. a wall of base64, as Google Docs markdown exports produce)."""
    lines = text.split("\n")
    defs: dict[str, str] = {}
    keep: list[tuple[str, bool]] = []  # (line, inside fenced code)
    fence = None
    for line in lines:
        m = _FENCE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            keep.append((line, True))
            continue
        if m:
            fence = m.group(1)
            keep.append((line, True))
            continue
        d = _REF_DEF.match(line)
        if d:
            dest = d.group(2)
            dest = dest[1:-1] if dest.startswith("<") else dest
            if not dest or re.search(r"[\s()]", dest):
                dest = f"<{dest}>"
            defs.setdefault(_ref_label(d.group(1)), dest + (f" {d.group(3)}" if d.group(3) else ""))
            continue
        keep.append((line, False))
    if not defs:
        return text

    def sub(m: re.Match[str]) -> str:
        if m.group(1):
            return m.group(0)
        bang, inner, label = m.group(2), m.group(3), m.group(4)
        target = defs.get(_ref_label(label or inner))
        return f"{bang}[{inner}]({target})" if target else m.group(0)

    return "\n".join(line if code else _REF_USE.sub(sub, line) for line, code in keep)


async def _details(c: CreClient, t: dict[str, Any]) -> dict[str, Any]:
    if t["ScenarioId"]:
        return await c.post("scenarios/getdetails", {"ScenarioId": t["ScenarioId"]})
    if t["VpcId"]:
        return await c.post("lab/getdetails", {"vpcId": t["VpcId"]})
    if t["EventId"]:
        return await c.post("events/getdetails", {"EventId": t["EventId"]})
    return await c.post("templates/getdetails", {"TemplateId": t["TemplateId"]})


@tool("read")
async def get_markdown(
    ctx: Context,
    kind: MarkdownKind = "student",
    scenario_id: str | None = None,
    vpc_id: str | None = None,
    event_id: str | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    """Read the participant briefing (kind=student) or admin walkthrough (kind=admin) markdown of a
    scenario, lab, event or template."""
    c = client(ctx)
    md = find_key(await _details(c, _target(scenario_id, vpc_id, event_id, template_id)), "Markdown") or {}
    entry = md.get(kind.capitalize()) if isinstance(md, dict) else None
    if not entry or not entry.get("URL"):
        return {"exists": False, "kind": kind}
    text = (await c.fetch_url(entry["URL"])).decode("utf-8", "replace")
    return {"exists": True, "kind": kind, "id": entry.get("ID"), "markdown": text}


@tool("write")
async def set_markdown(
    ctx: Context,
    kind: MarkdownKind,
    markdown: str | None = None,
    file_path: str | None = None,
    scenario_id: str | None = None,
    vpc_id: str | None = None,
    event_id: str | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    """Write the participant briefing (kind=student) or admin walkthrough (kind=admin), replacing
    the current text. Provide the content inline (markdown) or from a local file (file_path).
    Reference-style links/images are rewritten inline, as the dashboard can't render them.
    An admin walkthrough is created first if none exists."""
    if (markdown is None) == (file_path is None):
        raise CreError("provide exactly one of markdown or file_path")
    if markdown is None:
        markdown = read_local_file(file_path).decode("utf-8")  # type: ignore[arg-type]
    content = _inline_references(markdown).encode()
    c = client(ctx)
    t = _target(scenario_id, vpc_id, event_id, template_id)
    if kind == "admin":
        md = find_key(await _details(c, t), "Markdown") or {}
        if not (isinstance(md, dict) and md.get("Admin")):
            await c.post("docs/update", {**t, "AdminMarkdown": True, "Init": True})
    resp = await c.post("docs/update", {**t, "StudentMarkdown": kind == "student", "AdminMarkdown": kind == "admin"})
    url_data, doc_id = resp.get("UrlData"), resp.get("ID")
    if not url_data or not doc_id:
        raise CreError(f"no upload URL returned: {str(resp)[:300]}")
    await c.upload_presigned_post(url_data, str(doc_id), content)
    # The backend registers the new object asynchronously (~5s); wait so reads aren't stale.
    for _ in range(15):
        md = find_key(await _details(c, t), "Markdown") or {}
        if ((md.get(kind.capitalize()) or {}) if isinstance(md, dict) else {}).get("ID") == doc_id:
            return {"kind": kind, "id": doc_id, "bytes": len(content), "registered": True}
        await asyncio.sleep(2)
    return {"kind": kind, "id": doc_id, "bytes": len(content), "registered": False,
            "note": "uploaded, but not yet live; check get_markdown shortly"}


@tool("destructive")
async def delete_admin_markdown(
    ctx: Context,
    scenario_id: str | None = None,
    vpc_id: str | None = None,
    event_id: str | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    """Delete the admin walkthrough. Admins then see the student briefing instead."""
    t = _target(scenario_id, vpc_id, event_id, template_id)
    return await client(ctx).post("docs/update", {**t, "AdminMarkdown": True, "Delete": True})


@tool("read")
async def list_documents(
    ctx: Context,
    scenario_id: str | None = None,
    vpc_id: str | None = None,
    event_id: str | None = None,
    template_id: str | None = None,
) -> list[dict[str, Any]]:
    """Files attached to a scenario, lab, event or template ({ID, Name, Description, Access, ...})."""
    data = await _details(client(ctx), _target(scenario_id, vpc_id, event_id, template_id))
    return list(find_key(data, "Documents") or [])


@tool("write")
async def upload_document(
    ctx: Context,
    file_path: str,
    name: str | None = None,
    description: str = "",
    access: Literal["admin", "student"] = "admin",
    scenario_id: str | None = None,
    vpc_id: str | None = None,
    event_id: str | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    """Attach a local file to a scenario, lab, event or template. access=student makes it visible
    to participants; admin keeps it to range admins."""
    content = read_local_file(file_path)
    filename = Path(file_path).name
    c = client(ctx)
    t = _target(scenario_id, vpc_id, event_id, template_id)
    resp = await c.post("docs/update", {
        **t, "FileName": filename, "Name": name or filename, "Access": access, "Description": description,
    })
    url_data, doc_id = resp.get("UrlData"), resp.get("ID")
    if not url_data or not doc_id:
        raise CreError(f"no upload URL returned: {str(resp)[:300]}")
    await c.upload_presigned_post(url_data, filename, content)
    return {"id": doc_id, "name": name or filename, "access": access, "bytes": len(content)}


@tool("read")
async def download_document(
    ctx: Context,
    doc_id: str,
    save_path: str | None = None,
    scenario_id: str | None = None,
    vpc_id: str | None = None,
    event_id: str | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    """Download an attached document. With save_path, writes it to disk; otherwise returns the
    content as text (best for text files)."""
    c = client(ctx)
    t = _target(scenario_id, vpc_id, event_id, template_id)
    resp = await c.post("docs/download", {**t, "ID": doc_id})
    if not resp.get("url"):
        raise CreError(f"no download URL returned: {str(resp)[:300]}")
    data = await c.fetch_url(resp["url"])
    if save_path:
        return {"path": write_local_file(save_path, data), "bytes": len(data)}
    return {"bytes": len(data), "content": data.decode("utf-8", "replace")}


@tool("destructive")
async def delete_document(
    ctx: Context,
    doc_id: str,
    scenario_id: str | None = None,
    vpc_id: str | None = None,
    event_id: str | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    """Remove an attached document."""
    t = _target(scenario_id, vpc_id, event_id, template_id)
    return await client(ctx).post("docs/update", {**t, "ID": doc_id, "Delete": True})
