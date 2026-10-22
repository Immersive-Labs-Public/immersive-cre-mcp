"""The MCP server instance and helpers shared by the tool modules."""
from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from .client import CreClient, CreError
from .config import settings

INSTRUCTIONS = """\
Immersive Labs Cyber Ranges (CRE) - authoring and operations.

Concepts:
- Scenario: a catalogued exercise (offensive/defensive) with flags ("tasks"), a participant briefing
  (Student markdown), an Admin markdown walkthrough, attached documents and an image. It points at a
  TemplateId. Scenarios must be published to become visible to participants.
- Template: a saved lab image. Launching a template creates a Lab. A lab can be saved as a template.
- Lab (range): a live VPC identified by VpcId ("vpc-..."), with Systems (EC2 instances, InstanceId
  "i-..."), Subnets (with security-group rules), Apps, snapshots and VPN configs.
- Event: a scheduled multi-team exercise built on a template, with its own flags, teams and participants.
- Flags: list of {FlagId, Name, Value (points), CorrectAnswers[], Hint, Tags[MITRE ids], Dynamic?,
  DynamicConfig?}. The API replaces the whole list on save; the flag tools do the read-modify-write.

Typical authoring flow: launch_lab / build systems & subnets -> create_template_from_lab ->
create_scenario + update_scenario(template_id=...) -> add_flag ... -> set_markdown(student, admin)
-> publish_scenario.

Launching and running labs costs money and counts against the account's lab limit (get_account);
power labs off when idle. The API (the one the web dashboard uses) is not formally documented or versioned: shapes can change. Tools
that return raw API data say so; `raw_request` reaches any endpoint listed in docs/API.md.
"""


@asynccontextmanager
async def lifespan(_: MCPServer) -> AsyncIterator[CreClient]:
    client = CreClient()
    try:
        yield client
    finally:
        await client.aclose()


mcp = MCPServer("immersive-cre", instructions=INSTRUCTIONS, lifespan=lifespan)

_ANNOTATIONS = {
    "read": ToolAnnotations(read_only_hint=True, open_world_hint=True),
    "write": ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True),
    "destructive": ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True),
}
F = TypeVar("F", bound=Callable[..., Any])


def tool(kind: Literal["read", "write", "destructive"]) -> Callable[[F], F]:
    """Register a tool with matching annotations. In read-only mode, only `read` tools are exposed."""
    def deco(fn: F) -> F:
        if kind == "read" or not settings.immersive_cre_read_only:
            mcp.tool(annotations=_ANNOTATIONS[kind])(fn)
        return fn
    return deco


def client(ctx: Context) -> CreClient:
    return cast(CreClient, ctx.request_context.lifespan_context)


# ── helpers ──────────────────────────────────────────────────────────────────
def find_key(d: Any, key: str, depth: int = 2) -> Any:
    """`d[key]`, or the first match one or two levels down (responses nest under Scenario/Event/Template)."""
    if not isinstance(d, dict):
        return None
    if key in d:
        return d[key]
    if depth:
        for v in d.values():
            found = find_key(v, key, depth - 1)
            if found is not None:
                return found
    return None


def pick(d: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: d[k] for k in keys if k in d and d[k] not in (None, "", [])}


def read_local_file(path: str, max_bytes: int | None = None) -> bytes:
    p = Path(path).expanduser()
    if not p.is_file():
        raise CreError(f"file not found: {p}")
    data = p.read_bytes()
    if max_bytes and len(data) > max_bytes:
        raise CreError(f"{p.name} is {len(data)} bytes; limit is {max_bytes}")
    return data


def write_local_file(path: str, data: bytes | str, mode: int = 0o644) -> str:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "wb") as f:
        f.write(data.encode() if isinstance(data, str) else data)
    return str(p.resolve())


def image_payload(path: str) -> tuple[str, str]:
    """(ImageType, ImageData) as the dashboard sends them: extension + raw base64, max 2MB."""
    ext = Path(path).suffix.lstrip(".").lower()
    if ext not in {"bmp", "jpg", "jpeg", "png", "gif", "svg"}:
        raise CreError("image must be bmp, jpg, jpeg, png, gif or svg")
    return ext, base64.b64encode(read_local_file(path, 2 * 1024 * 1024)).decode()
