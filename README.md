# immersive-cre-mcp

MCP server for **Immersive Labs Cyber Ranges** (CRE), built for **range authors**.
It covers the whole dashboard: scenarios, flags (with answers), briefing and walkthrough markdown,
documents, templates, labs, systems, networking, snapshots, VPN, events and users.

> This uses the same public API the CRE web dashboard calls: any registered account can reach
> it by signing in. It isn't formally documented or versioned (see [docs/API.md](docs/API.md) for
> the endpoints as observed), so a dashboard release can change it.

# Installation

Requires Python 3.12+. Run it without installing via `uvx`, or install it with `pipx` or `pip`:

```bash
uvx immersive-cre-mcp            # run on demand, nothing to install
pipx install immersive-cre-mcp   # or install the command globally
pip install immersive-cre-mcp    # or into an existing environment
```

### From git

To use a version that isn't on PyPI, install straight from the repository. Add `@<ref>` to pin
a tag, branch or commit; leave it off to get the latest `main`.

```bash
uvx --from git+https://github.com/immersive-labs-innovation/immersive-cre-mcp@v0.1.0 immersive-cre-mcp
pipx install git+https://github.com/immersive-labs-innovation/immersive-cre-mcp@v0.1.0
pip install "immersive-cre-mcp @ git+https://github.com/immersive-labs-innovation/immersive-cre-mcp@<commit-sha>"
```

With `uvx`, pass the same `--from` in your client config (see [Add to a client](#add-to-a-client)):

```json
"command": "uvx",
"args": ["--from", "git+https://github.com/immersive-labs-innovation/immersive-cre-mcp@v0.1.0", "immersive-cre-mcp"]
```

`uvx` caches the build, so a pinned tag or commit is fetched only once. For a branch, add
`--refresh` to the `uvx` arguments to pick up new commits.

## Configuration

Settings are read from environment variables, so set them in your MCP client's config
(or in a `.env` file in the server's working directory).

| Variable | Default | |
|---|---|---|
| `IMMERSIVE_CRE_USERNAME` / `IMMERSIVE_CRE_PASSWORD` | – | Immersive Labs platform login (no API tokens exist) |
| `IMMERSIVE_CRE_BASE_URL` | `https://api4.eu.snaplabs.io` | Ranges API host |
| `IMMERSIVE_CRE_DASHBOARD_URL` | `https://dashboard.immersivelabs.eu.snaplabs.io` | Used for the OAuth state/referrer |
| `IMMERSIVE_CRE_TOKEN_CACHE` | `~/.cache/immersive-cre-mcp/token` | Session cookie cache (mode 0600); empty = memory only |
| `IMMERSIVE_CRE_READ_ONLY` | `false` | Only expose read tools |
| `IMMERSIVE_CRE_ENABLE_RAW` | `true` | Expose `raw_request` for endpoints without a tool |


## Add to a client

**Claude Code:**

```bash
claude mcp add immersive-cre \
  -e IMMERSIVE_CRE_USERNAME=you@example.com \
  -e IMMERSIVE_CRE_PASSWORD='...' \
  -- uvx immersive-cre-mcp
```

**Claude Desktop, Cursor, VS Code or any other MCP client** (JSON config):

```json
{
  "mcpServers": {
    "immersive-cre": {
      "command": "uvx",
      "args": ["immersive-cre-mcp"],
      "env": {
        "IMMERSIVE_CRE_USERNAME": "you@example.com",
        "IMMERSIVE_CRE_PASSWORD": "..."
      }
    }
  }
}
```

If you installed with `pipx` or `pip`, use `"command": "immersive-cre-mcp"` with no `args` instead.

Add `"IMMERSIVE_CRE_READ_ONLY": "true"` to `env` to explore safely without any write or delete tools.

The server also runs over HTTP with `immersive-cre-mcp --transport streamable-http`.

## Example usage

Once connected, ask your assistant in plain language. For example:

- *"List my scenarios and show the flags for the one called Ransomware Response."*
- *"Create a scenario called Phishing Triage with a short briefing, and add three flags:
  the sender's IP, the malicious domain, and the payload's SHA256."*
- *"Rewrite the student walkthrough for scenario 1234 to fix the typos and make step 3 clearer."*
- *"Reorder the flags in my Web App scenario so the easy ones come first, and add a hint to each."*
- *"In my AD Lab, add a DMZ subnet on 10.10.5.0/24 that accepts only TCP 80 and 443 from the
  attacker subnet, then add an Ubuntu web server on it at 10.10.5.10."*
- *"Give the web server a second interface on the internal subnet at 10.10.1.50 so it can reach
  the domain controller."*
- *"Lock down the internal subnet: allow RDP and SMB from the user subnet only and drop
  everything else inbound."*
- *"Set the lab's DHCP domain to corp.local with 10.10.1.10 as the DNS server, and push the same
  DNS settings to VPN users."*
- *"Add the Juice Shop on 10.10.3.59:3000 as an app participants can open from the lab page."*
- *"Which labs are running right now, and when do they shut down?"*
- *"Upload `network-diagram.pdf` as a document on the Phishing Triage scenario."*
- *"Show the scoreboard for event 42."*

## Tools (88)

| Area | Tools |
|---|---|
| Scenarios | `list_scenarios` `get_scenario` `create_scenario` `update_scenario` `publish_scenario` `delete_scenario` `set_scenario_image` `set_scenario_suggested_labs` `search_immersive_labs` |
| Flags (scenario or event) | `list_flags` `add_flag` `update_flag` `delete_flag` `reorder_flags` `replace_flags` |
| Markdown & documents | `get_markdown` `set_markdown` `delete_admin_markdown` `list_documents` `upload_document` `download_document` `delete_document` |
| Templates | `list_templates` `get_template` `create_template_from_lab` `edit_template` `share_template` `revoke_template_share` `delete_template` |
| Labs | `list_labs` `get_lab` `launch_lab` `launch_blank_lab` `launch_introductory_range` `wait_for_lab` `power_lab` `update_lab_settings` `delete_lab` `checkin` `get_lab_users` `manage_lab_users` `cache_lab_credentials` `download_lab_ssh_key` `get_launch_script_output` |
| Snapshots & VPN | `create_snapshot` `revert_snapshot` `delete_snapshot` `create_vpn` `download_vpn` `revoke_vpn` |
| Systems | `add_system` `update_system` `delete_system` `manage_system_interface` `get_system_console` `set_system_credentials` `create_image_from_system` `list_images` `get_image_info` `get_instance_pricing` `validate_ami` `get_playbook` `run_playbook` `get_playbook_jobs` |
| Network & apps | `manage_subnet` `update_dhcp` `set_lab_app` `connect_lab_app` |
| Events | `list_events` `get_event` `list_event_teams` `create_event` `update_event` `set_event_image` `delete_event` `manage_event_team` `manage_event_participant` `launch_event_lab` `get_event_scores` `submit_flag` |
| Account & users | `get_account` `list_users` `get_user` `invite_users` `update_user` `remove_users` `reinvite_user` `raw_request` |

Tools are annotated read / write / destructive, so clients can prompt before destructive calls.

Authoring notes:
- **Flags**: the API only saves the whole list. The flag tools read, modify and write it back, and
  generate `FlagId`s for new flags. Answers, hints and MITRE tags are always returned.
- **Markdown**: `set_markdown` uploads to S3, then waits (up to 30s) for the backend to register
  the new version, so a read straight after a write is current.
- **Costs**: launching or powering labs spends AWS money and counts against the account's lab limit.

# Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/immersive-labs-innovation/immersive-cre-mcp.git
cd immersive-cre-mcp
uv sync
cp .env.example .env   # then fill in credentials
```

A `.env` in the project root is picked up whatever the working directory, so a client can run
your checkout directly:

```bash
claude mcp add immersive-cre -- uv run --project /path/to/immersive-cre-mcp immersive-cre-mcp
```

```json
{"mcpServers": {"immersive-cre": {"command": "uv", "args": ["run", "--project", "/path/to/immersive-cre-mcp", "immersive-cre-mcp"]}}}
```

To try tools interactively, use the MCP Inspector: `npx @modelcontextprotocol/inspector uv run immersive-cre-mcp`.
Set `LOG_LEVEL=DEBUG` for more logging.

## Test status

These were exercised against the test account over MCP stdio, using a throwaway scenario that was
deleted afterwards: all read tools, scenario create/update/delete, every flag operation,
student/admin markdown write and read, and document upload/list/download/delete.

These are wired to the payloads in the dashboard bundle but have **not been run**, because they
launch, alter or delete real labs and users: lab launch/power/delete, snapshots, VPN, systems,
subnets, apps, events (write), user management, template create/share/delete, publishing, and images.

## Layout

```
src/immersive_cre_mcp/
  client.py      auth (IL → Hydra OAuth → token cookie), GET/POST transport, S3 upload/download
  config.py      settings (environment / .env)
  app.py         MCPServer instance, tool() decorator, shared helpers
  server.py      entry point (immersive-cre-mcp)
  tools/         one module per area (scenarios, flags, content, templates, labs, systems, events, account)
docs/API.md      endpoint reference (as observed from the dashboard)
```
