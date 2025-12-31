<p align="center">
  <img src="assets/logo.png" alt="QuickCall" width="400">
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
  <a href="#integrations">Integrations</a> |
  <a href="#install">Install</a> |
  <a href="#authentication">Authentication</a> |
  <a href="#commands">Commands</a>
</p>

---

## Integrations

- **Git** - commits, diffs, code changes (always available)
- **GitHub** - repos, PRs, commits, branches (requires QuickCall account)
- **Slack** - send messages, list channels/users (requires QuickCall account)

## Install

### Claude Code

```
/plugin marketplace add quickcall-dev/quickcall-integrations
/plugin install quickcall@quickcall-integrations
```

<details>
<summary>MCP only (without plugin)</summary>

```bash
claude mcp add quickcall -- uvx quickcall-integrations
```
</details>

<details>
<summary>Update to latest version</summary>

```
/plugin marketplace update quickcall-integrations
/plugin uninstall quickcall
/plugin install quickcall@quickcall-integrations
```

After updating, restart Claude Code or open a new terminal.
</details>

### Cursor

Add to your Cursor MCP config (`~/.cursor/mcp.json` for global, or `.cursor/mcp.json` for project):

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

Then restart Cursor.

> Also works with [Antigravity](https://antigravity.dev) and any other IDE that supports MCP servers.

## Authentication

To use GitHub and Slack integrations, connect your QuickCall account:

```
/quickcall:connect
```

This will guide you through:
1. Sign in with Google
2. Install GitHub App to your org/account
3. Connect Slack workspace

Credentials are stored locally in `~/.quickcall/credentials.json`.

## Commands

### Claude Code

| Command | Description |
|---------|-------------|
| `/quickcall:connect` | Connect QuickCall, GitHub, and Slack |
| `/quickcall:status` | Show connection status |
| `/quickcall:updates` | Get git updates (default: 1 day) |
| `/quickcall:updates 7d` | Get updates for last 7 days |

### Cursor / Other IDEs

Ask the AI naturally:
- "What did I work on today?"
- "Show me my open PRs"
- "List my GitHub repos"
- "Send a message to #general on Slack"

---

<p align="center">
  Built with ❤️ by <a href="https://quickcall.dev">QuickCall</a>
</p>
