"""
Credential storage and management for QuickCall MCP.

Stores device tokens locally in ~/.quickcall/credentials.json
Fetches fresh API credentials from quickcall.dev on demand.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# Local storage
QUICKCALL_DIR = Path.home() / ".quickcall"
CREDENTIALS_FILE = QUICKCALL_DIR / "credentials.json"

# QuickCall API - configurable via environment for local testing
# Set QUICKCALL_API_URL=http://localhost:8000 for local development
QUICKCALL_API_URL = os.getenv("QUICKCALL_API_URL", "https://api.quickcall.dev")


@dataclass
class StoredCredentials:
    """Credentials stored locally after device flow authentication."""

    device_token: str  # qt_xxxxx - for API authentication
    user_id: str
    email: Optional[str] = None
    username: Optional[str] = None
    authenticated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoredCredentials":
        return cls(
            device_token=data["device_token"],
            user_id=data["user_id"],
            email=data.get("email"),
            username=data.get("username"),
            authenticated_at=data.get("authenticated_at"),
        )


@dataclass
class APICredentials:
    """Fresh credentials fetched from QuickCall API."""

    # User info
    user_id: str
    email: Optional[str] = None
    username: Optional[str] = None

    # GitHub
    github_connected: bool = False
    github_token: Optional[str] = None  # Installation token (1 hour validity)
    github_username: Optional[str] = None
    github_installation_id: Optional[int] = None

    # Slack
    slack_connected: bool = False
    slack_bot_token: Optional[str] = None
    slack_team_name: Optional[str] = None
    slack_team_id: Optional[str] = None
    slack_user_id: Optional[str] = None


class CredentialStore:
    """
    Manages credential storage and retrieval.

    Usage:
        store = CredentialStore()

        # Check if authenticated
        if store.is_authenticated():
            creds = store.get_api_credentials()
            if creds.github_connected:
                # Use GitHub token
                pass

        # Save after device flow
        store.save(StoredCredentials(device_token="qt_xxx", user_id="user_xxx"))

        # Clear on logout
        store.clear()
    """

    def __init__(self, api_url: Optional[str] = None):
        """
        Initialize credential store.

        Args:
            api_url: QuickCall API URL (defaults to production)
        """
        self.api_url = api_url or QUICKCALL_API_URL
        self._stored: Optional[StoredCredentials] = None
        self._api_creds: Optional[APICredentials] = None
        self._load()

    def _load(self):
        """Load stored credentials from disk."""
        if not CREDENTIALS_FILE.exists():
            return

        try:
            with open(CREDENTIALS_FILE) as f:
                data = json.load(f)
                self._stored = StoredCredentials.from_dict(data)
                logger.debug(f"Loaded credentials for user {self._stored.user_id}")
        except Exception as e:
            logger.warning(f"Failed to load credentials: {e}")

    def save(self, credentials: StoredCredentials):
        """Save credentials to disk."""
        QUICKCALL_DIR.mkdir(parents=True, exist_ok=True)

        try:
            with open(CREDENTIALS_FILE, "w") as f:
                json.dump(credentials.to_dict(), f, indent=2)
            CREDENTIALS_FILE.chmod(0o600)  # Restrict permissions
            self._stored = credentials
            self._api_creds = None  # Clear cached API creds
            logger.info(f"Saved credentials for user {credentials.user_id}")
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")
            raise

    def clear(self):
        """Clear stored credentials."""
        if CREDENTIALS_FILE.exists():
            try:
                CREDENTIALS_FILE.unlink()
                logger.info("Cleared stored credentials")
            except Exception as e:
                logger.error(f"Failed to clear credentials: {e}")
                raise

        self._stored = None
        self._api_creds = None

    def is_authenticated(self) -> bool:
        """Check if we have stored credentials."""
        return self._stored is not None

    def get_stored_credentials(self) -> Optional[StoredCredentials]:
        """Get locally stored credentials (device token, etc)."""
        return self._stored

    def get_api_credentials(
        self, force_refresh: bool = False
    ) -> Optional[APICredentials]:
        """
        Fetch fresh API credentials from QuickCall.

        This calls the /api/cli/credentials endpoint to get:
        - GitHub installation token (fresh, 1 hour validity)
        - Slack bot token (decrypted)

        Args:
            force_refresh: Force fetch even if cached

        Returns:
            APICredentials with fresh tokens, or None if not authenticated
        """
        if not self._stored:
            return None

        # Always fetch fresh credentials - don't cache
        # Integration status can change at any time (user connects/disconnects via web)
        # Caching causes stale data issues where connected integrations show as disconnected

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.api_url}/api/cli/credentials",
                    headers={"Authorization": f"Bearer {self._stored.device_token}"},
                )

                if response.status_code == 401:
                    logger.warning("Device token invalid or revoked")
                    self.clear()
                    return None

                response.raise_for_status()
                data = response.json()

                self._api_creds = APICredentials(
                    user_id=data["user"]["user_id"],
                    email=data["user"].get("email"),
                    username=data["user"].get("username"),
                    github_connected=data["github"]["connected"],
                    github_token=data["github"].get("token"),
                    github_username=data["github"].get("username"),
                    github_installation_id=data["github"].get("installation_id"),
                    slack_connected=data["slack"]["connected"],
                    slack_bot_token=data["slack"].get("bot_token"),
                    slack_team_name=data["slack"].get("team_name"),
                    slack_team_id=data["slack"].get("team_id"),
                    slack_user_id=data["slack"].get("user_id"),
                )

                logger.debug(
                    f"Fetched API credentials: GitHub={self._api_creds.github_connected}, "
                    f"Slack={self._api_creds.slack_connected}"
                )
                return self._api_creds

        except httpx.HTTPStatusError as e:
            logger.error(f"API error fetching credentials: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch API credentials: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """Get authentication status for diagnostics."""
        if not self._stored:
            return {
                "authenticated": False,
                "credentials_file": str(CREDENTIALS_FILE),
                "file_exists": CREDENTIALS_FILE.exists(),
            }

        # Always fetch fresh status (force refresh to get latest connection states)
        api_creds = self.get_api_credentials(force_refresh=True)

        return {
            "authenticated": True,
            "credentials_file": str(CREDENTIALS_FILE),
            "user_id": self._stored.user_id,
            "email": self._stored.email,
            "username": self._stored.username,
            "authenticated_at": self._stored.authenticated_at,
            "github": {
                "connected": api_creds.github_connected if api_creds else False,
                "username": api_creds.github_username if api_creds else None,
            },
            "slack": {
                "connected": api_creds.slack_connected if api_creds else False,
                "team_name": api_creds.slack_team_name if api_creds else None,
            },
        }


# Global credential store instance
_credential_store: Optional[CredentialStore] = None


def get_credential_store() -> CredentialStore:
    """Get the global credential store instance."""
    global _credential_store
    if _credential_store is None:
        _credential_store = CredentialStore()
    return _credential_store


def is_authenticated() -> bool:
    """Check if the user is authenticated."""
    return get_credential_store().is_authenticated()


def get_credentials() -> Optional[APICredentials]:
    """Get fresh API credentials (GitHub token, Slack token, etc)."""
    return get_credential_store().get_api_credentials()


def clear_credentials():
    """Clear stored credentials (logout)."""
    get_credential_store().clear()
