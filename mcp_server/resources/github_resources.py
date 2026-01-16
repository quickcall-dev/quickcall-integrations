"""
GitHub MCP Resources - Exposes GitHub data for Claude's context.

Resources are automatically available in Claude's context when connected.
"""

import logging
from typing import Any, Dict, Optional

import yaml
from fastmcp import FastMCP

from mcp_server.auth import get_credential_store, get_github_pat
from mcp_server.auth.credentials import _find_project_root, _parse_env_file

logger = logging.getLogger(__name__)


def _load_issue_templates_config() -> Optional[Dict[str, Any]]:
    """
    Load issue templates from ISSUE_TEMPLATE_PATH in .quickcall.env.
    Returns None if not configured or file doesn't exist.
    """
    import os
    from pathlib import Path

    template_path = os.getenv("ISSUE_TEMPLATE_PATH")

    # Check .quickcall.env in project root
    if not template_path:
        project_root = _find_project_root()
        if project_root:
            config_path = project_root / ".quickcall.env"
            if config_path.exists():
                env_vars = _parse_env_file(config_path)
                if "ISSUE_TEMPLATE_PATH" in env_vars:
                    template_path = env_vars["ISSUE_TEMPLATE_PATH"]
                    if not Path(template_path).is_absolute():
                        template_path = str(project_root / template_path)

    if not template_path:
        return None

    try:
        with open(template_path) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to load issue templates: {e}")
        return None


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

        Use template names when creating issues with manage_issues.
        """
        config = _load_issue_templates_config()

        if not config:
            return "No issue templates configured.\n\nTo configure:\n1. Create a YAML file with your templates\n2. Add ISSUE_TEMPLATE_PATH=/path/to/templates.yaml to .quickcall.env"

        templates = config.get("templates", {})
        defaults = config.get("defaults", {})

        if not templates:
            lines = ["Issue Templates:", ""]
            if defaults:
                labels = defaults.get("labels", [])
                lines.append("Default template:")
                if labels:
                    lines.append(f"  Labels: {', '.join(labels)}")
                if defaults.get("body"):
                    lines.append(f"  Body template: {defaults['body'][:100]}...")
            return "\n".join(lines)

        lines = ["Available Issue Templates:", ""]

        for name, template in templates.items():
            labels = template.get("labels", [])
            body_preview = template.get("body", "")[:80]
            lines.append(f"- {name}")
            if labels:
                lines.append(f"    Labels: {', '.join(labels)}")
            if body_preview:
                lines.append(f"    Body: {body_preview}...")

        lines.append("")
        lines.append(
            "Usage: manage_issues(action='create', title='...', template='<name>')"
        )

        return "\n".join(lines)
