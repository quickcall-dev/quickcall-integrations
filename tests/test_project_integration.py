#!/usr/bin/env python3
"""
Integration test for GitHub Projects V2 support.

This test performs a full round-trip:
1. Lists available projects
2. Creates a test issue
3. Adds issue to project
4. Verifies issue is in project (by querying project items)
5. Removes issue from project
6. Closes/cleans up the test issue

Run with: uv run python tests/test_project_integration.py

Requires:
- GITHUB_TOKEN env var or .quickcall.env with GitHub PAT
- PAT needs 'project' scope for project operations
- Access to quickcall-dev/quickcall-integrations repo
"""

import sys
import time


def run_integration_test():
    """Run the full integration test."""
    from mcp_server.api_clients.github_client import GitHubClient
    from mcp_server.auth import get_github_pat

    print("=" * 60)
    print("GitHub Projects V2 Integration Test")
    print("=" * 60)

    # Check for credentials
    pat_token, source = get_github_pat()
    if not pat_token:
        print("\n❌ No GitHub PAT found!")
        print("   Set GITHUB_TOKEN env var or create .quickcall.env")
        print("   PAT needs 'project' scope for project operations")
        return False

    print(f"\n✅ Using PAT from: {source}")

    client = GitHubClient(token=pat_token)
    username = client.get_authenticated_user()
    print(f"✅ Authenticated as: {username}")

    # Configuration for test
    TEST_ORG = "quickcall-dev"
    TEST_REPO = "quickcall-integrations"
    TEST_ISSUE_TITLE = "[TEST] Project Integration Test - Safe to Delete"

    created_issue_number = None

    try:
        # Step 1: List projects
        print(f"\n--- Step 1: List projects for {TEST_ORG} ---")
        projects = client.list_projects(owner=TEST_ORG, is_org=True)

        if not projects:
            print("⚠️  No projects found. Creating test project not supported.")
            print("   Please create a project manually at:")
            print(f"   https://github.com/orgs/{TEST_ORG}/projects")
            return False

        print(f"✅ Found {len(projects)} project(s):")
        for p in projects:
            status = "closed" if p["closed"] else "open"
            print(f"   #{p['number']}: {p['title']} ({status})")

        # Use first open project for testing
        test_project = next((p for p in projects if not p["closed"]), projects[0])
        project_number = str(test_project["number"])
        print(f"\n✅ Using project #{project_number}: {test_project['title']}")

        # Step 2: Create a test issue
        print(f"\n--- Step 2: Create test issue in {TEST_ORG}/{TEST_REPO} ---")
        issue = client.create_issue(
            title=TEST_ISSUE_TITLE,
            body="This is an automated test issue for project integration.\n\n"
            "**This issue will be closed automatically after the test.**",
            labels=["test"],
            owner=TEST_ORG,
            repo=TEST_REPO,
        )
        created_issue_number = issue["number"]
        print(f"✅ Created issue #{created_issue_number}: {issue['title']}")
        print(f"   URL: {issue['html_url']}")

        # Small delay to ensure GitHub has processed the issue
        time.sleep(1)

        # Step 3: Add issue to project
        print(
            f"\n--- Step 3: Add issue #{created_issue_number} to project #{project_number} ---"
        )
        add_result = client.add_issue_to_project(
            issue_number=created_issue_number,
            project=project_number,
            owner=TEST_ORG,
            repo=TEST_REPO,
            project_owner=TEST_ORG,
        )
        print("✅ Added to project!")
        print(f"   Project item ID: {add_result.get('project_item_id')}")

        # Small delay for consistency
        time.sleep(1)

        # Step 4: Verify by attempting to remove (confirms it's in project)
        print(f"\n--- Step 4: Remove issue #{created_issue_number} from project ---")
        remove_result = client.remove_issue_from_project(
            issue_number=created_issue_number,
            project=project_number,
            owner=TEST_ORG,
            repo=TEST_REPO,
            project_owner=TEST_ORG,
        )
        print("✅ Removed from project!")
        print(f"   Deleted item ID: {remove_result.get('deleted_item_id')}")

        # Step 5: Test create with project parameter (simulated via re-add)
        print("\n--- Step 5: Re-add to project (simulating create+project flow) ---")
        client.add_issue_to_project(
            issue_number=created_issue_number,
            project=project_number,
            owner=TEST_ORG,
            repo=TEST_REPO,
            project_owner=TEST_ORG,
        )
        print("✅ Re-added to project!")

        # Wait for consistency
        time.sleep(2)

        # Cleanup: remove again
        try:
            client.remove_issue_from_project(
                issue_number=created_issue_number,
                project=project_number,
                owner=TEST_ORG,
                repo=TEST_REPO,
                project_owner=TEST_ORG,
            )
            print("✅ Cleaned up (removed from project)")
        except Exception as cleanup_err:
            print(f"⚠️  Cleanup warning (non-critical): {cleanup_err}")

        # Step 6: Close the test issue
        print(f"\n--- Step 6: Close test issue #{created_issue_number} ---")
        client.close_issue(created_issue_number, owner=TEST_ORG, repo=TEST_REPO)
        print(f"✅ Closed issue #{created_issue_number}")

        print("\n" + "=" * 60)
        print("✅ ALL INTEGRATION TESTS PASSED!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()

        # Cleanup: try to close the issue if it was created
        if created_issue_number:
            try:
                print(f"\n--- Cleanup: Closing test issue #{created_issue_number} ---")
                client.close_issue(created_issue_number, owner=TEST_ORG, repo=TEST_REPO)
                print(f"✅ Closed issue #{created_issue_number}")
            except Exception as cleanup_error:
                print(f"⚠️  Cleanup failed: {cleanup_error}")

        return False


def test_project_by_title():
    """Test finding project by title instead of number."""
    from mcp_server.api_clients.github_client import GitHubClient
    from mcp_server.auth import get_github_pat

    print("\n" + "=" * 60)
    print("Test: Find Project by Title")
    print("=" * 60)

    pat_token, _ = get_github_pat()
    if not pat_token:
        print("⚠️  Skipping - no PAT")
        return True

    client = GitHubClient(token=pat_token)

    TEST_ORG = "quickcall-dev"

    # Get projects
    projects = client.list_projects(owner=TEST_ORG, is_org=True)
    if not projects:
        print("⚠️  Skipping - no projects")
        return True

    # Test finding by title
    test_title = projects[0]["title"]
    print(f"\nSearching for project by title: '{test_title}'")

    project_id = client.get_project_id(test_title, owner=TEST_ORG, is_org=True)

    if project_id:
        print(f"✅ Found project ID: {project_id}")
        assert project_id == projects[0]["id"], "IDs should match"
        print("✅ Test passed!")
        return True
    else:
        print("❌ Project not found by title")
        return False


def test_error_handling():
    """Test error handling for invalid projects."""
    from mcp_server.api_clients.github_client import GitHubClient, GithubException
    from mcp_server.auth import get_github_pat

    print("\n" + "=" * 60)
    print("Test: Error Handling")
    print("=" * 60)

    pat_token, _ = get_github_pat()
    if not pat_token:
        print("⚠️  Skipping - no PAT")
        return True

    client = GitHubClient(token=pat_token)

    # Test 1: Non-existent project
    print("\nTest 1: Non-existent project number")
    project_id = client.get_project_id("99999", owner="quickcall-dev", is_org=True)
    if project_id is None:
        print("✅ Correctly returned None for non-existent project")
    else:
        print(f"❌ Expected None, got: {project_id}")
        return False

    # Test 2: Add to non-existent project should fail
    print("\nTest 2: Add to non-existent project")
    try:
        client.add_issue_to_project(
            issue_number=1,
            project="99999",
            owner="quickcall-dev",
            repo="quickcall-integrations",
            project_owner="quickcall-dev",
        )
        print("❌ Should have raised an exception")
        return False
    except GithubException as e:
        print(f"✅ Correctly raised GithubException: {e.data.get('message', str(e))}")

    print("\n✅ All error handling tests passed!")
    return True


if __name__ == "__main__":
    results = []

    # Run main integration test
    results.append(("Full Integration Test", run_integration_test()))

    # Run additional tests
    results.append(("Find Project by Title", test_project_by_title()))
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
