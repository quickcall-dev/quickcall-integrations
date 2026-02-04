#!/usr/bin/env python3
"""
Integration test for Pull Request Management.

This test performs a full round-trip:
1. Creates a test branch
2. Creates a test PR (auto-assigns to self)
3. Views the PR
4. Updates PR (title, body)
5. Adds/removes labels
6. Adds/removes assignees
7. Converts to draft and back
8. Requests reviewers (if available)
9. Adds a comment
10. Closes the PR
11. Cleans up branch

Run with: uv run python tests/test_pr_integration.py

Requires:
- GITHUB_TOKEN env var or .quickcall.env with GitHub PAT
- Access to quickcall-dev/quickcall-integrations repo
"""

import sys
import time
import secrets


def run_integration_test():
    """Run the full PR management integration test."""
    from mcp_server.api_clients.github_client import GitHubClient
    from mcp_server.auth import get_github_pat

    print("=" * 60)
    print("Pull Request Management Integration Test")
    print("=" * 60)

    # Check for credentials
    pat_token, source = get_github_pat()
    if not pat_token:
        print("\n❌ No GitHub PAT found!")
        print("   Set GITHUB_TOKEN env var or create .quickcall.env")
        return False

    print(f"\n✅ Using PAT from: {source}")

    client = GitHubClient(token=pat_token)
    username = client.get_authenticated_user()
    print(f"✅ Authenticated as: {username}")

    # Configuration for test
    TEST_ORG = "quickcall-dev"
    TEST_REPO = "quickcall-integrations"
    TEST_BRANCH = f"test/pr-integration-{secrets.token_hex(4)}"
    TEST_PR_TITLE = "[TEST] PR Integration Test - Safe to Delete"

    created_pr_number = None

    try:
        # Step 1: Create a test branch from main
        print(f"\n--- Step 1: Create test branch '{TEST_BRANCH}' ---")

        # Get the default branch SHA
        branches = client.list_branches(owner=TEST_ORG, repo=TEST_REPO)
        main_sha = None
        for branch in branches:
            if branch["name"] == "main":
                main_sha = branch["sha"]
                break

        if not main_sha:
            print("❌ Could not find main branch")
            return False

        print(f"✅ Found main branch at SHA: {main_sha[:7]}")

        # Create branch via Git refs API (need to use httpx directly)
        import httpx

        with httpx.Client() as http_client:
            response = http_client.post(
                f"https://api.github.com/repos/{TEST_ORG}/{TEST_REPO}/git/refs",
                headers={
                    "Authorization": f"Bearer {pat_token}",
                    "Accept": "application/vnd.github+json",
                },
                json={
                    "ref": f"refs/heads/{TEST_BRANCH}",
                    "sha": main_sha,
                },
            )
            if response.status_code == 201:
                print(f"✅ Created branch: {TEST_BRANCH}")
            elif response.status_code == 422:
                print("⚠️  Branch already exists, using it")
            else:
                print(f"❌ Failed to create branch: {response.status_code}")
                print(response.json())
                return False

        # Small delay for GitHub
        time.sleep(1)

        # Step 2: Create a test PR (should auto-assign to self)
        print("\n--- Step 2: Create test PR ---")
        pr = client.create_pr(
            title=TEST_PR_TITLE,
            head=TEST_BRANCH,
            base="main",
            body="This is an automated test PR for PR management integration.\n\n"
            "**This PR will be closed automatically after the test.**",
            draft=True,
            owner=TEST_ORG,
            repo=TEST_REPO,
        )
        created_pr_number = pr.number
        print(f"✅ Created PR #{created_pr_number}: {pr.title}")
        print(f"   URL: {pr.html_url}")
        print(f"   Draft: {pr.draft}")

        # Step 3: Auto-assign to self
        print(f"\n--- Step 3: Assign PR to self ({username}) ---")
        assign_result = client.add_pr_assignees(
            created_pr_number,
            assignees=[username],
            owner=TEST_ORG,
            repo=TEST_REPO,
        )
        print(f"✅ Assigned to: {assign_result['assignees']}")

        # Step 4: View PR
        print(f"\n--- Step 4: View PR #{created_pr_number} ---")
        viewed_pr = client.get_pr(created_pr_number, owner=TEST_ORG, repo=TEST_REPO)
        if viewed_pr:
            print(f"✅ Viewed PR #{viewed_pr.number}")
            print(f"   Title: {viewed_pr.title}")
            print(f"   State: {viewed_pr.state}")
            print(f"   Draft: {viewed_pr.draft}")
        else:
            print("❌ Could not view PR")
            return False

        # Step 5: Update PR
        print("\n--- Step 5: Update PR title and body ---")
        updated_pr = client.update_pr(
            created_pr_number,
            title=f"{TEST_PR_TITLE} (Updated)",
            body="Updated body.\n\n**This PR will be closed automatically.**",
            owner=TEST_ORG,
            repo=TEST_REPO,
        )
        print(f"✅ Updated PR title: {updated_pr.title}")

        # Step 6: Add labels
        print("\n--- Step 6: Add labels ---")
        label_result = client.add_pr_labels(
            created_pr_number,
            labels=["test"],
            owner=TEST_ORG,
            repo=TEST_REPO,
        )
        print(f"✅ Added labels: {label_result['labels']}")

        # Step 7: Mark ready for review
        print("\n--- Step 7: Mark ready for review ---")
        ready_result = client.mark_pr_ready_for_review(
            created_pr_number,
            owner=TEST_ORG,
            repo=TEST_REPO,
        )
        print(f"✅ {ready_result['message']}")
        print(f"   is_draft: {ready_result['is_draft']}")

        time.sleep(1)

        # Step 8: Convert back to draft
        print("\n--- Step 8: Convert back to draft ---")
        draft_result = client.convert_pr_to_draft(
            created_pr_number,
            owner=TEST_ORG,
            repo=TEST_REPO,
        )
        print(f"✅ {draft_result['message']}")
        print(f"   is_draft: {draft_result['is_draft']}")

        # Step 9: Add a comment
        print("\n--- Step 9: Add comment ---")
        comment = client.add_pr_comment(
            created_pr_number,
            body="This is an automated test comment.",
            owner=TEST_ORG,
            repo=TEST_REPO,
        )
        print(f"✅ Added comment: {comment['html_url']}")

        # Step 10: Close the PR
        print(f"\n--- Step 10: Close PR #{created_pr_number} ---")
        client.close_pr(created_pr_number, owner=TEST_ORG, repo=TEST_REPO)
        print(f"✅ Closed PR #{created_pr_number}")

        # Step 11: Clean up branch
        print(f"\n--- Step 11: Clean up branch '{TEST_BRANCH}' ---")
        with httpx.Client() as http_client:
            response = http_client.delete(
                f"https://api.github.com/repos/{TEST_ORG}/{TEST_REPO}/git/refs/heads/{TEST_BRANCH}",
                headers={
                    "Authorization": f"Bearer {pat_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            if response.status_code == 204:
                print(f"✅ Deleted branch: {TEST_BRANCH}")
            else:
                print(f"⚠️  Could not delete branch: {response.status_code}")

        print("\n" + "=" * 60)
        print("✅ ALL PR INTEGRATION TESTS PASSED!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()

        # Cleanup: try to close the PR and delete branch
        if created_pr_number:
            try:
                print(f"\n--- Cleanup: Closing PR #{created_pr_number} ---")
                client.close_pr(created_pr_number, owner=TEST_ORG, repo=TEST_REPO)
                print(f"✅ Closed PR #{created_pr_number}")
            except Exception as cleanup_error:
                print(f"⚠️  PR cleanup failed: {cleanup_error}")

        try:
            import httpx

            with httpx.Client() as http_client:
                http_client.delete(
                    f"https://api.github.com/repos/{TEST_ORG}/{TEST_REPO}/git/refs/heads/{TEST_BRANCH}",
                    headers={
                        "Authorization": f"Bearer {pat_token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
        except Exception:
            pass

        return False


def test_pr_list():
    """Test listing PRs."""
    from mcp_server.api_clients.github_client import GitHubClient
    from mcp_server.auth import get_github_pat

    print("\n" + "=" * 60)
    print("Test: List PRs")
    print("=" * 60)

    pat_token, _ = get_github_pat()
    if not pat_token:
        print("⚠️  Skipping - no PAT")
        return True

    client = GitHubClient(token=pat_token)

    TEST_ORG = "quickcall-dev"
    TEST_REPO = "quickcall-integrations"

    # Test list open PRs
    print("\nListing open PRs...")
    prs = client.list_prs(owner=TEST_ORG, repo=TEST_REPO, state="open", limit=5)
    print(f"✅ Found {len(prs)} open PR(s)")
    for pr in prs:
        print(f"   #{pr.number}: {pr.title}")

    # Test list closed PRs
    print("\nListing closed PRs...")
    prs = client.list_prs(owner=TEST_ORG, repo=TEST_REPO, state="closed", limit=5)
    print(f"✅ Found {len(prs)} closed PR(s)")

    print("\n✅ PR listing test passed!")
    return True


def test_error_handling():
    """Test error handling for invalid PR operations."""
    from mcp_server.api_clients.github_client import GitHubClient
    from github import GithubException
    from mcp_server.auth import get_github_pat

    print("\n" + "=" * 60)
    print("Test: Error Handling")
    print("=" * 60)

    pat_token, _ = get_github_pat()
    if not pat_token:
        print("⚠️  Skipping - no PAT")
        return True

    client = GitHubClient(token=pat_token)

    # Test 1: Non-existent PR
    print("\nTest 1: Get non-existent PR")
    pr = client.get_pr(999999, owner="quickcall-dev", repo="quickcall-integrations")
    if pr is None:
        print("✅ Correctly returned None for non-existent PR")
    else:
        print(f"❌ Expected None, got: {pr}")
        return False

    # Test 2: Merge non-existent PR should fail
    print("\nTest 2: Merge non-existent PR")
    try:
        client.merge_pr(
            999999,
            owner="quickcall-dev",
            repo="quickcall-integrations",
        )
        print("❌ Should have raised an exception")
        return False
    except GithubException as e:
        print(f"✅ Correctly raised GithubException: {e.status}")

    print("\n✅ All error handling tests passed!")
    return True


if __name__ == "__main__":
    results = []

    # Run main integration test
    results.append(("Full PR Integration Test", run_integration_test()))

    # Run additional tests
    results.append(("List PRs", test_pr_list()))
    results.append(("Error Handling", test_error_handling()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    all_passed = True
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print("=" * 60)
    sys.exit(0 if all_passed else 1)
