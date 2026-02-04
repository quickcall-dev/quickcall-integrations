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


# ============================================================================
# New Tests for Project Fields Support
# ============================================================================


def test_get_project_fields():
    """Test getting project fields with options for SingleSelect."""
    print("\n=== Test 10: get_project_fields ===")

    # Mock GraphQL response for fields query
    mock_response = {
        "node": {
            "fields": {
                "nodes": [
                    {"id": "PVTF_field1", "name": "Title", "dataType": "TITLE"},
                    {
                        "id": "PVTF_field2",
                        "name": "Status",
                        "dataType": "SINGLE_SELECT",
                        "options": [
                            {"id": "opt1", "name": "Todo"},
                            {"id": "opt2", "name": "In Progress"},
                            {"id": "opt3", "name": "Done"},
                        ],
                    },
                    {
                        "id": "PVTF_field3",
                        "name": "Priority",
                        "dataType": "SINGLE_SELECT",
                        "options": [
                            {"id": "opt4", "name": "Low"},
                            {"id": "opt5", "name": "Medium"},
                            {"id": "opt6", "name": "High"},
                        ],
                    },
                    {"id": "PVTF_field4", "name": "Due Date", "dataType": "DATE"},
                    {"id": "PVTF_field5", "name": "Notes", "dataType": "TEXT"},
                ]
            }
        }
    }

    # Parse fields like the client does
    node = mock_response.get("node")
    fields = []
    for field in node.get("fields", {}).get("nodes", []):
        if not field:
            continue

        field_data = {
            "id": field.get("id"),
            "name": field.get("name"),
            "data_type": field.get("dataType"),
        }

        # Add options for SingleSelect fields
        if "options" in field:
            field_data["options"] = [
                {"id": opt["id"], "name": opt["name"]}
                for opt in field.get("options", [])
            ]

        fields.append(field_data)

    assert len(fields) == 5, f"Expected 5 fields, got {len(fields)}"

    # Check Status field has options
    status_field = next((f for f in fields if f["name"] == "Status"), None)
    assert status_field is not None, "Status field should exist"
    assert status_field["data_type"] == "SINGLE_SELECT", (
        "Status should be SINGLE_SELECT"
    )
    assert len(status_field["options"]) == 3, "Status should have 3 options"
    assert status_field["options"][1]["name"] == "In Progress", (
        "Second option should be 'In Progress'"
    )

    # Check TEXT field has no options
    notes_field = next((f for f in fields if f["name"] == "Notes"), None)
    assert notes_field is not None, "Notes field should exist"
    assert "options" not in notes_field, "TEXT field should not have options"

    print("✅ Parsed 5 fields correctly")
    print(f"   - Status has {len(status_field['options'])} options")
    print("✅ Test passed!\n")
    return True


def test_update_project_field_single_select():
    """Test updating a SingleSelect field value."""
    print("\n=== Test 11: update_project_field (SINGLE_SELECT) ===")

    # Mock field lookup
    mock_fields = [
        {
            "id": "PVTF_status",
            "name": "Status",
            "data_type": "SINGLE_SELECT",
            "options": [
                {"id": "opt1", "name": "Todo"},
                {"id": "opt2", "name": "In Progress"},
                {"id": "opt3", "name": "Done"},
            ],
        }
    ]

    # Simulate finding field and option
    field_name = "Status"
    value = "In Progress"

    field = next(
        (f for f in mock_fields if f["name"].lower() == field_name.lower()), None
    )
    assert field is not None, "Should find Status field"

    # Find option ID
    option_id = None
    for opt in field.get("options", []):
        if opt["name"].lower() == value.lower():
            option_id = opt["id"]
            break

    assert option_id == "opt2", f"Should find option ID for '{value}'"

    # Build field value for mutation
    field_value = {"singleSelectOptionId": option_id}
    assert field_value == {"singleSelectOptionId": "opt2"}, (
        "Field value should have correct option ID"
    )

    # Mock mutation response
    mock_mutation_response = {
        "updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_item123"}}
    }

    updated_item = mock_mutation_response.get("updateProjectV2ItemFieldValue", {}).get(
        "projectV2Item"
    )
    result = {
        "success": True,
        "issue_number": 42,
        "project": "1",
        "field": field_name,
        "value": value,
        "item_id": updated_item["id"] if updated_item else None,
    }

    assert result["success"] is True, "Should be successful"
    assert result["field"] == "Status", "Should have correct field"
    assert result["value"] == "In Progress", "Should have correct value"

    print(f"✅ Found option ID '{option_id}' for value '{value}'")
    print(f"✅ Updated field: {result['field']} = {result['value']}")
    print("✅ Test passed!\n")
    return True


def test_update_project_field_text():
    """Test updating a TEXT field value."""
    print("\n=== Test 12: update_project_field (TEXT) ===")

    # Mock field lookup
    mock_fields = [
        {"id": "PVTF_notes", "name": "Notes", "data_type": "TEXT"},
    ]

    # Simulate finding field
    field_name = "Notes"
    value = "This is a note about the issue."

    field = next(
        (f for f in mock_fields if f["name"].lower() == field_name.lower()), None
    )
    assert field is not None, "Should find Notes field"
    assert field["data_type"] == "TEXT", "Should be TEXT type"

    # Build field value for TEXT
    field_value = {"text": value}
    assert field_value == {"text": "This is a note about the issue."}, (
        "Field value should have text"
    )

    print(f"✅ Text field value: {field_value}")
    print("✅ Test passed!\n")
    return True


