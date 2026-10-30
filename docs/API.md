# CRE ranges API reference

The API is public (any registered account can sign in and use it) but not formally documented
or versioned. This reference was compiled from the calls the CRE dashboard
(`dashboard.immersivelabs.eu.snaplabs.io`, bundle `assets/index-*.js`) uses against
`https://api4.eu.snaplabs.io/ranges/`, extracted 2026-10-12. **It can change without notice.**
To re-extract after a dashboard release, pull the bundle and look for the API object that maps
names like `updateScenarioFlags` to helpers (`Be(path)` = GET, `w(path, body)` = POST).

- Auth: `token` cookie from the immersive → Hydra OAuth flow (see `src/immersive_cre_mcp/client.py`).
  Standalone CRE accounts (not platform users) sign in to the `dashboard.eu.snaplabs.io` Cognito pool
  instead and call the same endpoints at `https://api.eu.snaplabs.io/main/<path>` (US: `api2.snaplabs.io`)
  with the Cognito ID token as the `Authorization` header (see `src/immersive_cre_mcp/cognito.py`).
- Most responses carry `"result": "success"`, or `"result": "error"` + `message` with HTTP 200.
- Uploads (`docs/update`) return `{UrlData: {url, fields}, ID}`, a pre-signed S3 POST. The file is
  posted as multipart `fields` + `file`. Markdown is registered asynchronously (~5s).
- Download/markdown URLs are pre-signed S3 GETs that expire after ~30s.

The **Tool** column names the MCP tool that wraps each call. ✓ = exercised live against the test account.

## Account & users
| Dashboard fn | Call | Body | Tool |
|---|---|---|---|
| getStaticUserInfo | GET `staticuserinfo` | – | `get_account` ✓ |
| activityCheckin | POST `checkin` | `{IdleTime}` | `checkin` |
| users / searchUsers | POST `users` | `{hideManagers}` / `{searchTerm,hideManagers}` | `list_users` ✓ |
| inviteUsers | POST `users` | `{emails,asCreators,asManagers,permissions:[{vpcId,permission}]}` | `invite_users` |
| addSSOUsers | POST `users` | `{userIds,asCreators,permissions}` | raw |
| inviteUsersToRange | POST `users` | `{emails,permissions,updateExistingUserPermissions:true}` | raw |
| removeUsers | POST `users` | `{delete:true,userIds}` | `remove_users` |
| reinvite | POST `users/reinvite` | `{UserId}` | `reinvite_user` |
| getUser | POST `v2/users/getUser` | `{userId}` | `get_user` |
| updateUser | POST `v2/users/update` | `{userId,asCreator,name,asManager,ranges}` | `update_user` |
| updateOwnName | POST `profile/update` | `{Name}` | raw |
| detachAws / deleteAccount | POST `account/detach` / `account/delete` | `{}` | (deliberately not wrapped) |

## Scenarios
| Dashboard fn | Call | Body | Tool |
|---|---|---|---|
| listScenarios | GET `scenarios` | – | `list_scenarios` ✓ |
| getScenarioDetails | POST `scenarios/getdetails` | `{ScenarioId}` | `get_scenario` ✓ |
| createScenario | POST `scenarios/create` | `{Name,Description,SourceScenarioId?}` → `{ScenarioId}` | `create_scenario` ✓ |
| updateScenario | POST `scenarios/update` | `{ScenarioId,Name,Description,TemplateId,ScenarioType,Difficulty,ParticipantSystemId,KeyTakeaways(string),ContainsMalware}` | `update_scenario` ✓ |
| updateScenarioSuggestedLabs | POST `scenarios/update` | `{ScenarioId,SuggestedLabIds}` | `set_scenario_suggested_labs` |
| updateScenarioFlags | POST `scenarios/updateflags` | `{ScenarioId,Flags}` (full list) | flag tools ✓ |
| updateScenarioImage | POST `scenarios/updateimg` | `{ScenarioId,ImageType:<ext>,ImageData:<base64>}` (≤2MB) | `set_scenario_image` |
| publishScenario | POST `scenarios/publish` | `{ScenarioId,Unpublish}` | `publish_scenario` |
| deleteScenario | POST `scenarios/delete` | `{ScenarioId}` | `delete_scenario` ✓ |
| searchImmersiveLabs | POST `scenarios/labs` | `{searchTerm}` | `search_immersive_labs` (needs the suggestedLabs feature) |

### Flag object
```json
{"FlagId": "<uuid, client-generated>", "Name": "...", "Value": 10, "CorrectAnswers": ["..."],
 "Hint": "...", "Tags": ["T1110"], "Dynamic": true,
 "DynamicConfig": {"System": "<system IP>", "ScriptType": "powershell|ssh", "Script": "...",
                   "Credentials": {"Username": "...", "Password": "..."}}}
```
Some older scenarios carry a `Flag` field instead of / as well as `CorrectAnswers`; edits preserve it.

