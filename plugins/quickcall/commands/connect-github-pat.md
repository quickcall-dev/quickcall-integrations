---
description: Connect GitHub using a Personal Access Token (for enterprise users)
---

# Connect GitHub via PAT

Use this if your organization can't install the QuickCall GitHub App.

## Steps

1. **Check if PAT already configured:**
   - Call `check_quickcall_status`
   - If `github_pat.configured` is true, inform user and ask if they want to reconnect

2. **Auto-detect PAT from .quickcall.env (IMPORTANT):**
   - Use the Read tool to check if `.quickcall.env` exists in the current project directory
   - If found, read it and look for `GITHUB_TOKEN=...` or `GITHUB_PAT=...`
   - If a token is found in the file, use it automatically (do NOT ask the user)
   - Also check `~/.quickcall.env` if not found in project root

3. **Get PAT from user (only if not found in .quickcall.env):**
   - If no token was found in config files, ask the user for their GitHub Personal Access Token
   - Remind them: "Create a PAT at https://github.com/settings/tokens with `repo` scope"
   - Or suggest: "You can also create a `.quickcall.env` file with `GITHUB_TOKEN=your_token`"

4. **Connect:**
   - Call `connect_github_via_pat` with the token (from file or user input)
   - The tool validates the token and auto-detects username

5. **Show result:**
   ```
   GitHub connected via PAT!
   Username: {username}
   Mode: Personal Access Token
   Source: .quickcall.env (or "manually provided")
   ```

## Notes

- PAT mode works independently of QuickCall
- Slack tools still require QuickCall authentication (`/quickcall:connect`)
- To disconnect PAT: call `disconnect_github_pat`
- The `.quickcall.env` file should NOT be committed to git (it contains secrets)
