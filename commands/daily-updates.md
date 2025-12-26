---
description: Get git updates for current repository (commits, diffs, changes)
---

# Daily Updates

Get the recent git updates for the user's current working directory.

## Instructions

1. Use the `get_updates` tool from the quickcall MCP server
2. Pass the current working directory as the `path` parameter
3. Default to 1 day of history (or use the number the user specifies)
4. Summarize the changes in a clear format:
   - Number of commits
   - Authors who contributed
   - Key changes made (based on commit messages and diff)
   - Any uncommitted changes

## Output Format

Provide a concise summary like:
- "3 commits today by Alice and Bob"
- "Main changes: Added auth flow, fixed login bug"
- "You have 2 uncommitted files"
