<p align="center">
  <img src="assets/logo.png" alt="QuickCall" width="400">
</p>

<h3 align="center">Eliminate interruptions for developers</h3>

<p align="center">
  <em>Ask about your work, get instant answers. No more context switching.</em>
</p>

<p align="center">
  <a href="#claude-code">Claude Code</a> |
  <a href="#cursor">Cursor</a> |
  <a href="#commands">Commands</a> |
  <a href="#development">Development</a>
</p>

---

**Current integrations:**
- Git - commits, diffs, code changes

**Coming soon:**
- Calendar
- Slack
- GitHub PRs & Issues

## Install

### Claude Code

Run these commands in [Claude Code](https://claude.ai/code):

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

## Commands

### Claude Code

- `/quickcall:updates` - Get git updates (default: 1 day)
- `/quickcall:updates 7d` - Get updates for last 7 days
- `/quickcall:updates 30d` - Get updates for last 30 days

### Cursor

Ask the AI naturally - it will use the `get_updates` tool:
- "What did I work on today?"
- "Show me recent commits"
- "What changed in the last week?"


## Development

```bash
git clone https://github.com/quickcall-dev/quickcall-integrations
cd quickcall-integrations
uv pip install -e .
quickcall-integrations
```
## Deployment

It only triggers on:

- Tags starting with v* (e.g., v0.1.0)
- Manual trigger (workflow_dispatch)

To publish to PyPI:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Or trigger manually from GitHub Actions page.
