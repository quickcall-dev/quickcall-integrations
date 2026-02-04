#!/usr/bin/env python3
"""
Integration test for Issue Comment Management.

This test performs a full round-trip:
1. Creates a test issue
2. Adds multiple comments
3. Lists comments (asc and desc order)
4. Updates a comment
5. Deletes a comment
6. Closes/cleans up the test issue

Run with: uv run python tests/test_comment_management.py

Requires:
- GITHUB_TOKEN env var or .quickcall.env with GitHub PAT
- Access to quickcall-dev/quickcall-integrations repo
"""

import sys
import time


def run_integration_test():
    """Run the full comment management integration test."""
    from mcp_server.api_clients.github_client import GitHubClient
    from mcp_server.auth import get_github_pat

    print("=" * 60)
    print("Issue Comment Management Integration Test")
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
    TEST_ISSUE_TITLE = "[TEST] Comment Management Test - Safe to Delete"

    created_issue_number = None
    comment_ids = []

    try:
        # Step 1: Create a test issue
        print("\n--- Step 1: Create test issue ---")
        issue = client.create_issue(
            title=TEST_ISSUE_TITLE,
            body="This is an automated test issue for comment management.\n\n"
            "**This issue will be closed automatically after the test.**",
            labels=["test"],
            owner=TEST_ORG,
            repo=TEST_REPO,
        )
        created_issue_number = issue["number"]
        print(f"✅ Created issue #{created_issue_number}")
        print(f"   URL: {issue['html_url']}")

        time.sleep(1)

        # Step 2: Add multiple comments
        print("\n--- Step 2: Add 3 comments ---")
        for i in range(1, 4):
            comment = client.comment_on_issue(
                issue_number=created_issue_number,
                body=f"Test comment #{i}",
                owner=TEST_ORG,
                repo=TEST_REPO,
            )
            comment_ids.append(comment["id"])
            print(f"✅ Added comment #{i} (ID: {comment['id']})")
            time.sleep(0.5)

        # Step 3: List comments (ascending - oldest first)
        print("\n--- Step 3: List comments (oldest first) ---")
        comments_asc = client.list_issue_comments(
            issue_number=created_issue_number,
            owner=TEST_ORG,
            repo=TEST_REPO,
            limit=10,
            order="asc",
        )
        print(f"✅ Found {len(comments_asc)} comments (asc)")
        for c in comments_asc:
            print(f"   - {c['body'][:50]} (by {c['author']})")

        # Step 4: List comments (descending - newest first)
        print("\n--- Step 4: List comments (newest first) ---")
        comments_desc = client.list_issue_comments(
            issue_number=created_issue_number,
            owner=TEST_ORG,
            repo=TEST_REPO,
            limit=10,
            order="desc",
        )
        print(f"✅ Found {len(comments_desc)} comments (desc)")
        for c in comments_desc:
            print(f"   - {c['body'][:50]} (by {c['author']})")

        # Verify order is reversed
        if comments_asc and comments_desc:
            assert comments_asc[0]["id"] == comments_desc[-1]["id"], (
                "Order should be reversed"
            )
            print("✅ Order verification passed")

        # Step 5: List with limit
        print("\n--- Step 5: List with limit=2 ---")
        comments_limited = client.list_issue_comments(
            issue_number=created_issue_number,
            owner=TEST_ORG,
            repo=TEST_REPO,
            limit=2,
            order="asc",
        )
        print(f"✅ Found {len(comments_limited)} comments (limited to 2)")
        assert len(comments_limited) == 2, "Should return exactly 2 comments"

        # Step 6: Update a comment
        print("\n--- Step 6: Update comment ---")
        comment_to_update = comment_ids[1]  # Update the second comment
        updated = client.update_issue_comment(
            comment_id=comment_to_update,
            body="Test comment #2 (UPDATED)",
            owner=TEST_ORG,
            repo=TEST_REPO,
        )
        print(f"✅ Updated comment ID {comment_to_update}")
        print(f"   New body: {updated['body']}")
        assert "UPDATED" in updated["body"], "Comment should be updated"

        # Step 7: Get specific comment
        print("\n--- Step 7: Get specific comment ---")
        fetched = client.get_issue_comment(
            comment_id=comment_to_update,
            owner=TEST_ORG,
            repo=TEST_REPO,
        )
        print(f"✅ Fetched comment ID {fetched['id']}")
        print(f"   Body: {fetched['body']}")

        # Step 8: Delete a comment
        print("\n--- Step 8: Delete comment ---")
        comment_to_delete = comment_ids[2]  # Delete the third comment
        result = client.delete_issue_comment(
            comment_id=comment_to_delete,
            owner=TEST_ORG,
            repo=TEST_REPO,
        )
        print(f"✅ Deleted comment ID {comment_to_delete}")
        assert result["deleted"] is True, "Should return deleted=True"

        # Verify deletion
        time.sleep(1)
        comments_after = client.list_issue_comments(
            issue_number=created_issue_number,
            owner=TEST_ORG,
            repo=TEST_REPO,
            limit=10,
        )
        print(f"✅ Verified: now {len(comments_after)} comments (was 3)")
        assert len(comments_after) == 2, "Should have 2 comments after deletion"

        # Step 9: Cleanup - close issue
        print("\n--- Step 9: Close test issue ---")
        client.close_issue(created_issue_number, owner=TEST_ORG, repo=TEST_REPO)
        print(f"✅ Closed issue #{created_issue_number}")

        print("\n" + "=" * 60)
        print("✅ ALL COMMENT MANAGEMENT TESTS PASSED!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()

        # Cleanup
        if created_issue_number:
            try:
                print(f"\n--- Cleanup: Closing issue #{created_issue_number} ---")
                client.close_issue(created_issue_number, owner=TEST_ORG, repo=TEST_REPO)
                print(f"✅ Closed issue #{created_issue_number}")
            except Exception as cleanup_error:
                print(f"⚠️  Cleanup failed: {cleanup_error}")

        return False


def test_error_handling():
    """Test error handling for invalid comment operations."""
    from mcp_server.api_clients.github_client import GitHubClient
    from github import GithubException, UnknownObjectException
    from mcp_server.auth import get_github_pat

    print("\n" + "=" * 60)
    print("Test: Error Handling")
    print("=" * 60)

    pat_token, _ = get_github_pat()
    if not pat_token:
        print("⚠️  Skipping - no PAT")
        return True

    client = GitHubClient(token=pat_token)

    # Test 1: Get non-existent comment
    print("\nTest 1: Get non-existent comment")
    try:
        client.get_issue_comment(
            comment_id=999999999,
            owner="quickcall-dev",
            repo="quickcall-integrations",
        )
        print("❌ Should have raised an exception")
        return False
    except (GithubException, UnknownObjectException):
        print("✅ Correctly raised exception for non-existent comment")

    # Test 2: Update non-existent comment
    print("\nTest 2: Update non-existent comment")
    try:
        client.update_issue_comment(
            comment_id=999999999,
            body="test",
            owner="quickcall-dev",
            repo="quickcall-integrations",
        )
        print("❌ Should have raised an exception")
        return False
    except (GithubException, UnknownObjectException):
        print("✅ Correctly raised exception for update")

    print("\n✅ All error handling tests passed!")
    return True


if __name__ == "__main__":
    results = []

    # Run main integration test
    results.append(("Full Comment Management Test", run_integration_test()))

    # Run error handling test
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
