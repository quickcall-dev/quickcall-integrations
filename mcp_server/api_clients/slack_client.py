"""
Slack API client for MCP server.

Provides Slack API operations using httpx.
Focuses on messaging and channel operations.
"""

import logging
from typing import List, Optional, Dict, Any

import httpx
from pydantic import BaseModel
from rapidfuzz import fuzz, process

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


class SlackChannelMessage(BaseModel):
    """Represents a message from channel history."""

    ts: str  # Message timestamp (used as ID)
    user: Optional[str] = None
    user_name: Optional[str] = None
    text: str
    thread_ts: Optional[str] = None
    reply_count: int = 0
    has_thread: bool = False


# ============================================================================
# Slack Client
# ============================================================================


class SlackClient:
    """
    Slack API client using httpx.

    Provides simplified interface for Slack operations.
    Uses bot token authentication.

    Note on Caching:
        This client caches channel list and user mappings to reduce API calls.
        Cache is per-instance and does NOT expire automatically.
        New channels/users won't appear until:
        - MCP server restarts (new session)
        - New SlackClient instance is created

        TODO: Add TTL-based cache invalidation if this becomes an issue.
        See internal-docs/issues/007-slack-api-caching.md
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
        # Caches (per-instance, cleared on new client)
        self._channel_cache: Optional[List["SlackChannel"]] = None
        self._user_cache: Optional[Dict[str, str]] = None

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
        self, include_private: bool = True, limit: int = 200, use_cache: bool = True
    ) -> List[SlackChannel]:
        """
        List Slack channels the bot has access to.

        Args:
            include_private: Whether to include private channels
            limit: Maximum channels to return
            use_cache: Use cached results if available (default: True)

        Returns:
            List of channels
        """
        # Return cached if available
        if use_cache and self._channel_cache is not None:
            return (
                self._channel_cache[:limit]
                if limit < len(self._channel_cache)
                else self._channel_cache
            )

        types = (
            "public_channel,private_channel" if include_private else "public_channel"
        )

        # Always fetch 200 to ensure we get all channels for caching
        fetch_limit = 200

        data = self._request_sync(
            "GET",
            "conversations.list",
            params={"types": types, "limit": fetch_limit, "exclude_archived": True},
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

        # Cache the full result
        self._channel_cache = channels
        return channels[:limit] if limit < len(channels) else channels

    def _resolve_channel(self, channel: Optional[str] = None) -> str:
        """
        Resolve channel name to channel ID with fuzzy matching.

        Args:
            channel: Channel name (with or without #) or channel ID

        Returns:
            Channel ID
        """
        channel = channel or self.default_channel

        if not channel:
            raise ValueError("No channel specified and no default channel configured")

        # If it's already an ID (starts with C or G for private), return as-is
        if channel.startswith("C") or channel.startswith("G"):
            return channel

        # Strip # prefix if present
        channel_name = channel.lstrip("#").lower()

        # Look up channel by name
        channels = self.list_channels()
        channel_names = {ch.name.lower(): ch for ch in channels}

        # First try exact match
        if channel_name in channel_names:
            return channel_names[channel_name].id

        # Use rapidfuzz for fuzzy matching
        # token_sort_ratio handles word reordering (e.g., "dev no sleep" = "no sleep dev")
        match = process.extractOne(
            channel_name,
            list(channel_names.keys()),
            scorer=fuzz.token_sort_ratio,
            score_cutoff=70,  # Minimum 70% match
        )

        if match:
            matched_name, score, _ = match
            logger.info(
                f"Fuzzy matched '{channel}' to '{matched_name}' (score: {score})"
            )
            return channel_names[matched_name].id

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
    # Message History
    # ========================================================================

    def get_channel_messages(
        self,
        channel: str,
        oldest: Optional[str] = None,
        latest: Optional[str] = None,
        limit: int = 100,
    ) -> List[SlackChannelMessage]:
        """
        Get messages from a channel.

        Args:
            channel: Channel name or ID
            oldest: Unix timestamp - only messages after this time
            latest: Unix timestamp - only messages before this time
            limit: Maximum messages to return (default 100)

        Returns:
            List of messages (newest first)
        """
        channel_id = self._resolve_channel(channel)

        params = {
            "channel": channel_id,
            "limit": limit,
        }

        if oldest:
            params["oldest"] = oldest
        if latest:
            params["latest"] = latest

        data = self._request_sync("GET", "conversations.history", params=params)

        # Get user info for resolving names
        user_map = self._get_user_map()

        messages = []
        for msg in data.get("messages", []):
            # Skip non-message types (joins, leaves, etc.)
            if msg.get("subtype") in ["channel_join", "channel_leave", "bot_add"]:
                continue

            user_id = msg.get("user")
            messages.append(
                SlackChannelMessage(
                    ts=msg.get("ts", ""),
                    user=user_id,
                    user_name=user_map.get(user_id, user_id),
                    text=msg.get("text", ""),
                    thread_ts=msg.get("thread_ts"),
                    reply_count=msg.get("reply_count", 0),
                    has_thread=msg.get("reply_count", 0) > 0,
                )
            )

        return messages

    def get_thread_replies(
        self,
        channel: str,
        thread_ts: str,
        limit: int = 100,
    ) -> List[SlackChannelMessage]:
        """
        Get replies in a thread.

        Args:
            channel: Channel name or ID
            thread_ts: Thread parent message timestamp
            limit: Maximum replies to return

        Returns:
            List of replies (includes parent message first)
        """
        channel_id = self._resolve_channel(channel)

        params = {
            "channel": channel_id,
            "ts": thread_ts,
            "limit": limit,
        }

        data = self._request_sync("GET", "conversations.replies", params=params)

        user_map = self._get_user_map()

        messages = []
        for msg in data.get("messages", []):
            user_id = msg.get("user")
            messages.append(
                SlackChannelMessage(
                    ts=msg.get("ts", ""),
                    user=user_id,
                    user_name=user_map.get(user_id, user_id),
                    text=msg.get("text", ""),
                    thread_ts=msg.get("thread_ts"),
                    reply_count=msg.get("reply_count", 0),
                    has_thread=False,
                )
            )

        return messages

    def _get_user_map(self) -> Dict[str, str]:
        """Get a mapping of user IDs to display names (cached)."""
        # Return cached if available
        if self._user_cache is not None:
            return self._user_cache

        try:
            users = self.list_users(limit=500, include_bots=True)
            self._user_cache = {
                u.id: u.display_name or u.real_name or u.name for u in users
            }
            return self._user_cache
        except Exception:
            return {}

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
