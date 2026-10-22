"""Labs (live ranges): lifecycle, power, settings, access, snapshots and VPN."""
from __future__ import annotations

import asyncio
import base64
import time
from typing import Any, Literal

from mcp.server.mcpserver import Context

from ..app import client, pick, tool, write_local_file
from ..client import CreError


# ── summaries ────────────────────────────────────────────────────────────────
def _system_summary(s: dict[str, Any]) -> dict[str, Any]:
    out = pick(s, "Name", "InstanceId", "Hostname", "OS", "State", "ActionState", "Type", "DiskSize",
               "AdminBox", "Attacker", "Snapshots", "Guacamole", "CredCaching", "Playbooks")
    out["IPs"] = [n["IpAddress"] for n in (s.get("NetworkInterfaces") or []) if n.get("IpAddress")]
    out["Interfaces"] = s.get("NetworkInterfaces") or []
    return out


def lab_summary(d: dict[str, Any]) -> dict[str, Any]:
    systems = d.get("Systems") or []
    states: dict[str, int] = {}
    for s in systems:
        st = str(s.get("State") or s.get("EC2State") or "unknown")
        states[st] = states.get(st, 0) + 1
    return {
        **pick(d, "VpcId", "Name", "Description", "State", "Running", "VpcCidr", "AutoOff", "Runtime",
               "LaunchInfo", "SnapLimit", "FullLabSnapLimit", "DhcpParams", "VpnParams", "TeamSim"),
        "SystemStates": states,
        "Systems": [_system_summary(s) for s in systems],
        "Subnets": d.get("Subnets") or [],
        "LabApps": d.get("LabApps") or [],
        "vpnConfigs": d.get("vpnConfigs") or [],
        "Documents": d.get("Documents") or [],
        "HasStudentMarkdown": bool((d.get("Markdown") or {}).get("Student")),
        "HasAdminMarkdown": bool((d.get("Markdown") or {}).get("Admin")),
    }


# ── lifecycle ────────────────────────────────────────────────────────────────
@tool("read")
async def list_labs(ctx: Context) -> list[dict[str, Any]]:
    """Labs in the account with their overall state."""
    return [
        pick(lab, "vpcId", "VpcId", "Name", "Description", "State", "TeamSim", "LastActivity")
        for lab in (await client(ctx).get("labs")).get("labs") or []
    ]


@tool("read")
async def get_lab(ctx: Context, vpc_id: str, raw: bool = False) -> dict[str, Any]:
    """A lab's full state: systems (InstanceIds, IPs, power, console creds, snapshots), subnets with
    security-group rules, apps, VPN configs, documents and settings. raw=true returns the API
    response untouched."""
    d = await client(ctx).post("lab/getdetails", {"vpcId": vpc_id})
    return d if raw else lab_summary(d)


@tool("write")
async def launch_lab(
    ctx: Context, name: str, template_id: str | None = None, scenario_id: str | None = None, description: str = "",
) -> dict[str, Any]:
    """Launch a lab from a template_id, or a scenario_id (uses its TemplateId). Provisioning takes
    minutes: follow with wait_for_lab. Counts against the account lab limit."""
    c = client(ctx)
    if not template_id:
        if not scenario_id:
            raise CreError("provide template_id or scenario_id")
        sc = (await c.post("scenarios/getdetails", {"ScenarioId": scenario_id})).get("Scenario") or {}
        template_id = sc.get("TemplateId")
        if not template_id:
            raise CreError(f"scenario {scenario_id} has no TemplateId")
    data = await c.post("lab/launch", {"LabId": template_id, "Name": name, "Description": description})
    return {"VpcId": data.get("VpcId"), "TemplateId": template_id, "next": "wait_for_lab(vpc_id)"}


@tool("write")
async def launch_blank_lab(
    ctx: Context,
    name: str,
    subnets: list[dict[str, str]],
    attacker_interface: str,
    description: str = "",
    cidr: str = "10.10.0.0/16",
) -> dict[str, Any]:
    """Create an empty lab to build a new range from scratch. subnets: [{"cidr": "10.10.1.0/24",
    "name": "Corp"}, ...] inside `cidr`. attacker_interface: CIDR of the subnet the attacker VPN
    pool routes to. Then add systems with add_system."""
    data = await client(ctx).post("lab/launch", {
        "Name": name, "Description": description, "Cidr": cidr, "Subnets": subnets,
        "AttackerInterface": attacker_interface,
    })
    return data


