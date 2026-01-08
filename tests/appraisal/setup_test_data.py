#!/usr/bin/env python3
"""
Setup test data for appraisal feature testing.

Fetches PRs from supabase/supabase and recreates them on revolving-org/supabase
with proper merge status so they can be discovered by search_merged_prs.

Usage:
    source secrets/git.env
    python tests/appraisal/setup_test_data.py
"""

import os
import sys
import time
import requests

# Configuration
SOURCE_REPO = "supabase/supabase"
TARGET_REPO = "revolving-org/supabase"
TARGET_BASE_BRANCH = "master"


def get_token() -> str:
    """Get GitHub PAT from environment."""
    token = os.environ.get("GH_PAT")
    if not token:
        print("Error: GH_PAT environment variable not set")
        print("Run: source secrets/git.env")
        sys.exit(1)
    return token


def fetch_diverse_prs(token: str, count: int = 10) -> list:
    """
    Fetch a diverse set of PRs from source repo.
    Gets a mix of feat, fix, chore, docs PRs.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    prs = []
    categories = {
        "feat": [],
        "fix": [],
        "chore": [],
        "docs": [],
    }

    # Search for merged PRs
    response = requests.get(
        "https://api.github.com/search/issues",
        headers=headers,
        params={
            "q": f"is:pr is:merged repo:{SOURCE_REPO}",
            "sort": "updated",
            "order": "desc",
            "per_page": 50,
        },
    )
    response.raise_for_status()
    items = response.json().get("items", [])

    # Categorize PRs
    for item in items:
        title = item["title"].lower()
        pr_data = {
            "number": item["number"],
            "title": item["title"],
            "body": item.get("body") or "",
            "labels": [label["name"] for label in item.get("labels", [])],
            "html_url": item["html_url"],
        }

        if title.startswith("feat") and len(categories["feat"]) < 3:
            categories["feat"].append(pr_data)
        elif title.startswith("fix") and len(categories["fix"]) < 3:
            categories["fix"].append(pr_data)
        elif title.startswith("chore") and len(categories["chore"]) < 2:
            categories["chore"].append(pr_data)
        elif title.startswith("docs") and len(categories["docs"]) < 2:
            categories["docs"].append(pr_data)

    # Combine categories
    for category, pr_list in categories.items():
        prs.extend(pr_list)
        print(f"  Found {len(pr_list)} {category} PRs")

    return prs[:count]


def recreate_pr_on_fork(source_pr: dict, token: str) -> tuple[int, bool]:
    """
    Recreate a PR from source repo onto fork, fully merged.

    Steps:
    1. Get base SHA (master branch)
    2. Create new branch
    3. Create dummy commit with original PR title as message
    4. Open PR with original title/body/labels
    5. Merge the PR

    Returns:
        Tuple of (pr_number, success)
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    try:
        # 1. Get base SHA (master branch)
        base_response = requests.get(
            f"https://api.github.com/repos/{TARGET_REPO}/git/refs/heads/{TARGET_BASE_BRANCH}",
            headers=headers,
        )
        base_response.raise_for_status()
        base_sha = base_response.json()["object"]["sha"]

        # 2. Create new branch
        branch_name = f"test-pr-{source_pr['number']}-{int(time.time())}"
        branch_response = requests.post(
            f"https://api.github.com/repos/{TARGET_REPO}/git/refs",
            headers=headers,
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        )
        branch_response.raise_for_status()

        # 3. Create a dummy commit
        # First, create a tree with a test file
        tree_response = requests.post(
            f"https://api.github.com/repos/{TARGET_REPO}/git/trees",
            headers=headers,
            json={
                "base_tree": base_sha,
                "tree": [
                    {
                        "path": f"test-data/pr-{source_pr['number']}.md",
                        "mode": "100644",
                        "type": "blob",
                        "content": f"# Test PR #{source_pr['number']}\n\n"
                        f"Original: {source_pr['html_url']}\n\n"
                        f"## Title\n{source_pr['title']}\n\n"
                        f"## Body\n{source_pr['body'][:500] if source_pr['body'] else 'No description'}\n",
                    }
                ],
            },
        )
        tree_response.raise_for_status()
        tree_sha = tree_response.json()["sha"]

        # Create commit
        commit_response = requests.post(
            f"https://api.github.com/repos/{TARGET_REPO}/git/commits",
            headers=headers,
            json={
                "message": source_pr["title"],
                "tree": tree_sha,
                "parents": [base_sha],
            },
        )
        commit_response.raise_for_status()
        commit_sha = commit_response.json()["sha"]

        # Update branch to point to new commit
        requests.patch(
            f"https://api.github.com/repos/{TARGET_REPO}/git/refs/heads/{branch_name}",
            headers=headers,
            json={"sha": commit_sha},
        )

        # 4. Open PR with original metadata
        pr_body = source_pr["body"] or ""
        pr_body += (
            f"\n\n---\n_Test data recreated from {SOURCE_REPO}#{source_pr['number']}_"
        )

        pr_response = requests.post(
            f"https://api.github.com/repos/{TARGET_REPO}/pulls",
            headers=headers,
            json={
                "title": source_pr["title"],
                "body": pr_body,
                "head": branch_name,
                "base": TARGET_BASE_BRANCH,
            },
        )
        pr_response.raise_for_status()
        pr_data = pr_response.json()
        pr_number = pr_data["number"]

        # 5. Add labels if any exist on target repo
        # (labels must exist in target repo first)
        # Skipping for simplicity

        # 6. MERGE the PR
        time.sleep(1)  # Brief pause to ensure PR is ready
        merge_response = requests.put(
            f"https://api.github.com/repos/{TARGET_REPO}/pulls/{pr_number}/merge",
            headers=headers,
            json={
                "commit_title": f"Merge PR #{pr_number}: {source_pr['title']}",
                "merge_method": "merge",
            },
        )

        success = merge_response.status_code == 200
        return pr_number, success

    except requests.exceptions.RequestException as e:
        print(f"    Error: {e}")
        return 0, False


def verify_merged_prs(token: str) -> int:
    """Verify how many merged PRs exist on target repo."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    response = requests.get(
        "https://api.github.com/search/issues",
        headers=headers,
        params={
            "q": f"is:pr is:merged repo:{TARGET_REPO}",
        },
    )
    response.raise_for_status()
    return response.json().get("total_count", 0)


def main():
    print("=" * 60)
    print("Appraisal Test Data Setup")
    print("=" * 60)
    print(f"\nSource: {SOURCE_REPO}")
    print(f"Target: {TARGET_REPO}")
    print()

    token = get_token()

    # Check current state
    existing_count = verify_merged_prs(token)
    print(f"Existing merged PRs on target: {existing_count}")

    if existing_count >= 10:
        print("\nAlready have 10+ merged PRs. Skipping setup.")
        print("To reset, manually delete PRs from the fork.")
        return

    # Fetch diverse PRs from source
    print(f"\nFetching diverse PRs from {SOURCE_REPO}...")
    prs = fetch_diverse_prs(token, count=10)
    print(f"Found {len(prs)} PRs to recreate")

    # Recreate each PR
    print(f"\nRecreating PRs on {TARGET_REPO}...")
    success_count = 0
    for i, pr in enumerate(prs, 1):
        print(f"\n[{i}/{len(prs)}] {pr['title'][:50]}...")
        pr_number, success = recreate_pr_on_fork(pr, token)
        if success:
            print(f"    Created and merged PR #{pr_number}")
            success_count += 1
        else:
            print("    Failed to create/merge PR")
        time.sleep(1)  # Rate limit friendly

    # Verify
    print("\n" + "=" * 60)
    final_count = verify_merged_prs(token)
    print(f"Final merged PR count: {final_count}")
    print(f"Successfully created: {success_count}/{len(prs)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
