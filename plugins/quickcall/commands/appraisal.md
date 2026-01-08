---
description: Generate contribution summary for performance reviews. Usage: /quickcall:appraisal 6m
---

# Appraisal Summary

Generate a comprehensive contribution summary for performance appraisals that helps developers sell their impact to leadership.

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

5. **Present the appraisal summary with leadership-ready framing**

## Output Format

```
## Contribution Summary ({period})

### Key Accomplishments

**1. {Feature Title}** (PR #{number} in {repo})
- {Brief description based on PR body/title}
- Technical Impact: {X additions, Y deletions, Z files changed}
- Business Impact: [How did this feature help users/revenue/growth? Fill in: ___]

> **Make it count:** Frame this as solving a customer pain point or enabling a business goal.

**2. {Enhancement/Fix Title}** (PR #{number} in {repo})
- {Brief description}
- Technical Impact: {metrics if fetched}
- Business Impact: [Did this reduce support tickets? Improve conversion? Fill in: ___]

> **Make it count:** Quantify the before/after. "Reduced page load by X%" or "Eliminated Y hours of manual work"

**3. {Another significant PR}**
...

---

### Metrics Summary

| Category      | Count |
|---------------|-------|
| Features      | X     |
| Enhancements  | Y     |
| Bug Fixes     | Z     |
| Chores        | W     |
| **Total PRs** | N     |

**Repositories:** {list of unique repos}
**Period:** {start_date} to {end_date}

> **Make it count:** "Delivered X features across Y repositories, demonstrating cross-team collaboration and system-wide ownership."

---

### Technical Areas
- {Infer from PR titles/repos what technologies or areas were worked on}
- {E.g., "Backend API development", "CI/CD improvements", etc.}

> **Make it count:** Connect technical skills to business value. "Improved CI/CD pipeline" → "Enabled faster releases, reducing time-to-market by [X days/weeks]"

---

### Business Impact (Fill in the blanks)

Use these prompts to strengthen your self-review:

1. **Revenue Impact:** [Did any feature directly impact revenue? e.g., "Payment integration enabled $X in new transactions"]

2. **User Impact:** [How many users benefited? e.g., "Auth improvements affected 10K+ daily active users"]

3. **Efficiency Gains:** [Time saved for team/customers? e.g., "Automated deployment saves 2 hours per release"]

4. **Risk Reduction:** [Bugs fixed that could have caused outages? e.g., "Fixed race condition that caused 3 incidents last quarter"]

5. **Strategic Alignment:** [How does this work support company OKRs/goals?]

---

*This is your technical proof. Now add the business story. Leadership cares about outcomes, not outputs.*
```

## Tips for Demonstrating Impact

- **Lead with outcomes, not outputs:** "Shipped 47 PRs" → "Delivered 3 major features that increased user engagement by X%"
- **Quantify everything:** Numbers are memorable. Even estimates help: "~20% faster", "saved ~4 hours/week"
- **Connect to company goals:** Tie your work to OKRs, quarterly goals, or strategic initiatives
- **Show growth:** Highlight new technologies learned, increased scope, or cross-team collaboration
- **Bug fixes matter:** Frame them as "risk reduction" or "reliability improvements"
- **Group related work:** "Authentication overhaul" sounds bigger than "5 auth-related PRs"
