---
description: List and summarize open PRs. Usage: /quickcall:pr-summary [repo]
---

# PR Summary

Get a summary of open pull requests for a repository.

## Arguments

Parse `$ARGUMENTS` for repository:
- `repo-name` → specific repository
- `owner/repo` → full repo path
- No argument → prompt user for repo

## Instructions

1. If no repo specified, ask user which repository to check
2. Use `manage_prs` tool with action="list" and state="open"
3. For each PR, show:
   - PR number and title
   - Author
   - Draft status
   - Created date
   - Labels (if any)
4. Group by status: ready for review vs draft
5. Provide a brief summary count

## Example Output

```
## Open PRs for owner/repo

### Ready for Review (2)
- #42: Add user authentication (@alice) - 2 days ago
- #38: Fix login bug (@bob) - 5 days ago [bug, urgent]

### Drafts (1)
- #45: WIP: New dashboard (@charlie) - 1 day ago

**Summary:** 3 open PRs (2 ready, 1 draft)
```

## Actions Available

If user wants to take action on PRs, use `manage_prs` with:
- `action="view"` - Get full PR details
- `action="merge"` - Merge a PR
- `action="comment"` - Add comment
- `action="request_reviewers"` - Request reviewers
- `action="review"` - Submit a review (APPROVE, REQUEST_CHANGES, COMMENT)
