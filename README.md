<p align="center">
  <img src="https://quickcall.dev/assets/v1/qc-full-512px-white.png" alt="QuickCall" width="400">
</p>

<h3 align="center">Eliminate interruptions for developers</h3>

<p align="center">
  <em>Ask about your work, get instant answers. No more context switching.</em>
</p>

<p align="center">
  <a href="https://quickcall.dev"><img src="https://img.shields.io/badge/Web-quickcall.dev-000000?logo=googlechrome&logoColor=white" alt="Web"></a>
  <a href="https://discord.gg/DtnMxuE35v"><img src="https://img.shields.io/badge/Discord-Join%20Us-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
</p>

<p align="center">
  <a href="#install">Install</a> |
  <a href="#capabilities">Capabilities</a> |
  <a href="#integrations">Integrations</a> |
  <a href="#authentication">Authentication</a> |
  <a href="#commands">Commands</a> |
  <a href="#troubleshooting">Troubleshooting</a>
</p>

---

## Install

### Claude Code

**In your terminal:**
```bash
claude mcp add quickcall -- uvx quickcall-integrations
```

**In Claude Code:**
```
/plugin marketplace add quickcall-dev/quickcall-integrations
```
```
/plugin enable quickcall
```

**Restart Claude Code**, then verify with `/mcp` and `/plugin list`.

### Cursor / Other IDEs