## Content (markdown & documents)
Target keys: `{VpcId, EventId, ScenarioId, TemplateId}`. Set the one that owns the content.

| Dashboard fn | Body (+ target) | Tool |
|---|---|---|
| getMdUploadUrl | `{StudentMarkdown,AdminMarkdown}` → UrlData, ID | `set_markdown` ✓ |
| initAdminMd | `{AdminMarkdown:true,Init:true}` | `set_markdown` (auto) ✓ |
| deleteAdminMd | `{AdminMarkdown:true,Delete:true}` | `delete_admin_markdown` |
| getUploadUrl | `{FileName,Name,Access:admin\|student,Description}` → UrlData, ID | `upload_document` ✓ |
| downloadFile | POST `docs/download` `{ID}` → `{url}` | `download_document` ✓ |
| deleteFile | `{ID,Delete:true}` | `delete_document` ✓ |

## Templates
| Dashboard fn | Call | Body | Tool |
|---|---|---|---|
| listTemplates | GET `templates` | – | `list_templates` ✓ |
| getTemplateInfo | POST `templates/getdetails` | `{TemplateId}` | `get_template` ✓ |
| templateLab | POST `templates/new` | `{VpcId,TemplateName,TemplateDesc}` | `create_template_from_lab` |
| editTemplate | POST `templates/edit` | `{templateId,name,description}` | `edit_template` |
| shareTemplate | POST `templates/share` | `{templateId,isPublic}` or `{templateId,shareWith}` | `share_template` |
| revokeTemplateAccess | POST `templates/share/revoke` | `{templateId,email}` | `revoke_template_share` |
| oldShareTemplate | POST `templates/share_old` | `{TemplateId,Shared}` | raw |
| deleteTemplate | POST `templates/delete` | `{templateId}` | `delete_template` |

## Labs
| Dashboard fn | Call | Body | Tool |
|---|---|---|---|
| listLabs | GET `labs` | – | `list_labs` ✓ |
| getLabDetails | POST `lab/getdetails` | `{vpcId}` or `{EventId}` | `get_lab` ✓ |
| launchLab | POST `lab/launch` | `{LabId:<TemplateId>,Name,Description}` → `{VpcId}` | `launch_lab` |
| launchNewLab | POST `lab/launch` | `{Name,Description,Cidr,Subnets:[{cidr,name}],AttackerInterface}` | `launch_blank_lab` |
| launchIntroductoryLab | POST `lab/launch` | `{Name,type:"introductoryRange",Variables:{domain_name}}` | `launch_introductory_range` |
| powerOn/Off/rebootLab | POST `lab/power` | `{VpcId,Power:on\|off\|reboot}` | `power_lab` |
| powerOn/Off/rebootSystem | POST `lab/power` | `{VpcId,InstanceIds,Power}` | `power_lab` |
| updateLabSettings | POST `lab/settings` | `{VpcId,Name,Description,AutoOff}` | `update_lab_settings` |
| deleteLab / forceDeleteLab | POST `lab/delete` / `lab/delete/force` | `{vpcId}` | `delete_lab` |
| getRangePermissions | POST `lab/permissions` | `{vpcId}` | `get_lab_users` ✓ |
| addUsersToRange | POST `lab/permissions` | `{vpcId,userIds,permission:view\|edit\|limited,updateExistingUserPermissions:true}` | `manage_lab_users` |
| updateUserRangePermission | POST `lab/permissions` | `{vpcId,userId,permission}` | `manage_lab_users` |
| deleteUserFromRange | POST `lab/permissions` | `{vpcId,userId,delete:true}` | `manage_lab_users` |
| cacheCreds | POST `lab/cachecreds` | `{VpcId}` | `cache_lab_credentials` |
| downloadSshKey | POST `lab/sshkey` | `{VpcId,Type}` | `download_lab_ssh_key` |
| getScriptOutput | POST `lab/scripts/output` | `{VpcId,ScriptId}` | `get_launch_script_output` |
| take(FullLab)Snapshot(s) | POST `lab/snapshots/new` | `{VpcId,CustomerName,InstanceIds?}` | `create_snapshot` |
| revertInstance / revertFullLab | POST `lab/snapshots/revert` | `{VpcId,SnapId,InstanceId?}` | `revert_snapshot` |
| deleteSnapshot / deleteFullLabSnapshot | POST `lab/snapshots/delete` / `deletef` | `{VpcId,SnapId,InstanceId}` / `{VpcId,SnapId}` | `delete_snapshot` |
| createVpnConfig | POST `lab/vpn/new` | `{vpcId,certType:UNIX\|WINDOWS,custName,certAccess:user\|admin}` → `{UUID}` | `create_vpn` |
| downloadVpnConfig | POST `lab/vpn/download` | `{UUID,vpcId}` → `{config:<base64>}` | `download_vpn` |
| revokeVpnConfig | POST `lab/vpn/revoke` | `{UUID,vpcId}` | `revoke_vpn` |

