---
description: Connect QuickCall, GitHub, and Slack integrations
---

# Connect Integrations

1. Call `check_quickcall_status` first
2. Connect based on status:
   - **QuickCall:** `connect_quickcall` → display URL + code → `complete_quickcall_auth`
   - **GitHub:** `connect_github` → display install URL
   - **Slack:** `connect_slack` → display install URL

**CRITICAL:** Always display the full URL as clickable markdown link:
```
**Code:** XXXX-XXXX
**URL:** [Open](https://app.quickcall.dev/cli/setup?code=XXXX-XXXX)
```

After connections, show status:
```
QuickCall: Connected
GitHub: Connected (username)
Slack: Connected (workspace)
```