Add to MCP config (`~/.cursor/mcp.json` or `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "quickcall": {
      "command": "uvx",
      "args": ["quickcall-integrations"]
    }
  }
}
```

> Works with any IDE that supports MCP servers.

## Capabilities

- **Get standup updates** from git history (commits, diffs, stats)
- **List PRs, commits, branches** from GitHub repos
- **Read & send Slack messages** with auto thread fetching
- **Fuzzy channel matching** - say "no sleep dev" and it finds "no-sleep-dev-channel"
- **Summarize Slack channels** - get key discussions from last N days

## Integrations

| Integration | Features | Auth Required |
|-------------|----------|---------------|
| **Git** | Commits, diffs, standup summaries | No |
| **GitHub** | Repos, PRs, commits, branches | Yes |
| **Slack** | Read/send messages, threads, channels | Yes |

<details>
<summary><strong>Available Tools (24)</strong></summary>

### Git
| Tool | Description |
|------|-------------|
| `get_updates` | Get git commits, diff stats, and uncommitted changes |

### GitHub
| Tool | Description |
|------|-------------|
| `list_repos` | List accessible repositories |
| `list_prs` | List pull requests (open/closed/all) |
| `get_prs` | Get PR details (title, description, files changed) |
| `list_commits` | List commits with optional filters |
| `get_commit` | Get commit details (message, stats, files) |
| `list_branches` | List repository branches |
| `manage_issues` | List, view, create, update, close, reopen, comment on issues + sub-issues |
| `check_github_connection` | Verify GitHub connection |

### Slack
| Tool | Description |
|------|-------------|
| `list_slack_channels` | List channels bot has access to |
| `send_slack_message` | Send message to a channel |
| `read_slack_messages` | Read messages with threads auto-fetched |
| `read_slack_thread` | Read replies in a thread |
| `list_slack_users` | List workspace users |
| `check_slack_connection` | Verify Slack connection |
| `reconnect_slack` | Re-authorize to get new permissions |

### Auth
| Tool | Description |
|------|-------------|
| `connect_quickcall` | Start device flow authentication |
| `check_quickcall_status` | Check connection status |
| `disconnect_quickcall` | Remove local credentials |
| `connect_github` | Install GitHub App |
| `connect_slack` | Authorize Slack App |

### Utility
| Tool | Description |
|------|-------------|
| `get_current_datetime` | Get current UTC datetime |
| `calculate_date_range` | Calculate date range for queries |
| `calculate_date_offset` | Add/subtract time from a date |

</details>

## Authentication

### Option 1: QuickCall (Recommended)

To use GitHub and Slack integrations, connect your QuickCall account:

```
/quickcall:connect
```

This will guide you through:
1. Sign in with Google
2. Install GitHub App to your org/account
3. Connect Slack workspace

Credentials are stored locally in `~/.quickcall/credentials.json`.

### Option 2: GitHub PAT (For Enterprise Users)

If your organization can't install the QuickCall GitHub App (common at enterprises with strict app policies), you can use a Personal Access Token instead:

**Environment Variable:**
```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

**Or config file** (create `.quickcall.env` in your project root or home directory):
```bash
# .quickcall.env
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_USERNAME=your-username  # Optional: for better UX
```

**Create a PAT at:** https://github.com/settings/tokens

**Required scopes (classic PAT):**

| Scope | Used For |
|-------|----------|
| `project` | GitHub Projects access |
| `read:user` | Read user profile data |
| `repo` | PRs, commits, branches, issues |

**Note:** PAT mode provides access to GitHub tools only. For Slack integration, use QuickCall authentication.

## Commands

### Claude Code

| Command | Description |
|---------|-------------|
| `/quickcall:connect` | Connect QuickCall, GitHub, and Slack |
| `/quickcall:status` | Show connection status |
| `/quickcall:updates` | Get git updates (default: 1 day) |
| `/quickcall:updates 7d` | Get updates for last 7 days |
| `/quickcall:slack-summary` | Summarize Slack messages (default: 1 day) |
| `/quickcall:slack-summary 7d` | Summarize last 7 days |

### Cursor / Other IDEs

Ask the AI naturally - see examples below.

## Example Prompts

### Git
```
What did I work on today?
Give me a standup summary for the last 3 days
What changes are uncommitted?
```

### GitHub
```
List my repos
Show open PRs on [repo-name]
What commits were made this week?
Get details of PR #123
List branches on [repo-name]
```

### Slack
```
Send "Build completed" to #deployments
What messages were posted in dev channel today?
Read messages from no sleep dev (fuzzy matches "no-sleep-dev-channel")
Summarize what was discussed in #engineering this week
List channels I have access to
```

### Combined
```
List open PRs on [repo] and send titles to #updates channel
What did I work on this week? Send summary to #standup
```

## Issue Management

The `manage_issues` tool provides full issue lifecycle management:

### Actions

| Action | Description |
|--------|-------------|
| `list` | List issues with filters |
| `view` | View issue details |
| `create` | Create new issue (with optional template) |
| `update` | Update issue title/body/labels |
| `close` | Close issue(s) |
| `reopen` | Reopen issue(s) |
| `comment` | Add comment to issue(s) |
| `add_sub_issue` | Add child issue to parent |
| `remove_sub_issue` | Remove child from parent |
| `list_sub_issues` | List sub-issues of a parent |

### List Filters

| Filter | Description |
|--------|-------------|
| `state` | `'open'`, `'closed'`, or `'all'` (default: `'open'`) |
| `labels` | Filter by one or more labels |
| `assignees` | Filter by assignee |
| `creator` | Filter by issue creator username |
| `milestone` | Filter by milestone: number, title, `'*'` (any), or `'none'` |
| `sort` | Sort by: `'created'`, `'updated'`, or `'comments'` (default: `'updated'`) |
| `limit` | Max issues to return (default: 30) |

**Examples:**
```
List open issues in milestone v1.0
List issues created by sagar
Show closed bugs sorted by comments
List issues without a milestone
```

### Issue Templates

QuickCall supports issue templates from two sources:

**1. GitHub Native Templates** (`.github/ISSUE_TEMPLATE/*.yml`)

Standard GitHub issue templates are automatically detected:
```yaml
# .github/ISSUE_TEMPLATE/bug_report.yml
name: Bug Report
description: Report a bug
labels: [bug]
body:
  - type: textarea
    attributes:
      label: Description
```

**2. Custom Templates** (`.quickcall.env`)

Define custom templates in your project config:
```bash
# .quickcall.env
ISSUE_TEMPLATE_PATH=/path/to/templates.yml
```

```yaml
# templates.yml
bug_report:
  name: Bug Report
  description: Report a bug
  labels: [bug]
  title_prefix: "[BUG] "
  body: |
    ## Description

    ## Steps to Reproduce

    ## Expected Behavior

feature_request:
  name: Feature Request
  labels: [enhancement]
  body: |
    ## Problem

    ## Proposed Solution
```

**Usage:**
```
Create a bug report issue titled "Login fails on Safari"
Create issue with feature_request template
```

## Troubleshooting

### Clean Reinstall

If commands don't appear or aren't updating:

```bash
# Remove everything
rm -rf ~/.claude/plugins/cache/quickcall-integrations
rm -rf ~/.claude/plugins/marketplaces/quickcall-integrations
claude mcp remove quickcall
```

Then follow the [install steps](#claude-code) again.

### Commands Not Showing?

Type `/quickcall:` - you should see `connect`, `status`, `updates`. If not, do a clean reinstall above.

---

<p align="center">
  Built with ❤️ by <a href="https://quickcall.dev">QuickCall</a>
</p>