## Systems, images, network
| Dashboard fn | Call | Body | Tool |
|---|---|---|---|
| addSystem | POST `lab/systems/add` | `{VpcId,ImageId?,ImageAmi?,Name,Hostname,Type,DiskSize,SubnetId,IpAddress}` | `add_system` |
| deleteSystem | POST `lab/systems/delete` | `{VpcId,InstanceId}` | `delete_system` |
| updateSystemInfo | POST `lab/systems/info` | `{VpcId,InstanceId,Name,Hostname,Attacker}` | `update_system` |
| updateSystemType / Disk | POST `lab/systems/specs` | `{VpcId,InstanceId,Type}` / `{…,DiskSize}` | `update_system` |
| updateSystemNetwork | POST `lab/systems/network` | `{VpcId,InstanceId,SubnetId,IpAddress}` / `{…,Delete:true}` | `manage_system_interface` |
| getConsoleUrl | POST `lab/systems/console` | `{InstanceId,VpcId}` | `get_system_console` |
| updateConsoleCreds / updateCachedCreds | POST `lab/systems/creds` | `{VpcId,InstanceId,Console:{…}}` / `{…,Cached:[…]}` | `set_system_credentials` |
| customImage | POST `lab/systems/image` | `{VpcId,InstanceId,Name,Description,AppIds}` | `create_image_from_system` |
| getAvailableImages | POST `getimages` | `{}` | `list_images` ✓ |
| getImageInfo | POST `getimages` | `{VpcId,ImageId}` | `get_image_info` |
| getInstancePricing | POST `getimages` | `{VpcId,InstanceId}` | `get_instance_pricing` |
| validateAmi | POST `lab/validateami` | `{AMI}` | `validate_ami` |
| addSubnet / updateSubnet / deleteSubnet | POST `lab/subnets` | `{VpcId,Subnet}` / `{VpcId,SubnetId,Subnet}` / `{VpcId,SubnetId,Delete:true}` | `manage_subnet` |
| updateDhcp | POST `lab/dhcp` | `{VpcId,DhcpOptions,VpnParams}` | `update_dhcp` |
| updateLabApp | POST `lab/apps` | `{VpcId,AppId?,Url,AppName,AppDesc,Attacker}` | `set_lab_app` |
| appConnect | POST `lab/apps/connect` | `{VpcId,AppId}` | `connect_lab_app` |
| getPlaybook | GET `playbook/<id>` | – | `get_playbook` |
| runPlaybook | POST `playbook/<id>/run` | `{instanceId,vpcId}` | `run_playbook` |
| getPlaybookJobs | GET `labs/<vpcId>/systems/<instanceId>/playbook-jobs` | – | `get_playbook_jobs` |

Subnet object: `{Name, Description, Cidr, Inbound:[rule], Outbound:[rule]}`, rule
`{ipRange, protocol:"-1"|tcp|udp|icmp, fromPort, toPort, description}`.
Console credential: `{Protocol: RDP|SSH|VNC, Username, Password, Port, Domain, DisableFT, DisableCopy, DisablePaste, SftpPort, SftpPassword}`.

## Events
| Dashboard fn | Call | Body | Tool |
|---|---|---|---|
| listEvents | GET `events` | – | `list_events` ✓ |
| getEventDetails | POST `events/getdetails` | `{EventId}` | `get_event` |
| getEventTeams | GET `events/<id>/teams?page=&pageSize=&search=` | – | `list_event_teams` |
| createEvent | POST `events/create` | `{Name,Description,StartTime,EndTime,LabCleanupDelay,SourceEventId}` | `create_event` |
| updateEvent | POST `events/update` | `{EventId,Name,Description,StartTime,EndTime,TemplateId,LabCleanupDelay,PrivateScoring}` | `update_event` |
| updateEventImage | POST `events/updateimg` | `{EventId,ImageType,ImageData}` | `set_event_image` |
| updateEventFlags | POST `events/updateflags` | `{EventId,Flags}` | flag tools (`event_id=`) |
| deleteEvent | POST `events/delete` | `{EventId}` | `delete_event` |
| add/update/deleteTeam | POST `events/participants` | `{AddTeam\|UpdateTeam\|DeleteTeam:true,EventId,TeamId?,Name?}` | `manage_event_team` |
| add/update/deleteParticipant | POST `events/participants` | `{AddParticipant\|UpdateParticipant\|DeleteParticipant:true,EventId,TeamId,UserId,Email?}` | `manage_event_participant` |
| launchEventLab / relaunchEventLab | POST `lab/eventlaunch` | `{TeamId,RelaunchFromLatest?}` | `launch_event_lab` |
| getScores | POST `lab/scoring` | `{EventId,Admin}` | `get_event_scores` |
| submitFlag | POST `lab/scoring` | `{EventId,Flag}` | `submit_flag` |
