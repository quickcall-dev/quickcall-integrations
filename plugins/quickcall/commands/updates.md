---
description: Get git updates. Usage: /quickcall:updates 7d (for 7 days)
---

# Git Updates

Get recent git updates for the user's current working directory.

## Arguments

Parse `$ARGUMENTS` for time period:
- `7d` → 7 days
- `30d` → 30 days
- No argument → default to 1 day

## Instructions

1. Use the `get_updates` tool from the quickcall MCP server
2. Pass the current working directory as the `path` parameter
3. Parse days from argument (e.g., "7d" → 7)
4. Summarize the changes:
   - Number of commits
   - Authors who contributed
   - Key changes (from commit messages and diff)
   - Uncommitted changes

## Output Format

Concise summary:
- "3 commits in last 7 days by Alice and Bob"
- "Main changes: Added auth flow, fixed login bug"
- "2 uncommitted files"
