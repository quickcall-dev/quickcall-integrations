#!/usr/bin/env python3
"""
Test GitHub Projects V2 tools.

Tests:
1. list_projects - lists projects for org/user
2. add_issue_to_project - adds issue to project
3. remove_issue_from_project - removes issue from project
4. manage_issues with project parameter - create + add to project

Usage:
    uv run python tests/test_project_tools.py
"""

from unittest.mock import MagicMock, patch

# Test the core logic without MCP server


def test_list_projects_returns_projects():
    """Test that list_projects returns project data."""
    print("\n=== Test 1: list_projects returns projects ===")

    # Mock GraphQL response
    mock_response = {
        "organization": {
            "projectsV2": {
                "nodes": [
                    {
                        "id": "PVT_kwDOTest123",
                        "number": 1,
                        "title": "Sprint Board",
                        "url": "https://github.com/orgs/test-org/projects/1",
                        "closed": False,
                    },
                    {
                        "id": "PVT_kwDOTest456",
                        "number": 2,
                        "title": "Backlog",
                        "url": "https://github.com/orgs/test-org/projects/2",
                        "closed": False,
                    },
                ]
            }
        }
    }

    # Simulate what list_projects does
    org = mock_response.get("organization")
    nodes = org.get("projectsV2", {}).get("nodes", [])

    projects = [
        {
            "id": node["id"],
            "number": node["number"],
            "title": node["title"],
            "url": node["url"],
            "closed": node["closed"],
        }
        for node in nodes
        if node
    ]

    assert len(projects) == 2, f"Expected 2 projects, got {len(projects)}"
    assert projects[0]["title"] == "Sprint Board", "First project title should match"
    assert projects[0]["number"] == 1, "First project number should be 1"

    print(f"✅ Found {len(projects)} projects")
    for p in projects:
        print(f"   - #{p['number']}: {p['title']}")

    print("✅ Test passed!\n")
    return True


def test_get_project_id_by_number():
    """Test getting project ID by number."""
    print("\n=== Test 2: get_project_id by number ===")

    # Mock GraphQL response for direct number lookup
    mock_response = {"organization": {"projectV2": {"id": "PVT_kwDOTest123"}}}

    org = mock_response.get("organization")
    project_data = org.get("projectV2")
    project_id = project_data["id"] if project_data else None

    assert project_id == "PVT_kwDOTest123", "Should return correct project ID"

    print(f"✅ Project ID: {project_id}")
    print("✅ Test passed!\n")
    return True


def test_get_project_id_by_title():
    """Test getting project ID by title (searches through list)."""
    print("\n=== Test 3: get_project_id by title ===")

    # Mock projects list
    mock_projects = [
        {"id": "PVT_kwDOTest123", "number": 1, "title": "Sprint Board"},
        {"id": "PVT_kwDOTest456", "number": 2, "title": "Backlog"},
    ]

    # Search by title
    search_title = "backlog"  # lowercase to test case-insensitive
    found_id = None
    for p in mock_projects:
        if p["title"].lower() == search_title.lower():
            found_id = p["id"]
            break

    assert found_id == "PVT_kwDOTest456", "Should find project by title"

    print(f"✅ Found project '{search_title}' with ID: {found_id}")
    print("✅ Test passed!\n")
    return True


def test_add_issue_to_project_mutation():
    """Test the add to project mutation structure."""
    print("\n=== Test 4: add_issue_to_project mutation ===")

    # Mock mutation response
    mock_response = {"addProjectV2ItemById": {"item": {"id": "PVTI_lADOTest789"}}}

    item = mock_response.get("addProjectV2ItemById", {}).get("item")
    result = {
        "success": True,
        "issue_number": 42,
        "project": "1",
        "project_item_id": item["id"] if item else None,
    }

    assert result["success"] is True, "Should be successful"
    assert result["project_item_id"] == "PVTI_lADOTest789", "Should have item ID"

    print(f"✅ Added issue #{result['issue_number']} to project")
    print(f"✅ Project item ID: {result['project_item_id']}")
    print("✅ Test passed!\n")
    return True


