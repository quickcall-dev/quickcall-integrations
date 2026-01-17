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
