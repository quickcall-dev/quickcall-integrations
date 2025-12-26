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

## Output Format (Standup Style)

Format the response for a standup meeting:

### Summary
One sentence executive summary of what was accomplished.

### What I worked on
- Bullet points of key changes (group related commits)
- Focus on features/fixes, not individual commits
- Use past tense action verbs

### In Progress
- Any uncommitted changes (what's being worked on now)

### Blockers
- Only mention if there are merge conflicts or issues visible in the data

---

Example output:

**Summary:** Built and shipped the QuickCall plugin with MCP server integration.

**What I worked on:**
- Set up plugin marketplace structure for distribution
- Implemented git updates command with configurable time range
- Fixed MCP configuration and install instructions

**In Progress:**
- Updating command output format

**Blockers:** None
