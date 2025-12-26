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

```
/plugin marketplace update quickcall-integrations
/plugin update quickcall
```

## Commands

- `/quickcall:daily-updates` - Get git updates for current repo

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
