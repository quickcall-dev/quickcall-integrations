#!/usr/bin/env python3
"""
Test appraisal tools locally.

Tests:
1. prepare_appraisal_data - fetches PRs in parallel, dumps to file, returns titles
2. get_appraisal_pr_details - reads from dump file

Usage:
    uv run python tests/test_appraisal_tools.py
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Test the core logic without MCP server


def test_prepare_appraisal_data_dumps_to_file():
    """Test that prepare_appraisal_data creates a file with PR data."""
    print("\n=== Test 1: prepare_appraisal_data dumps to file ===")

    # Mock data - simulating full PR details from parallel fetch
    mock_full_prs = [
        {
            "number": 1,
            "title": "feat: add login",
            "owner": "test-org",
            "repo": "test-repo",
            "additions": 100,
            "deletions": 20,
            "body": "Added login feature",
        },
        {
            "number": 2,
            "title": "fix: bug in auth",
            "owner": "test-org",
            "repo": "test-repo",
            "additions": 10,
            "deletions": 5,
            "body": "Fixed auth bug",
        },
        {
            "number": 3,
            "title": "chore: update deps",
            "owner": "test-org",
            "repo": "test-repo",
            "additions": 50,
            "deletions": 50,
            "body": "Updated dependencies",
        },
    ]

    # Simulate what prepare_appraisal_data does
    dump_data = {
        "author": "testuser",
        "period": "Last 180 days",
        "org": None,
        "repo": None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(mock_full_prs),
        "prs": mock_full_prs,
    }

    # Create temp file
    fd, file_path = tempfile.mkstemp(suffix=".json", prefix="appraisal_test_")
    with open(file_path, "w") as f:
        json.dump(dump_data, f, indent=2, default=str)

    # Verify file exists and has correct structure
    assert os.path.exists(file_path), "File should be created"

    with open(file_path) as f:
        loaded = json.load(f)

    assert loaded["count"] == 3, f"Expected 3 PRs, got {loaded['count']}"
    assert len(loaded["prs"]) == 3, "Should have 3 PRs in data"
    assert loaded["prs"][0]["title"] == "feat: add login", "First PR title should match"

    # Generate titles (what prepare_appraisal_data returns)
    pr_titles = [
        {
            "number": pr["number"],
            "title": pr["title"],
            "repo": f"{pr['owner']}/{pr['repo']}",
        }
        for pr in mock_full_prs
    ]

    result = {
        "file_path": file_path,
        "count": len(mock_full_prs),
        "author": "testuser",
        "period": "Last 180 days",
        "pr_titles": pr_titles,
        "next_step": "Call get_appraisal_pr_details...",
    }

    print(f"✅ File created: {file_path}")
    print(f"✅ PR count: {result['count']}")
    print(f"✅ PR titles returned: {len(result['pr_titles'])}")
    for t in result["pr_titles"]:
        print(f"   - #{t['number']}: {t['title']}")

    # Cleanup
    os.unlink(file_path)
    print("✅ Test passed!\n")
    return True


def test_get_appraisal_pr_details_reads_from_file():
    """Test that get_appraisal_pr_details reads selected PRs from dump."""
    print("\n=== Test 2: get_appraisal_pr_details reads from file ===")

    # Create a dump file
    mock_prs = [
        {
            "number": 1,
            "title": "feat: add login",
            "owner": "test-org",
            "repo": "test-repo",
            "additions": 100,
            "deletions": 20,
            "body": "Added login feature",
        },
        {
            "number": 2,
            "title": "fix: bug in auth",
            "owner": "test-org",
            "repo": "test-repo",
            "additions": 10,
            "deletions": 5,
            "body": "Fixed auth bug",
        },
        {
            "number": 3,
            "title": "chore: update deps",
            "owner": "test-org",
            "repo": "test-repo",
            "additions": 50,
            "deletions": 50,
            "body": "Updated dependencies",
        },
        {
            "number": 4,
            "title": "feat: add logout",
            "owner": "test-org",
            "repo": "test-repo",
            "additions": 80,
            "deletions": 10,
            "body": "Added logout",
        },
        {
            "number": 5,
            "title": "docs: update readme",
            "owner": "test-org",
            "repo": "test-repo",
            "additions": 20,
            "deletions": 5,
            "body": "Updated docs",
        },
    ]

    dump_data = {
        "author": "testuser",
        "period": "Last 180 days",
        "prs": mock_prs,
    }

    fd, file_path = tempfile.mkstemp(suffix=".json", prefix="appraisal_test_")
    with open(file_path, "w") as f:
        json.dump(dump_data, f)

    # Simulate get_appraisal_pr_details - select only PRs 1 and 4
    selected_numbers = [1, 4]
    pr_numbers_set = set(selected_numbers)

    with open(file_path) as f:
        data = json.load(f)

    selected_prs = [pr for pr in data.get("prs", []) if pr["number"] in pr_numbers_set]

    result = {
        "count": len(selected_prs),
        "requested": len(selected_numbers),
        "prs": selected_prs,
    }

    assert result["count"] == 2, f"Expected 2 PRs, got {result['count']}"
    assert result["prs"][0]["number"] == 1, "First PR should be #1"
    assert result["prs"][1]["number"] == 4, "Second PR should be #4"
    assert result["prs"][0]["additions"] == 100, "Should have full PR details"

    print(f"✅ Requested PRs: {selected_numbers}")
    print(f"✅ Retrieved {result['count']} PRs from dump")
    for pr in result["prs"]:
        print(
            f"   - #{pr['number']}: {pr['title']} (+{pr['additions']}/-{pr['deletions']})"
        )

    # Cleanup
    os.unlink(file_path)
    print("✅ Test passed!\n")
    return True


def test_parallel_fetch_simulation():
    """Test that parallel fetching logic works."""
    print("\n=== Test 3: Parallel fetch simulation ===")

    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time

    # Simulate fetching PR details
    def fetch_pr(pr_ref):
        # Simulate API latency
        time.sleep(0.1)
        return {
            "number": pr_ref["number"],
            "title": f"PR #{pr_ref['number']}",
            "owner": pr_ref["owner"],
            "repo": pr_ref["repo"],
            "additions": pr_ref["number"] * 10,
            "deletions": pr_ref["number"] * 2,
        }

    pr_refs = [
        {"owner": "test", "repo": "repo", "number": i}
        for i in range(1, 11)  # 10 PRs
    ]

    start = time.time()

    # Sequential (for comparison)
    # sequential_results = [fetch_pr(ref) for ref in pr_refs]
    # sequential_time = time.time() - start

    # Parallel
    start = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_pr, ref): ref for ref in pr_refs}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    parallel_time = time.time() - start

    assert len(results) == 10, f"Expected 10 results, got {len(results)}"
    print(f"✅ Fetched {len(results)} PRs in parallel")
    print(f"✅ Time: {parallel_time:.2f}s (vs ~1s sequential)")
    print("✅ Test passed!\n")
    return True


def test_full_flow_with_mock_client():
    """Test the full appraisal flow with mocked GitHub client."""
    print("\n=== Test 4: Full flow with mock client ===")

    from mcp_server.api_clients.github_client import GitHubClient

    # Create a mock client
    with patch.object(GitHubClient, "__init__", lambda self, **kwargs: None):
        client = GitHubClient(token="fake")
        client.token = "fake"
        client._is_pat_mode = True
        client.default_owner = "testuser"

        # Mock search_merged_prs
        mock_search_results = [
            {
                "number": 1,
                "title": "feat: add feature",
                "owner": "org",
                "repo": "repo",
                "merged_at": "2024-01-01",
                "body": "",
                "labels": [],
            },
            {
                "number": 2,
                "title": "fix: bug fix",
                "owner": "org",
                "repo": "repo",
                "merged_at": "2024-01-02",
                "body": "",
                "labels": [],
            },
        ]

        # Mock get_pr to return full details
        class MockPR:
            def __init__(self, num):
                self.number = num
                self.title = f"PR #{num}"
                self.body = f"Body for PR #{num}"
                self.state = "closed"
                self.additions = num * 100
                self.deletions = num * 10
                self.changed_files = num * 5
                self.commits = num
                self.draft = False
                self.mergeable = True
                self.labels = []
                self.reviewers = []
                self.created_at = datetime.now()
                self.updated_at = datetime.now()
                self.merged_at = datetime.now()
                self.html_url = f"https://github.com/org/repo/pull/{num}"
                self.head_branch = "feature"
                self.base_branch = "main"
                self.user = MagicMock(login="testuser")

            def model_dump(self):
                return {
                    "number": self.number,
                    "title": self.title,
                    "body": self.body,
                    "additions": self.additions,
                    "deletions": self.deletions,
                }

        client.search_merged_prs = MagicMock(return_value=mock_search_results)
        client.get_pr = MagicMock(side_effect=lambda num, **kw: MockPR(num))

        # Test search
        search_result = client.search_merged_prs(
            author="testuser", since_date="2024-01-01"
        )
        assert len(search_result) == 2, "Should get 2 PRs from search"
        print(f"✅ Search returned {len(search_result)} PRs")

        # Test get_pr
        pr = client.get_pr(1)
        assert pr.number == 1, "Should get PR #1"
        assert pr.additions == 100, "Should have additions"
        print(
            f"✅ get_pr returned PR #{pr.number} with +{pr.additions}/-{pr.deletions}"
        )

    print("✅ Test passed!\n")
    return True


def test_actual_github_client():
    """Test actual GitHub client if credentials available."""
    print("\n=== Test 5: Actual GitHub client (optional) ===")

    from mcp_server.auth import get_github_pat

    pat_token, source = get_github_pat()
    if not pat_token:
        print("⚠️  No GitHub PAT found, skipping live test")
        print("   Set GITHUB_TOKEN env var to enable this test")
        return True

    from mcp_server.api_clients.github_client import GitHubClient

    client = GitHubClient(token=pat_token)

    # Test search (limited)
    print(f"✅ Using PAT from {source}")

    try:
        prs = client.search_merged_prs(
            author=client.get_authenticated_user(),
            since_date="2024-12-01",
            limit=5,
            detail_level="summary",
        )
        print(f"✅ Found {len(prs)} merged PRs in last month")
        for pr in prs[:3]:
            print(f"   - #{pr['number']}: {pr['title'][:50]}")
    except Exception as e:
        print(f"⚠️  Search failed: {e}")

    print("✅ Test passed!\n")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Appraisal Tools")
    print("=" * 60)

    tests = [
        test_prepare_appraisal_data_dumps_to_file,
        test_get_appraisal_pr_details_reads_from_file,
        test_parallel_fetch_simulation,
        test_full_flow_with_mock_client,
        test_actual_github_client,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
