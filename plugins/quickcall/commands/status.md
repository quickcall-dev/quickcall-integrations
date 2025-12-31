---
description: Show QuickCall connection status
---

# Connection Status

Show the current status of all integrations.

## Instructions

1. Call `check_quickcall_status` tool

2. Display the results in a clean format:

```
QuickCall Status
----------------
Account: Connected / Not connected
GitHub:  Connected (username) / Not connected
Slack:   Connected (workspace) / Not connected
```

3. If not fully connected, suggest running `/quickcall:connect`
