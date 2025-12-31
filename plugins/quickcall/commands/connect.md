---
description: Connect QuickCall, GitHub, and Slack integrations
---

# Connect Integrations

Guide the user through connecting their integrations.

## Instructions

1. First, call `check_quickcall_status` to see current connection status

2. Based on status, guide user through connecting:

   **If not connected to QuickCall:**
   - Call `connect_quickcall` to start device flow auth
   - Wait for user to complete browser sign-in
   - Call `complete_quickcall_auth` with the device code

   **If QuickCall connected but GitHub not connected:**
   - Ask if user wants to connect GitHub
   - If yes, call `connect_github` to open GitHub App installation

   **If QuickCall connected but Slack not connected:**
   - Ask if user wants to connect Slack
   - If yes, call `connect_slack` to open Slack OAuth

3. After each connection, show updated status

## Output Format

Show a clear summary:
```
QuickCall: Connected
GitHub: Connected (username)
Slack: Connected (workspace)
```
