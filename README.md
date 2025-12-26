# QuickCall Integrations

Integrate QuickCall into dev workflows - eliminate interruptions for developers. Ask about your work, get instant answers. No more context switching.

**Current integrations:**
- Git - commits, diffs, code changes

**Coming soon:**
- Calendar
- Slack
- GitHub PRs & Issues

## Install

Run these commands in [Claude Code](https://claude.ai/code):

```
/plugin marketplace add quickcall-dev/quickcall-integrations
/plugin install quickcall@quickcall-integrations
```

**MCP only (without plugin):**
```bash
claude mcp add quickcall -- uvx quickcall-integrations
```

## Update

To get the latest version:

```
/plugin marketplace update quickcall-integrations
/plugin uninstall quickcall
/plugin install quickcall@quickcall-integrations
```

**Note:** After updating, restart Claude Code or open a new terminal for changes to take effect.

## Commands

- `/quickcall:updates` - Get git updates (default: 1 day)
- `/quickcall:updates 7d` - Get updates for last 7 days
- `/quickcall:updates 30d` - Get updates for last 30 days

Or just ask Claude naturally:
- "What did I work on today?"
- "Show me recent commits"
- "What's changed in the last week?"

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