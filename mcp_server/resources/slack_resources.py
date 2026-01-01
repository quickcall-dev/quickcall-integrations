"""
Slack MCP Resources - Exposes Slack data for Claude's context.

Resources are automatically available in Claude's context when connected.
"""

import logging
from fastmcp import FastMCP

from mcp_server.tools.slack_tools import _get_client
from mcp_server.auth import get_credential_store

logger = logging.getLogger(__name__)


def create_slack_resources(mcp: FastMCP) -> None:
    """Add Slack resources to the MCP server."""

    @mcp.resource("slack://channels")
    def get_slack_channels() -> str:
        """
        List of Slack channels the bot has access to.

        Use these channel names when reading/sending messages.
        """
        store = get_credential_store()

        if not store.is_authenticated():
            return "Slack not connected. Run connect_quickcall first."

        creds = store.get_api_credentials()
        if not creds or not creds.slack_connected or not creds.slack_bot_token:
            return "Slack not connected. Connect at quickcall.dev/assistant."

        try:
            # Use shared cached client
            client = _get_client()
            channels = client.list_channels(include_private=True, limit=200)

            # Format as readable list
            lines = ["Available Slack Channels:", ""]
            for ch in channels:
                status = "member" if ch.is_member else "not member"
                privacy = "private" if ch.is_private else "public"
                lines.append(f"- #{ch.name} ({privacy}, {status})")

            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Failed to fetch Slack channels: {e}")
            return f"Error fetching channels: {str(e)}"