@tool("write")
async def launch_introductory_range(ctx: Context, domain_name: str) -> dict[str, Any]:
    """Launch the built-in "Introductory Range" (an AD domain lab) with the given domain name."""
    return await client(ctx).post("lab/launch", {
        "Name": "Introductory Range", "type": "introductoryRange", "Variables": {"domain_name": domain_name},
    })


@tool("read")
async def wait_for_lab(
    ctx: Context,
    vpc_id: str,
    target: Literal["running", "stopped"] = "running",
    timeout_seconds: int = 600,
    poll_seconds: int = 20,
) -> dict[str, Any]:
    """Poll until every system in the lab is `target` (timeout max 1800s). Returns
    {reached, SystemStates, lab}. Safe to call again after a timeout."""
    c = client(ctx)
    timeout_seconds = max(10, min(timeout_seconds, 1800))
    poll_seconds = max(5, min(poll_seconds, 120))
    deadline = time.monotonic() + timeout_seconds
    while True:
        d = await c.post("lab/getdetails", {"vpcId": vpc_id})
        states = [str(s.get("State") or s.get("EC2State") or "").lower() for s in d.get("Systems") or []]
        reached = bool(states) and all(st == target for st in states)
        remaining = deadline - time.monotonic()
        if reached or remaining <= 0:
            summary = lab_summary(d)
            return {"reached": reached, "target": target, "SystemStates": summary["SystemStates"], "lab": summary}
        done = sum(st == target for st in states)
        await ctx.report_progress(done, len(states) or None, f"{done}/{len(states)} systems {target}")
        await asyncio.sleep(min(poll_seconds, remaining))


