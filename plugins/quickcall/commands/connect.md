---
description: Connect QuickCall, GitHub, and Slack integrations
---

# Connect Integrations

Connect all 3 services automatically in sequence:

1. **QuickCall** (if not connected):
   - `connect_quickcall` → display URL + code → `complete_quickcall_auth`

2. **GitHub** (if not connected):
   - `connect_github` → display install URL → wait for user to complete

3. **Slack** (if not connected):
   - `connect_slack` → display install URL → wait for user to complete

**CRITICAL:** Always display URLs as clickable markdown links:
```
**Code:** XXXX-XXXX
**URL:** [Open](https://app.quickcall.dev/cli/setup?code=XXXX-XXXX)
```

Do NOT ask user if they want to connect - just proceed to connect all services.

After all connections, show final status:
```
QuickCall: Connected
GitHub: Connected (username)
Slack: Connected (workspace)
```
