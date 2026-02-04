---
description: Manage GitHub Projects V2 - add issues, update fields
---

# GitHub Projects Management

Use `manage_projects` for all project operations.

## Key Principle: Minimize API Calls

**ALWAYS combine operations when possible:**

### Adding issue + setting fields (1 call instead of 2)
```python
manage_projects(
    action="add",
    issue_numbers=[42],
    project="1",
    fields={"Status": "Triage", "Issue Type": "Bug"},
    owner="org",
    repo="repo"
)
```

### DON'T do this (2 calls):
```python
# BAD - wasteful
manage_projects(action="add", issue_numbers=[42], project="1", ...)
manage_projects(action="update_fields", issue_numbers=[42], project="1", fields={...}, ...)
```

## Available Actions

| Action | Description | Required Params |
|--------|-------------|-----------------|
| `list` | List projects for org/user | `owner` (optional) |
| `add` | Add issues to project + optionally set fields | `issue_numbers`, `project`, optionally `fields` |
| `remove` | Remove issues from project | `issue_numbers`, `project` |
| `update_fields` | Update field values for issues already in project | `issue_numbers`, `project`, `fields` |

## Field Types

Check `github://projects` resource for available fields and values:
- **SINGLE_SELECT**: Use exact option name (e.g., "In Progress", "High")
- **TEXT**: Any string
- **NUMBER**: Numeric value as string
- **DATE**: ISO format (YYYY-MM-DD)

## Common Workflows

### Create issue and add to project with status
```python
# Step 1: Create issue
result = manage_issues(action="create", title="Bug fix", owner="org", repo="repo")
issue_num = result["issue"]["number"]

# Step 2: Add to project WITH fields (single call)
manage_projects(
    action="add",
    issue_numbers=[issue_num],
    project="1",
    fields={"Status": "Todo", "Issue Type": "Bug"},
    owner="org",
    repo="repo"
)
```

### Move issue to different status
```python
manage_projects(
    action="update_fields",
    issue_numbers=[42],
    project="1",
    fields={"Status": "In Progress"},
    owner="org",
    repo="repo"
)
```

### Bulk update multiple issues
```python
manage_projects(
    action="update_fields",
    issue_numbers=[42, 43, 44],
    project="1",
    fields={"Status": "Done"},
    owner="org",
    repo="repo"
)
```