@tool("write")
async def power_lab(
    ctx: Context, vpc_id: str, action: Literal["on", "off", "reboot"], instance_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Power the whole lab on/off/reboot, or only the given systems."""
    body: dict[str, Any] = {"VpcId": vpc_id, "Power": action}
    if instance_ids:
        body["InstanceIds"] = instance_ids
    return await client(ctx).post("lab/power", body)


@tool("write")
async def update_lab_settings(
    ctx: Context,
    vpc_id: str,
    name: str | None = None,
    description: str | None = None,
    auto_off_minutes: int | None = None,
) -> dict[str, Any]:
    """Rename a lab, change its description or idle auto-off (minutes, 0 = never). Unspecified
    fields keep their current values."""
    c = client(ctx)
    cur = await c.post("lab/getdetails", {"vpcId": vpc_id})
    return await c.post("lab/settings", {
        "VpcId": vpc_id,
        "Name": name if name is not None else cur.get("Name", ""),
        "Description": description if description is not None else cur.get("Description", ""),
        "AutoOff": auto_off_minutes if auto_off_minutes is not None else int(cur.get("AutoOff") or 0),
    })


@tool("destructive")
async def delete_lab(ctx: Context, vpc_id: str, force: bool = False) -> dict[str, Any]:
    """Permanently delete a lab and all its systems. Normally the lab must be powered off first
    (power_lab off, then wait_for_lab target=stopped); force=true skips that."""
    return await client(ctx).post("lab/delete/force" if force else "lab/delete", {"vpcId": vpc_id})


@tool("write")
async def checkin(ctx: Context) -> dict[str, Any]:
    """Mark the account active so the idle auto-off timer doesn't power down running labs."""
    return await client(ctx).post("checkin", {"IdleTime": 0})


# ── access ───────────────────────────────────────────────────────────────────
@tool("read")
async def get_lab_users(ctx: Context, vpc_id: str) -> list[dict[str, Any]]:
    """Users with access to a lab and their permission."""
    return (await client(ctx).post("lab/permissions", {"vpcId": vpc_id})).get("users") or []


@tool("write")
async def manage_lab_users(
    ctx: Context,
    vpc_id: str,
    action: Literal["add", "set_permission", "remove"],
    user_ids: list[str],
    permission: Literal["view", "edit", "limited"] = "view",
) -> list[dict[str, Any]]:
    """Grant users access to a lab (add), change their permission, or remove them. Returns the
    resulting access list."""
    c = client(ctx)
    if action == "add":
        await c.post("lab/permissions", {"vpcId": vpc_id, "userIds": user_ids, "permission": permission,
                                         "updateExistingUserPermissions": True})
    else:
        for uid in user_ids:
            body: dict[str, Any] = {"vpcId": vpc_id, "userId": uid}
            body |= {"delete": True} if action == "remove" else {"permission": permission}
            await c.post("lab/permissions", body)
    return (await c.post("lab/permissions", {"vpcId": vpc_id})).get("users") or []


@tool("write")
async def cache_lab_credentials(ctx: Context, vpc_id: str) -> dict[str, Any]:
    """Cache console credentials for all of a lab's systems (as the dashboard's "cache creds")."""
    return await client(ctx).post("lab/cachecreds", {"VpcId": vpc_id})


@tool("read")
async def download_lab_ssh_key(ctx: Context, vpc_id: str, key_type: str = "pem", save_path: str | None = None) -> dict[str, Any]:
    """Get the lab's SSH private key (key_type as the dashboard offers, e.g. pem / ppk). With
    save_path, writes it (mode 0600) instead of returning it."""
    data = await client(ctx).post("lab/sshkey", {"VpcId": vpc_id, "Type": key_type})
    key = data.get("key") or data.get("Key") or data.get("data")
    if save_path and isinstance(key, str):
        return {"path": write_local_file(save_path, key, 0o600)}
    return data


@tool("read")
async def get_launch_script_output(ctx: Context, vpc_id: str, script_id: str) -> dict[str, Any]:
    """Output of a template launch script (ids appear in the lab's LaunchInfo/settings)."""
    return await client(ctx).post("lab/scripts/output", {"VpcId": vpc_id, "ScriptId": script_id})


# ── snapshots ────────────────────────────────────────────────────────────────
@tool("write")
async def create_snapshot(ctx: Context, vpc_id: str, name: str, instance_ids: list[str] | None = None) -> dict[str, Any]:
    """Snapshot specific systems, or the whole lab when instance_ids is omitted (limits in get_lab:
    SnapLimit per system, FullLabSnapLimit)."""
    body: dict[str, Any] = {"VpcId": vpc_id, "CustomerName": name}
    if instance_ids:
        body["InstanceIds"] = instance_ids
    return await client(ctx).post("lab/snapshots/new", body)


@tool("destructive")
async def revert_snapshot(ctx: Context, vpc_id: str, snap_id: str, instance_id: str | None = None) -> dict[str, Any]:
    """Revert to a snapshot, discarding later changes. instance_id for a system snapshot; omit for
    a full-lab snapshot."""
    return await client(ctx).post("lab/snapshots/revert", {"VpcId": vpc_id, "SnapId": snap_id, "InstanceId": instance_id})


@tool("destructive")
async def delete_snapshot(ctx: Context, vpc_id: str, snap_id: str, instance_id: str | None = None) -> dict[str, Any]:
    """Delete a snapshot. instance_id for a system snapshot; omit for a full-lab snapshot."""
    if instance_id:
        return await client(ctx).post("lab/snapshots/delete", {"VpcId": vpc_id, "SnapId": snap_id, "InstanceId": instance_id})
    return await client(ctx).post("lab/snapshots/deletef", {"VpcId": vpc_id, "SnapId": snap_id})


# ── VPN ──────────────────────────────────────────────────────────────────────
@tool("write")
async def create_vpn(
    ctx: Context,
    vpc_id: str,
    name: str,
    access: Literal["user", "admin"] = "user",
    cert_type: Literal["UNIX", "WINDOWS"] = "UNIX",
) -> dict[str, Any]:
    """Issue an OpenVPN config. access=user is the Attacker pool; admin reaches the whole lab.
    Requires the AdminBox to be running. Returns UUID for download_vpn."""
    data = await client(ctx).post(
        "lab/vpn/new", {"vpcId": vpc_id, "certType": cert_type, "custName": name, "certAccess": access},
    )
    return {"UUID": data.get("UUID"), "next": "download_vpn; the cert can take a minute to issue"}


@tool("read")
async def download_vpn(ctx: Context, vpc_id: str, vpn_id: str, save_path: str | None = None) -> dict[str, Any]:
    """Fetch an issued .ovpn config (vpn_id = UUID). With save_path, writes it (mode 0600).
    ready=false means the cert is still being issued."""
    data = await client(ctx).request("POST", "lab/vpn/download", {"UUID": vpn_id, "vpcId": vpc_id}, check=False)
    if not data.get("config"):
        return {"ready": False, "message": data.get("message")}
    config = base64.b64decode(data["config"]).decode()
    if save_path:
        return {"ready": True, "path": write_local_file(save_path, config, 0o600)}
    return {"ready": True, "config": config}


@tool("destructive")
async def revoke_vpn(ctx: Context, vpc_id: str, vpn_id: str) -> dict[str, Any]:
    """Revoke a VPN config so it can no longer connect."""
    return await client(ctx).post("lab/vpn/revoke", {"UUID": vpn_id, "vpcId": vpc_id})
