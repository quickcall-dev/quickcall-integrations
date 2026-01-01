"""
Slack Tools - Messaging and channel operations.

These tools require authentication via QuickCall.
Connect using connect_quickcall tool first.
"""

from typing import Optional
from datetime import datetime, timedelta, timezone
import logging

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from mcp_server.auth import get_credential_store
from mcp_server.api_clients.slack_client import SlackClient, SlackAPIError

logger = logging.getLogger(__name__)

# Module-level client cache (keyed by token hash for security)
_client_cache: Optional[tuple[str, SlackClient]] = None


def _get_client() -> SlackClient:
    """Get the Slack client, raising error if not configured. Uses cached client."""
    global _client_cache

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

    # Return cached client if token matches
    token_hash = hash(creds.slack_bot_token)
    if _client_cache and _client_cache[0] == token_hash:
        return _client_cache[1]

    # Create new client and cache it
    client = SlackClient(bot_token=creds.slack_bot_token)
    _client_cache = (token_hash, client)
    return client


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

    @mcp.tool(tags={"slack", "messages", "history"})
    def read_slack_messages(
        channel: str = Field(
            ...,
            description="Channel name (with or without #) or channel ID",
        ),
        days: int = Field(
            default=1,
            description="Number of days to look back (default: 1)",
        ),
        limit: int = Field(
            default=50,
            description="Maximum messages to return (default: 50)",
        ),
        include_threads: bool = Field(
            default=True,
            description="Automatically fetch thread replies for messages with threads (default: true)",
        ),
    ) -> dict:
        """
        Read messages from a Slack channel.

        Returns messages from the specified channel within the date range.
        Bot must be a member of the channel.
        Requires QuickCall authentication with Slack connected.
        """
        try:
            client = _get_client()

            # Calculate oldest timestamp
            oldest_dt = datetime.now(timezone.utc) - timedelta(days=days)
            oldest_ts = str(oldest_dt.timestamp())

            messages = client.get_channel_messages(
                channel=channel,
                oldest=oldest_ts,
                limit=limit,
            )

            result_messages = []
            for msg in messages:
                msg_data = {
                    "ts": msg.ts,
                    "user": msg.user_name or msg.user,
                    "text": msg.text,
                    "has_thread": msg.has_thread,
                    "reply_count": msg.reply_count,
                }

                # Fetch thread replies if message has a thread and include_threads is True
                if include_threads and msg.has_thread and msg.reply_count > 0:
                    try:
                        thread_replies = client.get_thread_replies(
                            channel=channel,
                            thread_ts=msg.ts,
                            limit=50,
                        )
                        # Skip first message (it's the parent) and add replies
                        msg_data["replies"] = [
                            {
                                "ts": reply.ts,
                                "user": reply.user_name or reply.user,
                                "text": reply.text,
                            }
                            for reply in thread_replies
                            if reply.ts != msg.ts  # Skip parent message
                        ]
                    except Exception as e:
                        logger.warning(f"Failed to fetch thread {msg.ts}: {e}")
                        msg_data["replies"] = []

                result_messages.append(msg_data)

            return {
                "count": len(result_messages),
                "channel": channel,
                "days": days,
                "messages": result_messages,
            }
        except ToolError:
            raise
        except SlackAPIError as e:
            raise ToolError(str(e))
        except ValueError as e:
            raise ToolError(str(e))
        except Exception as e:
            raise ToolError(f"Failed to read Slack messages: {str(e)}")

    @mcp.tool(tags={"slack", "messages", "threads"})
    def read_slack_thread(
        channel: str = Field(
            ...,
            description="Channel name (with or without #) or channel ID",
        ),
        thread_ts: str = Field(
            ...,
            description="Thread timestamp (ts) of the parent message",
        ),
        limit: int = Field(
            default=50,
            description="Maximum replies to return (default: 50)",
        ),
    ) -> dict:
        """
        Read replies in a Slack thread.

        Returns all replies in the specified thread.
        Use the 'ts' from read_slack_messages to get thread_ts.
        Bot must be a member of the channel.
        Requires QuickCall authentication with Slack connected.
        """
        try:
            client = _get_client()

            messages = client.get_thread_replies(
                channel=channel,
                thread_ts=thread_ts,
                limit=limit,
            )

            return {
                "count": len(messages),
                "channel": channel,
                "thread_ts": thread_ts,
                "messages": [
                    {
                        "ts": msg.ts,
                        "user": msg.user_name or msg.user,
                        "text": msg.text,
                        "is_parent": msg.ts == thread_ts,
                    }
                    for msg in messages
                ],
            }
        except ToolError:
            raise
        except SlackAPIError as e:
            raise ToolError(str(e))
        except ValueError as e:
            raise ToolError(str(e))
        except Exception as e:
            raise ToolError(f"Failed to read Slack thread: {str(e)}")
