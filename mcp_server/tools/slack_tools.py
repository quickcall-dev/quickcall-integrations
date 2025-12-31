"""
Slack Tools - Messaging and channel operations.

These tools require authentication via QuickCall.
Connect using connect_quickcall tool first.
"""

from typing import Optional
import logging

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from mcp_server.auth import get_credential_store
from mcp_server.api_clients.slack_client import SlackClient, SlackAPIError

logger = logging.getLogger(__name__)


def _get_client() -> SlackClient:
    """Get the Slack client, raising error if not configured."""
    store = get_credential_store()

    if not store.is_authenticated():
        raise ToolError(
            "Not connected to QuickCall. "
            "Run connect_quickcall to authenticate and enable Slack tools."
        )

    # Fetch fresh credentials from API
    creds = store.get_api_credentials()

    if not creds or not creds.slack_connected:
        raise ToolError(
            "Slack not connected. "
            "Connect Slack at quickcall.dev/assistant to enable Slack tools."
        )

    if not creds.slack_bot_token:
        raise ToolError(
            "Could not fetch Slack token. "
            "Try reconnecting Slack at quickcall.dev/assistant."
        )

    # Create client with fresh token
    return SlackClient(bot_token=creds.slack_bot_token)


def create_slack_tools(mcp: FastMCP) -> None:
    """Add Slack tools to the MCP server."""

    @mcp.tool(tags={"slack", "channels"})
    def list_slack_channels(
        include_private: bool = Field(
            default=True,
            description="Include private channels the bot has access to (default: true)",
        ),
        limit: int = Field(
            default=100,
            description="Maximum number of channels to return (default: 100)",
        ),
    ) -> dict:
        """
        List Slack channels the bot has access to.

        Returns channel names, IDs, and membership status.
        Requires QuickCall authentication with Slack connected.
        """
        try:
            client = _get_client()
            channels = client.list_channels(
                include_private=include_private, limit=limit
            )

            return {
                "count": len(channels),
                "channels": [ch.model_dump() for ch in channels],
            }
        except ToolError:
            raise
        except SlackAPIError as e:
            raise ToolError(str(e))
        except Exception as e:
            raise ToolError(f"Failed to list Slack channels: {str(e)}")

    @mcp.tool(tags={"slack", "messaging"})
    def send_slack_message(
        message: str = Field(
            ...,
            description="Message text to send. Supports Slack mrkdwn formatting.",
        ),
        channel: Optional[str] = Field(
            default=None,
            description="Channel name (with or without #) or channel ID. Required.",
        ),
    ) -> dict:
        """
        Send a message to a Slack channel.

        The bot must be a member of the channel to send messages.
        Requires QuickCall authentication with Slack connected.

        Message formatting (mrkdwn):
        - *bold* for bold text
        - _italic_ for italic text
        - `code` for inline code
        - ```code block``` for code blocks
        - <https://example.com|link text> for links
        """
        try:
            client = _get_client()
            result = client.send_message(text=message, channel=channel)

            return {
                "success": result.ok,
                "channel": result.channel,
                "message_ts": result.ts,
            }
        except ToolError:
            raise
        except SlackAPIError as e:
            raise ToolError(str(e))
        except ValueError as e:
            raise ToolError(str(e))
        except Exception as e:
            raise ToolError(f"Failed to send Slack message: {str(e)}")

    @mcp.tool(tags={"slack", "users"})
    def list_slack_users(
        limit: int = Field(
            default=100,
            description="Maximum number of users to return (default: 100)",
        ),
        include_bots: bool = Field(
            default=False,
            description="Include bot users in the list (default: false)",
        ),
    ) -> dict:
        """
        List users in the Slack workspace.

        Returns user names, display names, and email addresses.
        Requires QuickCall authentication with Slack connected.
        """
        try:
            client = _get_client()
            users = client.list_users(limit=limit, include_bots=include_bots)

            return {
                "count": len(users),
                "users": [user.model_dump() for user in users],
            }
        except ToolError:
            raise
        except SlackAPIError as e:
            raise ToolError(str(e))
        except Exception as e:
            raise ToolError(f"Failed to list Slack users: {str(e)}")

    @mcp.tool(tags={"slack", "status"})
    def check_slack_connection() -> dict:
        """
        Check if Slack is connected and working.

        Tests the Slack bot token by calling auth.test.
        Use this to verify your Slack integration is working.
        """
        store = get_credential_store()

        if not store.is_authenticated():
            return {
                "connected": False,
                "error": "Not connected to QuickCall. Run connect_quickcall first.",
            }

        creds = store.get_api_credentials()

        if not creds:
            return {
                "connected": False,
                "error": "Could not fetch credentials from QuickCall.",
            }

        if not creds.slack_connected:
            return {
                "connected": False,
                "error": "Slack not connected. Connect at quickcall.dev/assistant.",
            }

        try:
            client = _get_client()
            status = client.health_check()

            if status.get("connected"):
                status["team_name"] = creds.slack_team_name
                status["team_id"] = creds.slack_team_id
            return status
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }
