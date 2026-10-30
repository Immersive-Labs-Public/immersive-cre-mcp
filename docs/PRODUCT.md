# Immersive CRE MCP: Product Overview

## What it is
An MCP server that connects any AI assistant (Claude Code, Claude Desktop, Cursor, VS Code) to **immersive Cyber Ranges**. It covers everything the CRE dashboard can do (88 tools), and it also gives an agent what it needs to **get inside the range**: a VPN into the lab network, the lab's SSH key, the system logins and the platform's playbooks.

So an agent doesn't just draw the network. It can log on to the machines it built, install and configure software, set up the vulnerable services and hidden evidence, check that the exercise works, and then save the finished environment as a reusable template.

## The problem
Building a range has two layers, and both are slow:

1. **The range wrapper.** Subnets, firewall rules, systems, IPs, DNS, snapshots, VPN configs and templates, all set up by clicking through the dashboard.
2. **The environment inside it.** Domain controllers, joined workstations, users and groups, web apps, misconfigurations, planted logs and artefacts. This means logging on to each box by hand, running scripts, checking the result and starting over when something breaks.

Most of the time goes into the second layer, and none of it can be scripted from the dashboard.

## What it enables

### 1. Get inside the machines
Once the MCP server provides the access below, an agent with a shell (such as Claude Code) can work on the systems directly:

- **Network access:** issue an **admin VPN** config that reaches every subnet in the lab and save it to disk. The agent connects with its own OpenVPN client.
- **Credentials:** download the lab's **SSH private key**, read each system's console logins, and save logins for every system in one call.
- **Remote work over the VPN:** the agent then uses SSH, WinRM/PowerShell or its own Ansible to run commands and scripts on any system, including copying files and changing settings.
- **Browser console** (Guacamole RDP/SSH/VNC) for any system, as a fallback or for a human to check the work.

### 2. Install and configure whole environments
- **Platform playbooks:** run the Ansible playbooks the platform offers on any system, and check job status and output.
- **Build anything else:** for example, promote a domain controller, create OUs, users and groups, join workstations, install IIS, Apache or a vulnerable web app, set up services, and deploy EDR/SIEM agents or log forwarders.
- **Plant the scenario:** add the misconfigurations, weak credentials, persistence, phishing emails and log artefacts the exercise depends on.
- **Debug launches:** read the output of a template's launch scripts to see why a box didn't come up properly.

> *"Connect to the AD Lab over VPN, promote DC01 to a domain controller for corp.local, create 50 users across Sales, IT and Finance, give svc_backup a weak password and an SPN, and join WS01 and WS02 to the domain."*

### 3. Check the exercise actually works
- **Test it like a participant:** connect with a *user* VPN (attacker pool only) and confirm the intended attack path works and the off-limits systems really can't be reached.
- **Check every flag:** for each answer, confirm it can be found on the box where the walkthrough says it is.
- **Dynamic flags:** create flags whose answers are generated at launch by a PowerShell or SSH script on a system, so each participant gets a different answer.

### 4. Iterate safely, then freeze it
- **Snapshot before every risky change** (single system or the whole lab), and roll back after a broken install instead of rebuilding.
- **Save as a custom image:** turn a fully configured system into a reusable image (with its lab apps).
- **Save as a template:** capture the whole lab (systems, network and apps) in one step, then share it with specific accounts or make it public.

### 5. Describe the network and get it built
- Create subnets with their CIDR ranges and inbound and outbound rules: *"Add a DMZ on 10.10.5.0/24 that only accepts TCP 80/443 from the attacker subnet."*
- Connect systems to more than one network, set fixed IPs, and set the DHCP domain and DNS (including for VPN users).
- Add systems from base images, custom images or your own validated AMIs. Resize them using live pricing, and mark which box is the participant's attacker machine.

### 6. Run the lab
- Launch from a template, a scenario, a blank network or the built-in AD "Introductory Range". The assistant waits until the lab is ready before carrying on.
- Power the whole lab or single systems on and off, and keep the idle auto-off timer from shutting labs down while you work.
- Manage which users can access each lab, publish lab apps (e.g. *Juice Shop on 10.10.3.59:3000*), and issue or revoke VPN configs for participants.

### 7. Write and run the exercise
- Create and publish scenarios, write the briefing and walkthrough, and attach documents.
- Manage flags (answers, hints, MITRE ATT&CK tags, ordering) in bulk.
- Run live events: teams, participants, event labs and scoreboards.

## Example: from nothing to a published exercise
> "Launch a blank lab with attacker, DMZ and corp subnets. Add a Windows Server DC at 10.10.1.10 and two Windows 10 workstations, plus an Ubuntu web server in the DMZ that only allows 80/443 from the attacker subnet. Snapshot everything. Connect over the admin VPN, build the corp.local domain with users, join the workstations, deploy a vulnerable app on the web server with credentials that work on WS01, and plant the flags. Test the attack path from the attacker VPN, fix anything that doesn't work, then save it as the *Web to Domain v1* template and attach it to a new scenario with a walkthrough."

## Safety and control
- **Read-only mode** (`IMMERSIVE_CRE_READ_ONLY=true`) exposes only tools that look and never change anything. Use it for safe exploring.
- Every tool is marked as **read**, **write** or **destructive**, so the assistant's client can ask for confirmation before deleting, rolling back or launching.
- VPN configs and SSH keys are written to disk with owner-only permissions (0600). VPN configs can be revoked once the build is done.
- No API tokens exist: it signs in with the user's own platform login, so it gets that user's permissions, and the session is cached with owner-only file permissions.
- `raw_request` can reach any endpoint that doesn't have its own tool yet (can be turned off).

## Current status and caveats
- **Tested end to end against a real account:** all read tools, scenario create/update/delete, every flag operation, markdown, and documents.
- **Built but not yet run against a live account:** lab launch, power and delete; snapshots; VPN; SSH keys; systems; playbooks; subnets; apps; templates; images; event writes; and user management. The request formats were copied from the dashboard's own code, but these steps need checking before anyone relies on them. That includes the whole "get inside the machines" path.
- **Hands-on work happens in the agent's own environment.** The MCP server provides the access (VPN, key, logins) but doesn't run commands on systems itself, except through platform playbooks. The agent's machine needs an OpenVPN client (usually run with root/sudo) plus SSH and WinRM tools.
- The admin VPN needs the lab's AdminBox to be running.
- It uses the same API the dashboard calls, which isn't documented or versioned. A dashboard release could break tools.
- Launching or powering labs costs AWS money and counts against the account's lab limit.

## Getting started
```bash
claude mcp add immersive-cre -e IMMERSIVE_CRE_USERNAME=you@example.com \
  -e IMMERSIVE_CRE_PASSWORD='...' -- uvx immersive-cre-mcp
```

See the [README](../README.md) for installation, configuration and the full tool list, and [API.md](API.md) for the endpoint reference.

## Annex: Tool list

| Area | Count | Tools |
|---|---|---|
| Scenarios | 9 | list_scenarios, get_scenario, create_scenario, update_scenario, publish_scenario, delete_scenario, set_scenario_image, set_scenario_suggested_labs, search_immersive_labs |
| Flags (scenario or event) | 6 | list_flags, add_flag, update_flag, delete_flag, reorder_flags, replace_flags |
| Markdown & documents | 7 | get_markdown, set_markdown, delete_admin_markdown, list_documents, upload_document, download_document, delete_document |
| Templates | 7 | list_templates, get_template, create_template_from_lab, edit_template, share_template, revoke_template_share, delete_template |
| Labs | 15 | list_labs, get_lab, launch_lab, launch_blank_lab, launch_introductory_range, wait_for_lab, power_lab, update_lab_settings, delete_lab, checkin, get_lab_users, manage_lab_users, cache_lab_credentials, download_lab_ssh_key, get_launch_script_output |
| Snapshots & VPN | 6 | create_snapshot, revert_snapshot, delete_snapshot, create_vpn, download_vpn, revoke_vpn |
| Systems | 14 | add_system, update_system, delete_system, manage_system_interface, get_system_console, set_system_credentials, create_image_from_system, list_images, get_image_info, get_instance_pricing, validate_ami, get_playbook, run_playbook, get_playbook_jobs |
| Network & apps | 4 | manage_subnet, update_dhcp, set_lab_app, connect_lab_app |
| Events | 12 | list_events, get_event, list_event_teams, create_event, update_event, set_event_image, delete_event, manage_event_team, manage_event_participant, launch_event_lab, get_event_scores, submit_flag |
| Account & users | 8 | get_account, list_users, get_user, invite_users, update_user, remove_users, reinvite_user, raw_request |
| **Total** | **88** | |
