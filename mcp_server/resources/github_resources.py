"""
GitHub MCP Resources - Exposes GitHub data for Claude's context.

Resources are automatically available in Claude's context when connected.
"""

import logging

from fastmcp import FastMCP

from mcp_server.auth import get_credential_store, get_github_pat

logger = logging.getLogger(__name__)


def create_github_resources(mcp: FastMCP) -> None:
    """Add GitHub resources to the MCP server."""

    @mcp.resource("github://repositories")
    def get_github_repositories() -> str:
        """
        List of GitHub repositories the user has access to.

        Use these when working with GitHub operations.
        """
        store = get_credential_store()

        # Check if authenticated via PAT or QuickCall
        pat_token, pat_source = get_github_pat()
        has_pat = pat_token is not None

        if not has_pat and not store.is_authenticated():
            return "GitHub not connected. Options:\n- Run connect_github_via_pat with a Personal Access Token\n- Run connect_quickcall to use QuickCall"

        # Check QuickCall GitHub App connection
        has_app = False
        if store.is_authenticated():
            creds = store.get_api_credentials()
            if creds and creds.github_connected and creds.github_token:
                has_app = True

        if not has_pat and not has_app:
            return "GitHub not connected. Connect at quickcall.dev/assistant or use connect_github_via_pat."

        try:
            # Import here to avoid circular imports
            from mcp_server.tools.github_tools import _get_client

            client = _get_client()
            repos = client.list_repos(limit=50)

            # Determine auth mode for display
            auth_mode = "PAT" if has_pat else "GitHub App"

            lines = [f"GitHub Repositories (via {auth_mode}):", ""]
            for repo in repos:
                visibility = "private" if repo.private else "public"
                lines.append(f"- {repo.full_name} ({visibility})")

            if len(repos) >= 50:
                lines.append("")
                lines.append("(Showing first 50 repos)")

            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Failed to fetch GitHub repositories: {e}")
            return f"Error fetching repositories: {str(e)}"

    @mcp.resource("github://issue-templates")
    def get_issue_templates() -> str:
        """
        Available issue templates from project configuration.

        Supports both:
        - GitHub native templates (.github/ISSUE_TEMPLATE/*.yml)
        - Custom templates (ISSUE_TEMPLATE_PATH in .quickcall.env)

        Use template names when creating issues with manage_issues.
        """
        # Import here to avoid circular imports
        from mcp_server.tools.github_tools import _get_all_templates

        templates = _get_all_templates()

        if not templates:
            return (
                "No issue templates found.\n\n"
                "Supported sources:\n"
                "1. GitHub native: .github/ISSUE_TEMPLATE/*.yml\n"
                "2. Custom: Add ISSUE_TEMPLATE_PATH to .quickcall.env"
            )

        lines = ["Available Issue Templates:", ""]

        for key, template in templates.items():
            name = template.get("name", key)
            description = template.get("description", "")
            labels = template.get("labels", [])
            title_prefix = template.get("title_prefix", "")

            lines.append(f"- {key}")
            if name != key:
                lines.append(f"    Name: {name}")
            if description:
                lines.append(f"    Description: {description}")
            if labels:
                lines.append(f"    Labels: {', '.join(labels)}")
            if title_prefix:
                lines.append(f"    Title prefix: {title_prefix}")

        lines.append("")
        lines.append(
            "Usage: manage_issues(action='create', title='...', template='<key>')"
        )

        return "\n".join(lines)

    @mcp.resource("github://projects")
    def get_github_projects() -> str:
        """
        List of GitHub Projects V2 with their fields and options.

        Use these for project management operations like updating issue status.
        """
        store = get_credential_store()

        # Check if authenticated via PAT or QuickCall
        pat_token, pat_source = get_github_pat()
        has_pat = pat_token is not None

        if not has_pat and not store.is_authenticated():
            return "GitHub not connected. Options:\n- Run connect_github_via_pat with a Personal Access Token\n- Run connect_quickcall to use QuickCall"

        # Check QuickCall GitHub App connection
        has_app = False
        if store.is_authenticated():
            creds = store.get_api_credentials()
            if creds and creds.github_connected and creds.github_token:
                has_app = True

        if not has_pat and not has_app:
            return "GitHub not connected. Connect at quickcall.dev/assistant or use connect_github_via_pat."

        try:
            # Import here to avoid circular imports
            from mcp_server.tools.github_tools import _get_client

            client = _get_client()

            # Determine auth mode for display
            auth_mode = "PAT" if has_pat else "GitHub App"

            # Get the authenticated user
            username = client.get_authenticated_user()

            # Collect all projects from user and their orgs
            all_projects = []

            # 1. Try user projects first
            try:
                user_projects = client.list_projects_with_fields(
                    owner=username, is_org=False, limit=100
                )
                all_projects.extend(user_projects)
            except Exception:
                pass

            # 2. Get unique orgs from repos the user has access to
            try:
                repos = client.list_repos(limit=100)
                org_counts: dict = {}
                for repo in repos:
                    if repo.owner != username:
                        org_counts[repo.owner] = org_counts.get(repo.owner, 0) + 1

                # Sort orgs by repo count (most repos first)
                sorted_orgs = sorted(
                    org_counts.keys(), key=lambda x: org_counts[x], reverse=True
                )

                # Fetch projects from all orgs
                for org in sorted_orgs:
                    try:
                        org_projects = client.list_projects_with_fields(
                            owner=org, is_org=True, limit=100
                        )
                        all_projects.extend(org_projects)
                    except Exception:
                        pass
            except Exception:
                pass

            if not all_projects:
                return (
                    f"GitHub Projects (via {auth_mode}):\n\n"
                    f"No projects found for {username} or accessible orgs.\n\n"
                    "To list projects for a specific org, use:\n"
                    "  manage_issues(action='list_projects', owner='org-name')"
                )

            projects = all_projects

            lines = [f"GitHub Projects (via {auth_mode}):", ""]

            for proj in projects:
                status = "closed" if proj["closed"] else "open"
                lines.append(f"- #{proj['number']}: {proj['title']} ({status})")
                lines.append(f"  URL: {proj['url']}")

                # Show fields
                fields = proj.get("fields", [])
                if fields:
                    lines.append("  Fields:")
                    for field in fields:
                        name = field.get("name", "Unknown")
                        data_type = field.get("data_type", "UNKNOWN")

                        if data_type == "SINGLE_SELECT":
                            options = field.get("options", [])
                            option_names = [opt["name"] for opt in options]
                            lines.append(
                                f"    - {name} (SINGLE_SELECT): {', '.join(option_names)}"
                            )
                        else:
                            lines.append(f"    - {name} ({data_type})")

                lines.append("")

            lines.append("Usage:")
            lines.append(
                "  manage_projects(action='update_fields', issue_numbers=[42], project='1',"
            )
            lines.append(
                "                  fields={'Status': 'In Progress', 'Priority': 'High'})"
            )

            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Failed to fetch GitHub projects: {e}")
            return f"Error fetching projects: {str(e)}"
