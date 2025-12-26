# QuickCall Integrations

Developer integrations for Claude Code and Cursor.

**Current integrations:**
- Git - commits, diffs, code changes

**Coming soon:**
- Calendar
- Slack
- GitHub PRs & Issues

## Install

**Plugin (recommended):**
```bash
/plugin marketplace add quickcall-dev/quickcall-integrations
/plugin install quickcall@quickcall-integrations
```

**MCP only:**
```bash
claude mcp add quickcall -- uvx quickcall-integrations
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
