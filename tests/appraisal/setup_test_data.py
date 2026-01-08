#!/usr/bin/env python3
"""
Setup test data for appraisal feature testing.

Fetches 500 PRs from supabase/supabase and recreates them on revolving-org/supabase
with varied states: merged, open, in review.

Usage:
    source secrets/git.env
    source .venv/bin/activate
    python tests/appraisal/setup_test_data.py [--count 500] [--force]
"""

import argparse
import os
import sys
import time
import requests
from dataclasses import dataclass

# Configuration
SOURCE_REPO = "supabase/supabase"
TARGET_REPO = "revolving-org/supabase"
TARGET_BASE_BRANCH = "master"

# PR state distribution (percentages)
MERGED_PERCENT = 70  # 70% merged
OPEN_PERCENT = 20  # 20% open (in progress)
REVIEW_PERCENT = 10  # 10% open with review requested


@dataclass
class PRData:
    number: int
    title: str
    body: str
    labels: list
    html_url: str
    state: str  # 'merged', 'open', 'review'


def get_token() -> str:
    """Get GitHub PAT from environment."""
    token = os.environ.get("GH_PAT")
    if not token:
        print("Error: GH_PAT environment variable not set")
        print("Run: source secrets/git.env")
        sys.exit(1)
    return token


def fetch_prs_paginated(token: str, query: str, count: int) -> list:
    """Fetch PRs with pagination (max 100 per page)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    all_items = []
    page = 1
    per_page = 100

    while len(all_items) < count:
        response = requests.get(
            "https://api.github.com/search/issues",
            headers=headers,
            params={
                "q": query,
                "sort": "updated",
                "order": "desc",
                "per_page": per_page,
                "page": page,
            },
        )

        if response.status_code == 403:
            print("Rate limited. Waiting 60s...")
            time.sleep(60)
            continue

        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])

        if not items:
            break

        all_items.extend(items)
        print(f"  Fetched page {page}: {len(items)} PRs (total: {len(all_items)})")

        page += 1
        time.sleep(0.5)  # Rate limit friendly

        if len(items) < per_page:
            break

    return all_items[:count]


def fetch_diverse_prs(token: str, count: int = 500) -> list[PRData]:
    """
    Fetch a diverse set of PRs from source repo.
    Gets merged PRs and open PRs for variety.
    """
    prs = []

    # Calculate how many of each type to fetch
    merged_count = int(count * 0.8)  # Fetch more merged, we'll use 70%
    open_count = int(count * 0.4)  # Fetch open PRs

    # Fetch merged PRs
    print(f"\nFetching merged PRs from {SOURCE_REPO}...")
    merged_query = f"is:pr is:merged repo:{SOURCE_REPO}"
    merged_items = fetch_prs_paginated(token, merged_query, merged_count)

    for item in merged_items:
        prs.append(
            PRData(
                number=item["number"],
                title=item["title"],
                body=item.get("body") or "",
                labels=[label["name"] for label in item.get("labels", [])],
                html_url=item["html_url"],
                state="merged",
            )
        )

    # Fetch open PRs
    print(f"\nFetching open PRs from {SOURCE_REPO}...")
    open_query = f"is:pr is:open repo:{SOURCE_REPO}"
    open_items = fetch_prs_paginated(token, open_query, open_count)

    for i, item in enumerate(open_items):
        # Alternate between 'open' and 'review' states
        state = "review" if i % 3 == 0 else "open"
        prs.append(
            PRData(
                number=item["number"],
                title=item["title"],
                body=item.get("body") or "",
                labels=[label["name"] for label in item.get("labels", [])],
                html_url=item["html_url"],
                state=state,
            )
        )

    # Shuffle to mix states
    import random

    random.shuffle(prs)

    # Rebalance to target percentages
    merged_target = int(count * MERGED_PERCENT / 100)
    open_target = int(count * OPEN_PERCENT / 100)
    review_target = int(count * REVIEW_PERCENT / 100)

    result = []
    merged_added = open_added = review_added = 0

    for pr in prs:
        if len(result) >= count:
            break

        if pr.state == "merged" and merged_added < merged_target:
            result.append(pr)
            merged_added += 1
        elif pr.state == "open" and open_added < open_target:
            result.append(pr)
            open_added += 1
        elif pr.state == "review" and review_added < review_target:
            result.append(pr)
            review_added += 1

    # Fill remaining slots with any available PRs
    for pr in prs:
        if len(result) >= count:
            break
        if pr not in result:
            result.append(pr)

    print("\nPR distribution:")
    print(f"  Merged: {sum(1 for p in result if p.state == 'merged')}")
    print(f"  Open: {sum(1 for p in result if p.state == 'open')}")
    print(f"  Review: {sum(1 for p in result if p.state == 'review')}")

    return result[:count]


def recreate_pr_on_fork(
    source_pr: PRData, token: str, pr_index: int
) -> tuple[int, bool]:
    """
    Recreate a PR from source repo onto fork.

    Based on source_pr.state:
    - 'merged': Create and merge the PR
    - 'open': Create PR but leave it open
    - 'review': Create PR and request review

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

        # 2. Create new branch with unique name
        branch_name = f"test-pr-{pr_index}-{source_pr.number}-{int(time.time())}"
        branch_response = requests.post(
            f"https://api.github.com/repos/{TARGET_REPO}/git/refs",
            headers=headers,
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        )
        branch_response.raise_for_status()

        # 3. Create a dummy commit
        tree_response = requests.post(
            f"https://api.github.com/repos/{TARGET_REPO}/git/trees",
            headers=headers,
            json={
                "base_tree": base_sha,
                "tree": [
                    {
                        "path": f"test-data/pr-{pr_index}-{source_pr.number}.md",
                        "mode": "100644",
                        "type": "blob",
                        "content": f"# Test PR #{source_pr.number}\n\n"
                        f"Original: {source_pr.html_url}\n\n"
                        f"## Title\n{source_pr.title}\n\n"
                        f"## State\n{source_pr.state}\n\n"
                        f"## Body\n{source_pr.body[:500] if source_pr.body else 'No description'}\n",
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
                "message": source_pr.title,
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
        pr_body = source_pr.body or ""
        pr_body += (
            f"\n\n---\n_Test data recreated from {SOURCE_REPO}#{source_pr.number}_"
        )
        pr_body += f"\n_Target state: {source_pr.state}_"

        pr_response = requests.post(
            f"https://api.github.com/repos/{TARGET_REPO}/pulls",
            headers=headers,
            json={
                "title": source_pr.title,
                "body": pr_body,
                "head": branch_name,
                "base": TARGET_BASE_BRANCH,
            },
        )
        pr_response.raise_for_status()
        pr_data = pr_response.json()
        pr_number = pr_data["number"]

        # 5. Handle based on target state
        if source_pr.state == "merged":
            time.sleep(0.5)
            merge_response = requests.put(
                f"https://api.github.com/repos/{TARGET_REPO}/pulls/{pr_number}/merge",
                headers=headers,
                json={
                    "commit_title": f"Merge PR #{pr_number}: {source_pr.title}",
                    "merge_method": "merge",
                },
            )
            success = merge_response.status_code == 200

        elif source_pr.state == "review":
            # Request review (if we had collaborators, we'd add them here)
            # For now, just leave it open - it simulates "waiting for review"
            success = True

        else:  # 'open'
            # Just leave the PR open
            success = True

        return pr_number, success

    except requests.exceptions.RequestException as e:
        print(f"    Error: {e}")
        return 0, False


def get_existing_pr_count(token: str) -> dict:
    """Get count of existing PRs on target repo by state."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    counts = {"merged": 0, "open": 0, "total": 0}

    # Count merged
    response = requests.get(
        "https://api.github.com/search/issues",
        headers=headers,
        params={"q": f"is:pr is:merged repo:{TARGET_REPO}"},
    )
    if response.status_code == 200:
        counts["merged"] = response.json().get("total_count", 0)

    time.sleep(0.5)

    # Count open
    response = requests.get(
        "https://api.github.com/search/issues",
        headers=headers,
        params={"q": f"is:pr is:open repo:{TARGET_REPO}"},
    )
    if response.status_code == 200:
        counts["open"] = response.json().get("total_count", 0)

    counts["total"] = counts["merged"] + counts["open"]
    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Setup test data for appraisal testing"
    )
    parser.add_argument(
        "--count", type=int, default=500, help="Number of PRs to create"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force creation even if PRs exist"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Appraisal Test Data Setup (Extended)")
    print("=" * 60)
    print(f"\nSource: {SOURCE_REPO}")
    print(f"Target: {TARGET_REPO}")
    print(f"Target count: {args.count}")
    print()

    token = get_token()

    # Check current state
    existing = get_existing_pr_count(token)
    print("Existing PRs on target:")
    print(f"  Merged: {existing['merged']}")
    print(f"  Open: {existing['open']}")
    print(f"  Total: {existing['total']}")

    if existing["total"] >= args.count and not args.force:
        print(f"\nAlready have {existing['total']}+ PRs. Use --force to add more.")
        return

    # Calculate how many more to create
    to_create = args.count - existing["total"] if not args.force else args.count
    if to_create <= 0:
        to_create = args.count

    print(f"\nWill create {to_create} new PRs")

    # Fetch diverse PRs from source
    print(f"\nFetching diverse PRs from {SOURCE_REPO}...")
    prs = fetch_diverse_prs(token, count=to_create)
    print(f"\nFetched {len(prs)} PRs to recreate")

    # Recreate each PR
    print(f"\nRecreating PRs on {TARGET_REPO}...")
    print("This will take a while for large counts. Progress:")

    success_count = 0
    merged_count = 0
    open_count = 0
    review_count = 0

    start_time = time.time()

    for i, pr in enumerate(prs, 1):
        # Progress indicator every 10 PRs
        if i % 10 == 0 or i == 1:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(prs) - i) / rate if rate > 0 else 0
            print(
                f"\n[{i}/{len(prs)}] {pr.state.upper()} - {pr.title[:40]}... "
                f"(ETA: {eta / 60:.1f}min)"
            )

        pr_number, success = recreate_pr_on_fork(pr, token, i)

        if success:
            success_count += 1
            if pr.state == "merged":
                merged_count += 1
            elif pr.state == "open":
                open_count += 1
            else:
                review_count += 1

        # Rate limiting - be gentle with GitHub API
        time.sleep(0.3)

        # Extra pause every 50 PRs to avoid rate limits
        if i % 50 == 0:
            print("  Pausing 5s to avoid rate limits...")
            time.sleep(5)

    # Final summary
    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)

    final = get_existing_pr_count(token)
    print(f"\nFinal PR counts on {TARGET_REPO}:")
    print(f"  Merged: {final['merged']}")
    print(f"  Open: {final['open']}")
    print(f"  Total: {final['total']}")

    print("\nThis run:")
    print(f"  Successfully created: {success_count}/{len(prs)}")
    print(f"    - Merged: {merged_count}")
    print(f"    - Open: {open_count}")
    print(f"    - Review: {review_count}")

    elapsed = time.time() - start_time
    print(f"\nTime elapsed: {elapsed / 60:.1f} minutes")
    print("=" * 60)


if __name__ == "__main__":
    main()
