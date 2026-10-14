"""Building a lab: systems, images, credentials, playbooks, subnets, apps and DHCP."""
from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver import Context

from ..app import client, tool
from ..client import CreError


# ── systems ──────────────────────────────────────────────────────────────────
@tool("write")
async def add_system(
    ctx: Context,
    vpc_id: str,
    name: str,
    subnet_id: str,
    instance_type: str = "t3.medium",
    disk_gb: int = 30,
    hostname: str | None = None,
    ip_address: str | None = None,
    image_id: str | None = None,
    image_ami: str | None = None,
) -> dict[str, Any]:
    """Add a system to a lab. Choose a base image from list_images (image_id) or a custom AMI
    (image_ami, check it with validate_ami). subnet_id is a lab Subnet Id from get_lab."""
    if not image_id and not image_ami:
        raise CreError("provide image_id (from list_images) or image_ami")
    return await client(ctx).post("lab/systems/add", {
        "VpcId": vpc_id, "ImageId": image_id, "ImageAmi": image_ami, "Name": name, "Hostname": hostname,
        "Type": instance_type, "DiskSize": disk_gb, "SubnetId": subnet_id, "IpAddress": ip_address,
    })


@tool("write")
async def update_system(
    ctx: Context,
    vpc_id: str,
    instance_id: str,
    name: str | None = None,
    hostname: str | None = None,
    attacker: bool | None = None,
    instance_type: str | None = None,
    disk_gb: int | None = None,
) -> dict[str, Any]:
    """Edit a system: name/hostname/attacker flag, instance type (e.g. t3.large), or grow its disk.
    Unspecified fields are unchanged. attacker=true marks it as the participant's own box."""
    c = client(ctx)
    results: dict[str, Any] = {}
    if name is not None or hostname is not None or attacker is not None:
        lab = await c.post("lab/getdetails", {"vpcId": vpc_id})
        cur = next((s for s in lab.get("Systems") or [] if s.get("InstanceId") == instance_id), None)
        if cur is None:
            raise CreError(f"no system {instance_id} in {vpc_id}")
        results["info"] = await c.post("lab/systems/info", {
            "VpcId": vpc_id, "InstanceId": instance_id,
            "Name": name if name is not None else cur.get("Name"),
            "Hostname": hostname if hostname is not None else cur.get("Hostname", ""),
            "Attacker": attacker if attacker is not None else bool(cur.get("Attacker")),
        })
    if instance_type is not None:
        results["type"] = await c.post("lab/systems/specs", {"VpcId": vpc_id, "InstanceId": instance_id, "Type": instance_type})
    if disk_gb is not None:
        results["disk"] = await c.post("lab/systems/specs", {"VpcId": vpc_id, "InstanceId": instance_id, "DiskSize": disk_gb})
    if not results:
        raise CreError("nothing to update")
    return results


@tool("destructive")
async def delete_system(ctx: Context, vpc_id: str, instance_id: str) -> dict[str, Any]:
    """Permanently remove a system from a lab."""
    return await client(ctx).post("lab/systems/delete", {"VpcId": vpc_id, "InstanceId": instance_id})


