---
description: Connect GitHub using a Personal Access Token (for enterprise users)
---

# Connect GitHub via PAT

Use this if your organization can't install the QuickCall GitHub App.

## Steps

1. **Call `connect_github_via_pat` (no arguments needed):**
   - The tool auto-detects tokens from these locations (in order):
     1. `GITHUB_TOKEN` or `GITHUB_PAT` environment variable
     2. `.quickcall.env` in project root (where `.git` is located)
     3. `~/.quickcall.env` in home directory
   - If a token is found, it validates and connects automatically
   - If no token is found, it returns an error with helpful instructions

2. **If no token found automatically:**
   - Ask the user for their GitHub Personal Access Token
   - Remind them: "Create a PAT at https://github.com/settings/tokens with scopes: project, read:user, repo"
   - Or suggest: "Create a `.quickcall.env` file in your project root with `GITHUB_TOKEN=ghp_xxx`"
   - Call `connect_github_via_pat` with the provided token

3. **Show result:**
   ```
   GitHub connected via PAT!
   Username: {username}
   Token source: {token_source}
   ```

## Notes

- PAT mode works independently of QuickCall
- Slack tools still require QuickCall authentication (`/quickcall:connect`)
- To disconnect PAT: call `disconnect_github_pat`
- The `.quickcall.env` file should NOT be committed to git (it contains secrets)