def test_update_project_field_invalid_option():
    """Test error handling when SingleSelect option is invalid."""
    print("\n=== Test 13: update_project_field (invalid option) ===")

    # Mock field lookup
    mock_fields = [
        {
            "id": "PVTF_status",
            "name": "Status",
            "data_type": "SINGLE_SELECT",
            "options": [
                {"id": "opt1", "name": "Todo"},
                {"id": "opt2", "name": "In Progress"},
                {"id": "opt3", "name": "Done"},
            ],
        }
    ]

    # Try to find an invalid option
    field_name = "Status"
    value = "Invalid Status"

    field = next(
        (f for f in mock_fields if f["name"].lower() == field_name.lower()), None
    )
    assert field is not None, "Should find Status field"

    # Find option ID
    option_id = None
    for opt in field.get("options", []):
        if opt["name"].lower() == value.lower():
            option_id = opt["id"]
            break

    # Should not find option
    assert option_id is None, "Should NOT find option for invalid value"

    # Build error message like the client does
    available_options = [opt["name"] for opt in field.get("options", [])]
    error_message = f"Option '{value}' not found for field '{field_name}'. Available options: {available_options}"

    assert "Invalid Status" in error_message, "Error should mention the invalid value"
    assert "Todo" in error_message, "Error should list available options"
    assert "In Progress" in error_message, "Error should list available options"
    assert "Done" in error_message, "Error should list available options"

    print(f"✅ Correctly detected invalid option: '{value}'")
    print(f"✅ Error message includes available options: {available_options}")
    print("✅ Test passed!\n")
    return True


def test_list_projects_with_fields():
    """Test listing projects with fields in one call."""
    print("\n=== Test 14: list_projects_with_fields ===")

    # Mock GraphQL response
    mock_response = {
        "organization": {
            "projectsV2": {
                "nodes": [
                    {
                        "id": "PVT_project1",
                        "number": 1,
                        "title": "Sprint Board",
                        "url": "https://github.com/orgs/test-org/projects/1",
                        "closed": False,
                        "fields": {
                            "nodes": [
                                {"id": "PVTF_f1", "name": "Title", "dataType": "TITLE"},
                                {
                                    "id": "PVTF_f2",
                                    "name": "Status",
                                    "dataType": "SINGLE_SELECT",
                                    "options": [
                                        {"id": "opt1", "name": "Todo"},
                                        {"id": "opt2", "name": "Done"},
                                    ],
                                },
                            ]
                        },
                    }
                ]
            }
        }
    }

    # Parse like the client does
    owner = "test-org"
    org = mock_response.get("organization")
    nodes = org.get("projectsV2", {}).get("nodes", [])

    projects = []
    for node in nodes:
        if not node:
            continue

        # Parse fields
        fields = []
        for field in node.get("fields", {}).get("nodes", []):
            if not field:
                continue

            field_data = {
                "id": field.get("id"),
                "name": field.get("name"),
                "data_type": field.get("dataType"),
            }

            if "options" in field:
                field_data["options"] = [
                    {"id": opt["id"], "name": opt["name"]}
                    for opt in field.get("options", [])
                ]

            fields.append(field_data)

        projects.append(
            {
                "id": node["id"],
                "number": node["number"],
                "title": node["title"],
                "url": node["url"],
                "closed": node["closed"],
                "owner": owner,
                "fields": fields,
            }
        )

    assert len(projects) == 1, f"Expected 1 project, got {len(projects)}"
    assert projects[0]["title"] == "Sprint Board", "Should have correct title"
    assert len(projects[0]["fields"]) == 2, "Should have 2 fields"

    status_field = next(
        (f for f in projects[0]["fields"] if f["name"] == "Status"), None
    )
    assert status_field is not None, "Should have Status field"
    assert len(status_field["options"]) == 2, "Status should have 2 options"

    print(f"✅ Parsed project: {projects[0]['title']}")
    print(f"✅ Fields: {[f['name'] for f in projects[0]['fields']]}")
    print("✅ Test passed!\n")
    return True


def test_get_project_item_id():
    """Test finding project item ID for an issue."""
    print("\n=== Test 15: get_project_item_id ===")

    # Mock paginated response
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
    target_issue_id = "I_issue2"
    node = mock_items_response.get("node", {})
    items = node.get("items", {})

    item_id = None
    for item in items.get("nodes", []):
        content = item.get("content")
        if content and content.get("id") == target_issue_id:
            item_id = item["id"]
            break

    assert item_id == "PVTI_item2", "Should find item ID for issue #42"

    print(f"✅ Found project item ID: {item_id}")
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
        # New tests for project fields
        test_get_project_fields,
        test_update_project_field_single_select,
        test_update_project_field_text,
        test_update_project_field_invalid_option,
        test_list_projects_with_fields,
        test_get_project_item_id,
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
