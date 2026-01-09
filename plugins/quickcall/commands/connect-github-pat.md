---
description: Connect GitHub using a Personal Access Token (for enterprise users)
---

# Connect GitHub via PAT

Use this if your organization can't install the QuickCall GitHub App.

## Steps

1. **Check if PAT already configured:**
   - Call `check_quickcall_status`
   - If `github_pat.configured` is true, inform user and ask if they want to reconnect

2. **Get PAT from user:**
   - Ask user for their GitHub Personal Access Token
   - Remind them: "Create a PAT at https://github.com/settings/tokens with `repo` scope"

3. **Connect:**
   - Call `connect_github_via_pat` with the provided token
   - The tool validates the token and auto-detects username

4. **Show result:**
   ```
   GitHub connected via PAT!
   Username: {username}
   Mode: Personal Access Token
   ```

## Notes

- PAT mode works independently of QuickCall
- Slack tools still require QuickCall authentication (`/quickcall:connect`)
- To disconnect PAT: call `disconnect_github_pat`