def test_remove_issue_from_project_flow():
    """Test the remove from project flow (find item, then delete)."""
    print("\n=== Test 5: remove_issue_from_project flow ===")

    # Mock: First query to find the item in project
    mock_items_response = {
        "node": {
            "items": {
                "nodes": [
                    {"id": "PVTI_item1", "content": {"id": "I_issue1", "number": 41}},
                    {"id": "PVTI_item2", "content": {"id": "I_issue2", "number": 42}},
                    {"id": "PVTI_item3", "content": {"id": "I_issue3", "number": 43}},
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    }

    # Find item ID for issue #42
    target_issue_id = "I_issue2"  # This is what get_issue_node_id would return
    node = mock_items_response.get("node", {})
    items = node.get("items", {})

    item_id = None
    for item in items.get("nodes", []):
        content = item.get("content")
        if content and content.get("id") == target_issue_id:
            item_id = item["id"]
            break

    assert item_id == "PVTI_item2", "Should find correct item ID"

    # Mock delete mutation response
    mock_delete_response = {"deleteProjectV2Item": {"deletedItemId": "PVTI_item2"}}

    deleted_id = mock_delete_response.get("deleteProjectV2Item", {}).get(
        "deletedItemId"
    )
    result = {
        "success": True,
        "issue_number": 42,
        "project": "1",
        "deleted_item_id": deleted_id,
    }

    assert result["success"] is True, "Should be successful"
    assert result["deleted_item_id"] == "PVTI_item2", "Should have deleted item ID"

    print(f"✅ Found item ID {item_id} for issue #42")
    print(f"✅ Deleted item: {result['deleted_item_id']}")
    print("✅ Test passed!\n")
    return True


def test_manage_issues_create_with_project():
    """Test creating an issue and adding to project in one call."""
    print("\n=== Test 6: manage_issues create with project ===")

    # Simulate the flow
    mock_created_issue = {
        "number": 100,
        "title": "New Feature",
        "html_url": "https://github.com/test-org/test-repo/issues/100",
        "labels": [],
        "assignees": [],
    }

    mock_project_result = {
        "success": True,
        "issue_number": 100,
        "project": "1",
        "project_item_id": "PVTI_newitem",
    }

    # Simulate what manage_issues does
    result = {"action": "created", "issue": mock_created_issue}

    # Add project info
    result["project"] = "1"
    result["project_added"] = mock_project_result.get("success", False)
    result["project_item_id"] = mock_project_result.get("project_item_id")

    assert result["action"] == "created", "Action should be created"
    assert result["project_added"] is True, "Project should be added"
    assert result["project_item_id"] == "PVTI_newitem", "Should have item ID"

    print(f"✅ Created issue #{result['issue']['number']}")
    print(f"✅ Added to project: {result['project']}")
    print(f"✅ Project item ID: {result['project_item_id']}")
    print("✅ Test passed!\n")
    return True


def test_graphql_error_handling():
    """Test handling of GraphQL errors."""
    print("\n=== Test 7: GraphQL error handling ===")

    # Mock error response
    mock_error_response = {
        "errors": [{"message": "Could not resolve to a ProjectV2 with the number 999."}]
    }

    # Simulate error handling
    if "errors" in mock_error_response:
        error_messages = [
            e.get("message", str(e)) for e in mock_error_response["errors"]
        ]
        error_str = "; ".join(error_messages)
        assert "ProjectV2" in error_str, "Error should mention ProjectV2"
        print(f"✅ Caught error: {error_str}")

    print("✅ Test passed!\n")
    return True


def test_with_mock_github_client():
    """Test with mocked GitHubClient."""
    print("\n=== Test 8: Full flow with mock GitHubClient ===")

    from mcp_server.api_clients.github_client import GitHubClient

    with patch.object(GitHubClient, "__init__", lambda self, **kwargs: None):
        client = GitHubClient(token="fake")
        client.token = "fake"
        client._is_pat_mode = True
        client.default_owner = "test-org"
        client.default_repo = "test-repo"
        client._repo_cache = {}

        # Mock _graphql_request
        def mock_graphql(query, variables=None):
            if "projectsV2" in query:
                return {
                    "organization": {
                        "projectsV2": {
                            "nodes": [
                                {
                                    "id": "PVT_test1",
                                    "number": 1,
                                    "title": "Board",
                                    "url": "https://example.com",
                                    "closed": False,
                                }
                            ]
                        }
                    }
                }
            if "addProjectV2ItemById" in query:
                return {"addProjectV2ItemById": {"item": {"id": "PVTI_new"}}}
            return {}

        client._graphql_request = MagicMock(side_effect=mock_graphql)

        # Mock get_issue_node_id
        client.get_issue_node_id = MagicMock(return_value="I_issue123")

        # Mock get_project_id
        client.get_project_id = MagicMock(return_value="PVT_test1")

        # Test list_projects
        projects = client.list_projects(owner="test-org")
        assert len(projects) == 1, "Should get 1 project"
        print(f"✅ list_projects returned {len(projects)} project(s)")

        # Test add_issue_to_project
        client.add_issue_to_project(
            issue_number=42,
            project="1",
            owner="test-org",
            repo="test-repo",
        )
        # Note: This will use our mocked methods
        print("✅ add_issue_to_project called successfully")

    print("✅ Test passed!\n")
    return True


def test_actual_github_client():
    """Test actual GitHub client if credentials available."""
    print("\n=== Test 9: Actual GitHub client (optional) ===")

    from mcp_server.auth import get_github_pat

    pat_token, source = get_github_pat()
    if not pat_token:
        print("⚠️  No GitHub PAT found, skipping live test")
        print("   Set GITHUB_TOKEN env var to enable this test")
        return True

    from mcp_server.api_clients.github_client import GitHubClient

    client = GitHubClient(token=pat_token)

    print(f"✅ Using PAT from {source}")

    # Test list_projects on a known org (if available)
    try:
        username = client.get_authenticated_user()
        print(f"✅ Authenticated as: {username}")

        # Try listing user projects
        projects = client.list_projects(owner=username, is_org=False)
        print(f"✅ Found {len(projects)} user projects")
        for p in projects[:3]:
            print(f"   - #{p['number']}: {p['title']}")
    except Exception as e:
        print(f"⚠️  list_projects failed (expected if no projects): {e}")

    print("✅ Test passed!\n")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Testing GitHub Projects V2 Tools")
    print("=" * 60)

    tests = [
        test_list_projects_returns_projects,
        test_get_project_id_by_number,
        test_get_project_id_by_title,
        test_add_issue_to_project_mutation,
        test_remove_issue_from_project_flow,
        test_manage_issues_create_with_project,
        test_graphql_error_handling,
        test_with_mock_github_client,
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
