# Testing QuickCall Integrations MCP Server

## Quick Test

### 1. Start the server

```bash
cd src && python server.py
```

### 2. Run the test

```bash
python tests/test_tools.py
```

## Using with Claude Code

### Add to Claude Code config

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "quickcall": {
      "command": "python",
      "args": ["/path/to/quickcall-mcp-server/src/server.py"],
      "env": {
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

Or for HTTP mode (run server separately):

```json
{
  "mcpServers": {
    "quickcall": {
      "url": "http://localhost:8001/mcp"
    }
  }
}
```

### Test in Claude Code

Once configured, try these prompts:

```
"What have I been working on today?"
"Show me my uncommitted changes"
"Summarize my work this week"
```

## Using MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

Then connect to `http://localhost:8001/mcp` and test the tools:
- `get_updates` - Shows uncommitted + committed changes
- `get_diff` - Shows detailed diffs
- `summarize_updates` - AI summary (needs OPENAI_API_KEY)

## Environment Variables

```bash
# Optional - for AI summaries
export OPENAI_API_KEY=your_key

# Server config (optional)
export MCP_HOST=0.0.0.0
export MCP_PORT=8001
export MCP_TRANSPORT=streamable-http  # or "stdio" for Claude Code
```
