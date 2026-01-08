---
description: Generate contribution summary for performance reviews. Usage: /quickcall:appraisal 6m
---

# Appraisal Summary

Generate a comprehensive contribution summary for performance appraisals.

## Arguments

Parse `$ARGUMENTS` for time period:
- `6m` or `6mo` → 180 days (default)
- `3m` or `3mo` → 90 days
- `1y` or `12m` → 365 days
- No argument → default to 180 days

## Instructions

1. **Gather contribution data:**

   **Option A - GitHub API (preferred if connected):**
   - Use `search_merged_prs` tool with parsed days
   - If user specifies an org, pass the `org` parameter
   - If user specifies a repo, pass the `repo` parameter (format: "owner/repo")
   - Default author is the authenticated user

   **Option B - Local Git (fallback if not connected or for specific repo):**
   - Use `get_local_contributions` tool on the current directory
   - This parses local git history for commits by the user
   - Extracts PR numbers from merge commit messages where available

2. **Analyze and categorize each PR:**
   Examine each PR's title, body, and labels to categorize:
   - **Features**: New functionality (feat:, add:, implement, new, create)
   - **Enhancements**: Improvements (improve:, update:, perf:, optimize, enhance)
   - **Bug fixes**: (fix:, bugfix:, hotfix:, resolve, patch)
   - **Chores**: Maintenance work (docs:, test:, ci:, chore:, refactor:, bump)

3. **Identify top accomplishments:**
   - Filter out chores for the highlights
   - Sort features and enhancements by significance (based on title complexity, labels)
   - For top 3-5 PRs, call `get_pr` to fetch detailed metrics (additions, deletions, files)

4. **Calculate summary metrics:**
   - Total PRs merged by category
   - Unique repos contributed to
   - Date range covered

5. **Present the appraisal summary**

## Output Format

```
## Contribution Summary ({period})

### Key Accomplishments

**1. {Feature Title}** (PR #{number} in {repo})
- {Brief description based on PR body/title}
- Impact: {X additions, Y deletions, Z files changed}

**2. {Enhancement Title}** (PR #{number} in {repo})
- {Brief description}
- Impact: {metrics if fetched}

**3. {Another significant PR}**
...

### Metrics

| Category      | Count |
|---------------|-------|
| Features      | X     |
| Enhancements  | Y     |
| Bug Fixes     | Z     |
| Chores        | W     |
| **Total PRs** | N     |

**Repositories:** {list of unique repos}
**Period:** {start_date} to {end_date}

### Technical Areas
- {Infer from PR titles/repos what technologies or areas were worked on}
- {E.g., "Backend API development", "CI/CD improvements", etc.}

---

*Ready for your self-review. Add business impact, user metrics, and stakeholder feedback to make it compelling.*
```

## Tips

- Focus on FEATURES and ENHANCEMENTS - these show impact
- Group related PRs if they're part of the same project/feature
- Look for patterns showing growth (new tech, increased scope, cross-team work)
- Be encouraging - help them see the value of their work!
- If there are many PRs, summarize by theme rather than listing all