@tool("write")
async def manage_system_interface(
    ctx: Context,
    vpc_id: str,
    instance_id: str,
    action: Literal["add", "remove"],
    subnet_id: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    """Add a network interface to a system on another subnet (optional fixed ip_address), or remove
    its secondary interface."""
    if action == "add":
        if not subnet_id:
            raise CreError("subnet_id is required to add an interface")
        body = {"VpcId": vpc_id, "InstanceId": instance_id, "SubnetId": subnet_id, "IpAddress": ip_address}
    else:
        body = {"VpcId": vpc_id, "InstanceId": instance_id, "Delete": True}
    return await client(ctx).post("lab/systems/network", body)


@tool("read")
async def get_system_console(ctx: Context, vpc_id: str, instance_id: str) -> dict[str, Any]:
    """Browser (Guacamole) console URL for a running system."""
    return await client(ctx).post("lab/systems/console", {"InstanceId": instance_id, "VpcId": vpc_id})


@tool("write")
async def set_system_credentials(
    ctx: Context,
    vpc_id: str,
    instance_id: str,
    credentials: dict[str, Any] | list[dict[str, Any]],
    which: Literal["console", "cached"] = "console",
) -> dict[str, Any]:
    """Set how the console connects to a system. A credential is {Protocol: RDP|SSH|VNC, Username?,
    Password?, Port?, Domain? (RDP), DisableFT?, DisableCopy?, DisablePaste?, SftpPort?, SftpPassword?}.
    which=console sets the primary console login (one object); which=cached sets the list of extra
    cached credentials (a list; [] clears)."""
    body: dict[str, Any] = {"VpcId": vpc_id, "InstanceId": instance_id}
    body["Console" if which == "console" else "Cached"] = credentials
    return await client(ctx).post("lab/systems/creds", body)


@tool("write")
async def create_image_from_system(
    ctx: Context, vpc_id: str, instance_id: str, name: str, description: str = "", app_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Save a system as a reusable custom image (appears in list_images). app_ids: LabApps to bundle."""
    return await client(ctx).post("lab/systems/image", {
        "VpcId": vpc_id, "InstanceId": instance_id, "Name": name, "Description": description, "AppIds": app_ids or [],
    })


@tool("read")
async def list_images(ctx: Context, search: str = "") -> Any:
    """Base and custom images available for add_system."""
    data = await client(ctx).post("getimages", {})
    if not search:
        return data
    q = search.lower()
    images = data.get("Images") or data.get("images")
    if isinstance(images, list):
        return [i for i in images if q in str(i).lower()]
    return data


@tool("read")
async def get_image_info(ctx: Context, vpc_id: str, image_id: str) -> dict[str, Any]:
    """Details of one image (OS, default size, credentials) in the context of a lab."""
    return await client(ctx).post("getimages", {"VpcId": vpc_id, "ImageId": image_id})


@tool("read")
async def get_instance_pricing(ctx: Context, vpc_id: str, instance_id: str) -> dict[str, Any]:
    """Instance-type options and pricing for an existing system (for update_system)."""
    return await client(ctx).post("getimages", {"VpcId": vpc_id, "InstanceId": instance_id})


@tool("read")
async def validate_ami(ctx: Context, ami: str) -> dict[str, Any]:
    """Check a custom AMI id can be used with add_system(image_ami=...)."""
    return await client(ctx).post("lab/validateami", {"AMI": ami})


# ── playbooks ────────────────────────────────────────────────────────────────
@tool("read")
async def get_playbook(ctx: Context, playbook_id: str) -> dict[str, Any]:
    """An Ansible playbook available to systems (ids are in each system's Playbooks)."""
    return await client(ctx).get(f"playbook/{playbook_id}")


@tool("write")
async def run_playbook(ctx: Context, playbook_id: str, vpc_id: str, instance_id: str) -> dict[str, Any]:
    """Run an Ansible playbook against a system."""
    return await client(ctx).post(f"playbook/{playbook_id}/run", {"instanceId": instance_id, "vpcId": vpc_id})


@tool("read")
async def get_playbook_jobs(ctx: Context, vpc_id: str, instance_id: str) -> dict[str, Any]:
    """Playbook runs on a system and their status/output."""
    return await client(ctx).get(f"labs/{vpc_id}/systems/{instance_id}/playbook-jobs")


# ── network ──────────────────────────────────────────────────────────────────
@tool("write")
async def manage_subnet(
    ctx: Context,
    vpc_id: str,
    action: Literal["add", "update", "delete"],
    subnet_id: str | None = None,
    name: str | None = None,
    cidr: str | None = None,
    description: str = "",
    inbound: list[dict[str, Any]] | None = None,
    outbound: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Add, update or delete a lab subnet and its security-group rules. Rules look like
    {"ipRange": "10.10.0.0/16", "protocol": "-1"|"tcp"|"udp"|"icmp", "fromPort": 22|null,
    "toPort": 22|null, "description": "..."}. update replaces name/description/rules (pass the full
    rule lists; see get_lab Subnets for the current ones)."""
    c = client(ctx)
    if action == "delete":
        if not subnet_id:
            raise CreError("subnet_id is required")
        return await c.post("lab/subnets", {"VpcId": vpc_id, "SubnetId": subnet_id, "Delete": True})
    if not name or not cidr:
        raise CreError("name and cidr are required")
    subnet = {"Name": name, "Description": description, "Cidr": cidr,
              "Inbound": inbound or [], "Outbound": outbound or []}
    if action == "add":
        return await c.post("lab/subnets", {"VpcId": vpc_id, "Subnet": subnet})
    if not subnet_id:
        raise CreError("subnet_id is required")
    return await c.post("lab/subnets", {"VpcId": vpc_id, "SubnetId": subnet_id, "Subnet": subnet})


@tool("write")
async def update_dhcp(
    ctx: Context, vpc_id: str, dhcp_options: dict[str, Any], vpn_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Set lab DHCP options ({"Domain": "corp.local", "DnsServers": ["10.10.1.10"]}) and VPN client
    params ({"Admin"|"User": {"Domains": [...], "DnsServers": [...]}}). See get_lab DhcpParams/VpnParams."""
    c = client(ctx)
    if vpn_params is None:
        vpn_params = (await c.post("lab/getdetails", {"vpcId": vpc_id})).get("VpnParams") or {}
    return await c.post("lab/dhcp", {"VpcId": vpc_id, "DhcpOptions": dhcp_options, "VpnParams": vpn_params})


@tool("write")
async def set_lab_app(
    ctx: Context,
    vpc_id: str,
    name: str,
    url: str,
    description: str = "",
    attacker: bool = True,
    app_id: str | None = None,
) -> dict[str, Any]:
    """Add (or with app_id, edit) a web app link shown on the lab (e.g. http://10.10.3.59:3000).
    attacker=true shows it to participants."""
    return await client(ctx).post("lab/apps", {
        "VpcId": vpc_id, "AppId": app_id, "Url": url, "AppName": name, "AppDesc": description, "Attacker": attacker,
    })


@tool("read")
async def connect_lab_app(ctx: Context, vpc_id: str, app_id: str) -> dict[str, Any]:
    """Get a browser connection URL for a lab app."""
    return await client(ctx).post("lab/apps/connect", {"VpcId": vpc_id, "AppId": app_id})
