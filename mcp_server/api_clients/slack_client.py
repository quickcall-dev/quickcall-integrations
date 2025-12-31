"""
Slack API client for MCP server.

Provides Slack API operations using httpx.
Focuses on messaging and channel operations.
"""

import logging
from typing import List, Optional, Dict, Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic models for Slack data
# ============================================================================


class SlackChannel(BaseModel):
    """Represents a Slack channel."""

    id: str
    name: str
    is_private: bool = False
    is_member: bool = False
    topic: str = ""
    purpose: str = ""


class SlackUser(BaseModel):
    """Represents a Slack user."""

    id: str
    name: str
    real_name: str = ""
    display_name: str = ""
    email: Optional[str] = None
    is_admin: bool = False
    is_bot: bool = False


class SlackMessage(BaseModel):
    """Represents a sent Slack message."""

    ok: bool
    channel: str
    ts: str  # Message timestamp (used as ID)
    message: Optional[Dict[str, Any]] = None


# ============================================================================
# Slack Client
# ============================================================================


class SlackClient:
    """
    Slack API client using httpx.

    Provides simplified interface for Slack operations.
    Uses bot token authentication.
    """

    BASE_URL = "https://slack.com/api"

    def __init__(self, bot_token: str, default_channel: Optional[str] = None):
        """
        Initialize Slack API client.

        Args:
            bot_token: Slack bot OAuth token (xoxb-...)
            default_channel: Default channel name or ID for sending messages
        """
        self.bot_token = bot_token
        self.default_channel = default_channel
        self._headers = {
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make an async request to Slack API."""
        url = f"{self.BASE_URL}/{endpoint}"

        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(url, headers=self._headers, params=params)
            else:
                response = await client.post(url, headers=self._headers, json=json)

            data = response.json()

            if not data.get("ok"):
                error = data.get("error", "unknown_error")
                raise SlackAPIError(f"Slack API error: {error}")

            return data

    def _request_sync(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make a sync request to Slack API."""
        url = f"{self.BASE_URL}/{endpoint}"

        with httpx.Client() as client:
            if method == "GET":
                response = client.get(url, headers=self._headers, params=params)
            else:
                response = client.post(url, headers=self._headers, json=json)

            data = response.json()

            if not data.get("ok"):
                error = data.get("error", "unknown_error")
                raise SlackAPIError(f"Slack API error: {error}")

            return data

    # ========================================================================
    # Connection / Auth
    # ========================================================================

    def health_check(self) -> Dict[str, Any]:
        """
        Check if Slack connection is working.

        Returns:
            Dict with connection status and workspace info
        """
        try:
            data = self._request_sync("POST", "auth.test")
            return {
                "connected": True,
                "team": data.get("team"),
                "team_id": data.get("team_id"),
                "user": data.get("user"),
                "user_id": data.get("user_id"),
                "bot_id": data.get("bot_id"),
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }

    # ========================================================================
    # Channel Operations
    # ========================================================================

    def list_channels(
        self, include_private: bool = True, limit: int = 200
    ) -> List[SlackChannel]:
        """
        List Slack channels the bot has access to.

        Args:
            include_private: Whether to include private channels
            limit: Maximum channels to return

        Returns:
            List of channels
        """
        types = (
            "public_channel,private_channel" if include_private else "public_channel"
        )

        data = self._request_sync(
            "GET",
            "conversations.list",
            params={"types": types, "limit": limit, "exclude_archived": True},
        )

        channels = []
        for ch in data.get("channels", []):
            channels.append(
                SlackChannel(
                    id=ch["id"],
                    name=ch["name"],
                    is_private=ch.get("is_private", False),
                    is_member=ch.get("is_member", False),
                    topic=ch.get("topic", {}).get("value", ""),
                    purpose=ch.get("purpose", {}).get("value", ""),
                )
            )

        return channels

    def _resolve_channel(self, channel: Optional[str] = None) -> str:
        """
        Resolve channel name to channel ID.

        Args:
            channel: Channel name (with or without #) or channel ID

        Returns:
            Channel ID
        """
        channel = channel or self.default_channel

        if not channel:
            raise ValueError("No channel specified and no default channel configured")

        # If it's already an ID (starts with C), return as-is
        if channel.startswith("C"):
            return channel

        # Strip # prefix if present
        channel_name = channel.lstrip("#").lower()

        # Look up channel by name
        channels = self.list_channels()
        for ch in channels:
            if ch.name.lower() == channel_name:
                return ch.id

        raise ValueError(f"Channel '{channel}' not found or bot is not a member")

    # ========================================================================
    # Messaging
    # ========================================================================

    def send_message(
        self,
        text: str,
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> SlackMessage:
        """
        Send a message to a Slack channel.

        Args:
            text: Message text (supports mrkdwn formatting)
            channel: Channel name or ID (uses default if not specified)
            thread_ts: Thread timestamp to reply to (optional)

        Returns:
            SlackMessage with sent message details
        """
        channel_id = self._resolve_channel(channel)

        payload = {
            "channel": channel_id,
            "text": text,
        }

        if thread_ts:
            payload["thread_ts"] = thread_ts

        data = self._request_sync("POST", "chat.postMessage", json=payload)

        return SlackMessage(
            ok=data.get("ok", False),
            channel=data.get("channel", channel_id),
            ts=data.get("ts", ""),
            message=data.get("message"),
        )

    async def send_message_async(
        self,
        text: str,
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> SlackMessage:
        """
        Send a message to a Slack channel (async version).

        Args:
            text: Message text (supports mrkdwn formatting)
            channel: Channel name or ID (uses default if not specified)
            thread_ts: Thread timestamp to reply to (optional)

        Returns:
            SlackMessage with sent message details
        """
        channel_id = self._resolve_channel(channel)

        payload = {
            "channel": channel_id,
            "text": text,
        }

        if thread_ts:
            payload["thread_ts"] = thread_ts

        data = await self._request("POST", "chat.postMessage", json=payload)

        return SlackMessage(
            ok=data.get("ok", False),
            channel=data.get("channel", channel_id),
            ts=data.get("ts", ""),
            message=data.get("message"),
        )

    # ========================================================================
    # User Operations
    # ========================================================================

    def list_users(
        self, limit: int = 200, include_bots: bool = False
    ) -> List[SlackUser]:
        """
        List users in the Slack workspace.

        Args:
            limit: Maximum users to return
            include_bots: Whether to include bot users

        Returns:
            List of users
        """
        data = self._request_sync("GET", "users.list", params={"limit": limit})

        users = []
        for member in data.get("members", []):
            # Skip deleted users
            if member.get("deleted"):
                continue

            # Skip bots unless requested
            if not include_bots and member.get("is_bot"):
                continue

            # Skip Slackbot
            if member.get("id") == "USLACKBOT":
                continue

            profile = member.get("profile", {})
            users.append(
                SlackUser(
                    id=member["id"],
                    name=member.get("name", ""),
                    real_name=member.get("real_name", ""),
                    display_name=profile.get("display_name", ""),
                    email=profile.get("email"),
                    is_admin=member.get("is_admin", False),
                    is_bot=member.get("is_bot", False),
                )
            )

        return users


class SlackAPIError(Exception):
    """Exception raised for Slack API errors."""

    pass
