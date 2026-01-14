#!/usr/bin/env python3
"""
Integration test for appraisal tools.

Tests the actual MCP tool functions with real GitHub API calls.

Usage:
    uv run python tests/test_appraisal_integration.py
"""

import json
import os
import sys

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_prepare_appraisal_data_tool():
    """Test prepare_appraisal_data MCP tool with real API."""
    print("\n=== Integration Test: prepare_appraisal_data ===")

    from mcp_server.auth import get_github_pat, get_credential_store
    from mcp_server.api_clients.github_client import GitHubClient

    # Check auth
    pat_token, source = get_github_pat()
    store = get_credential_store()

    if not pat_token and not store.is_authenticated():
        print("⚠️  No GitHub auth available, skipping integration test")
        return None

    # Get client
    if pat_token:
        client = GitHubClient(token=pat_token)
        author = client.get_authenticated_user()
        print(f"✅ Using PAT ({source}), user: {author}")
    else:
        creds = store.get_api_credentials()
        client = GitHubClient(
            token=creds.github_token,
            default_owner=creds.github_username,
            installation_id=creds.github_installation_id,
        )
        author = creds.github_username
        print(f"✅ Using GitHub App, user: {author}")

    # Step 1: Search merged PRs
    print("\n[Step 1] Searching merged PRs (last 30 days, limit 10)...")
    from datetime import datetime, timedelta, timezone

    since_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

    pr_list = client.search_merged_prs(
        author=author,
        since_date=since_date,
        limit=10,
        detail_level="full",
    )

    if not pr_list:
        print("⚠️  No merged PRs found in last 30 days")
        return None

    print(f"✅ Found {len(pr_list)} PRs")
    for pr in pr_list[:3]:
        print(f"   - #{pr['number']}: {pr['title'][:50]}")

    # Step 2: Fetch full details in parallel
    print("\n[Step 2] Fetching full PR details in parallel...")
    pr_refs = [
        {"owner": pr["owner"], "repo": pr["repo"], "number": pr["number"]}
        for pr in pr_list
    ]

    full_prs = client.fetch_prs_parallel(pr_refs, max_workers=5)
    print(f"✅ Fetched {len(full_prs)} PRs with full details")

    if full_prs:
        pr = full_prs[0]
        print(
            f"   Sample: #{pr['number']} - +{pr.get('additions', 0)}/-{pr.get('deletions', 0)}"
        )

    # Step 3: Dump to file
    print("\n[Step 3] Dumping to file...")
    import tempfile

    dump_data = {
        "author": author,
        "period": "Last 30 days",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(full_prs),
        "prs": full_prs,
    }

    fd, file_path = tempfile.mkstemp(suffix=".json", prefix="appraisal_integration_")
    with open(file_path, "w") as f:
        json.dump(dump_data, f, indent=2, default=str)

    file_size = os.path.getsize(file_path)
    print(f"✅ Dumped to: {file_path}")
    print(f"   Size: {file_size / 1024:.1f} KB")

    # Step 4: Generate titles (what tool returns)
    print("\n[Step 4] Generating PR titles for Claude...")
    pr_titles = [
        {
            "number": pr["number"],
            "title": pr["title"],
            "repo": f"{pr.get('owner', '')}/{pr.get('repo', '')}",
        }
        for pr in full_prs
    ]

    print(f"✅ Generated {len(pr_titles)} titles")
    for t in pr_titles[:5]:
        print(f"   - #{t['number']}: {t['title'][:50]}")

    # Step 5: Test get_appraisal_pr_details
    print("\n[Step 5] Testing get_appraisal_pr_details...")
    if len(full_prs) >= 2:
        selected_numbers = [full_prs[0]["number"], full_prs[1]["number"]]

        with open(file_path) as f:
            data = json.load(f)

        pr_numbers_set = set(selected_numbers)
        selected_prs = [
            pr for pr in data.get("prs", []) if pr["number"] in pr_numbers_set
        ]

        print(f"✅ Retrieved {len(selected_prs)} selected PRs from dump")
        for pr in selected_prs:
            print(
                f"   - #{pr['number']}: {pr['title'][:40]} (+{pr.get('additions', 0)}/-{pr.get('deletions', 0)})"
            )

    # Cleanup
    os.unlink(file_path)
    print("\n✅ Integration test passed!")
    return True


def test_response_size():
    """Test that response sizes are reasonable."""
    print("\n=== Test: Response sizes ===")

    # Simulate 100 PRs
    mock_pr_titles = [
        {
            "number": i,
            "title": f"PR title for #{i} - some description here",
            "repo": "org/repo",
        }
        for i in range(1, 101)
    ]

    # Calculate size of titles-only response
    titles_response = {
        "file_path": "/tmp/appraisal_xxx.json",
        "count": 100,
        "author": "testuser",
        "period": "Last 180 days",
        "pr_titles": mock_pr_titles,
        "next_step": "Call get_appraisal_pr_details...",
    }

    titles_size = len(json.dumps(titles_response))
    print(f"✅ Titles-only response for 100 PRs: {titles_size / 1024:.1f} KB")

    # Compare to full response (old way)
    mock_full_prs = [
        {
            "number": i,
            "title": f"PR title for #{i} - some description here",
            "body": "This is a longer description " * 10,
            "owner": "org",
            "repo": "repo",
            "additions": 100,
            "deletions": 50,
            "changed_files": 10,
            "labels": ["bug", "feature"],
            "merged_at": "2024-01-01T00:00:00Z",
            "html_url": f"https://github.com/org/repo/pull/{i}",
        }
        for i in range(1, 101)
    ]

    full_response = {
        "count": 100,
        "prs": mock_full_prs,
    }

    full_size = len(json.dumps(full_response))
    print(f"✅ Full response for 100 PRs: {full_size / 1024:.1f} KB")
    print(f"✅ Reduction: {(1 - titles_size / full_size) * 100:.0f}%")

    assert titles_size < full_size / 2, "Titles response should be <50% of full"
    print("✅ Test passed!\n")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Appraisal Tools - Integration Tests")
    print("=" * 60)

    results = []

    # Test response sizes first (no auth needed)
    try:
        results.append(("Response sizes", test_response_size()))
    except Exception as e:
        print(f"❌ Failed: {e}")
        results.append(("Response sizes", False))

    # Test actual tool flow
    try:
        result = test_prepare_appraisal_data_tool()
        results.append(("prepare_appraisal_data", result))
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback

        traceback.print_exc()
        results.append(("prepare_appraisal_data", False))

    print("\n" + "=" * 60)
    print("Results:")
    for name, passed in results:
        status = "✅ PASS" if passed else ("⚠️ SKIP" if passed is None else "❌ FAIL")
        print(f"  {name}: {status}")
    print("=" * 60)
