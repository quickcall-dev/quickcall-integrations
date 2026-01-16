"""
Credential storage and management for QuickCall MCP.

Stores device tokens locally in ~/.quickcall/credentials.json
Fetches fresh API credentials from quickcall.dev on demand.

Also supports GitHub PAT fallback for users without GitHub App access:
- Environment variable: GITHUB_TOKEN or GITHUB_PAT
- Config file: .quickcall.env in project root or ~/.quickcall.env
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# Local storage
QUICKCALL_DIR = Path.home() / ".quickcall"
CREDENTIALS_FILE = QUICKCALL_DIR / "credentials.json"

# PAT config file names (searched in order)
PAT_CONFIG_FILENAMES = [".quickcall.env", "quickcall.env"]

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
class GitHubPATCredentials:
    """GitHub PAT credentials stored locally (independent of QuickCall)."""

    token: str  # ghp_xxx or github_pat_xxx
    username: str
    configured_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GitHubPATCredentials":
        return cls(
            token=data["token"],
            username=data["username"],
            configured_at=data["configured_at"],
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

    Supports two independent credential types:
    1. QuickCall credentials (device token for API auth)
    2. GitHub PAT credentials (for users without GitHub App access)

    Usage:
        store = CredentialStore()

        # QuickCall auth
        if store.is_authenticated():
            creds = store.get_api_credentials()

        # GitHub PAT auth
        pat_creds = store.get_github_pat_credentials()
        if pat_creds:
            # Use PAT
            pass

        # Save credentials
        store.save(StoredCredentials(...))  # QuickCall
        store.save_github_pat(token="ghp_xxx", username="user")  # PAT
    """

    def __init__(self, api_url: Optional[str] = None):
        """
        Initialize credential store.

        Args:
            api_url: QuickCall API URL (defaults to production)
        """
        self.api_url = api_url or QUICKCALL_API_URL
        self._stored: Optional[StoredCredentials] = None
        self._github_pat: Optional[GitHubPATCredentials] = None
        self._api_creds: Optional[APICredentials] = None
        self._load()

    def _load(self):
        """Load stored credentials from disk."""
        if not CREDENTIALS_FILE.exists():
            return

        try:
            with open(CREDENTIALS_FILE) as f:
                data = json.load(f)

                # New format: separate keys for quickcall and github_pat
                if "quickcall" in data:
                    self._stored = StoredCredentials.from_dict(data["quickcall"])
                    logger.debug(
                        f"Loaded QuickCall credentials for user {self._stored.user_id}"
                    )
                elif "device_token" in data:
                    # Legacy format: direct StoredCredentials
                    self._stored = StoredCredentials.from_dict(data)
                    logger.debug(
                        f"Loaded legacy credentials for user {self._stored.user_id}"
                    )

                # Load GitHub PAT if present
                if "github_pat" in data:
                    self._github_pat = GitHubPATCredentials.from_dict(
                        data["github_pat"]
                    )
                    logger.debug(
                        f"Loaded GitHub PAT for user {self._github_pat.username}"
                    )

        except Exception as e:
            logger.warning(f"Failed to load credentials: {e}")

    def _save_to_file(self):
        """Save all credentials to disk."""
        QUICKCALL_DIR.mkdir(parents=True, exist_ok=True)

        data = {}
        if self._stored:
            data["quickcall"] = self._stored.to_dict()
        if self._github_pat:
            data["github_pat"] = self._github_pat.to_dict()

        try:
            with open(CREDENTIALS_FILE, "w") as f:
                json.dump(data, f, indent=2)
            CREDENTIALS_FILE.chmod(0o600)  # Restrict permissions
            logger.debug("Saved credentials to disk")
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")
            raise

    def save(self, credentials: StoredCredentials):
        """Save QuickCall credentials to disk."""
        self._stored = credentials
        self._api_creds = None  # Clear cached API creds
        self._save_to_file()
        logger.info(f"Saved QuickCall credentials for user {credentials.user_id}")

    def clear(self):
        """Clear all stored credentials (QuickCall + PAT)."""
        if CREDENTIALS_FILE.exists():
            try:
                CREDENTIALS_FILE.unlink()
                logger.info("Cleared all stored credentials")
            except Exception as e:
                logger.error(f"Failed to clear credentials: {e}")
                raise

        self._stored = None
        self._github_pat = None
        self._api_creds = None

    def clear_quickcall(self):
        """Clear only QuickCall credentials, keep PAT if configured."""
        self._stored = None
        self._api_creds = None
        if self._github_pat:
            self._save_to_file()
        elif CREDENTIALS_FILE.exists():
            CREDENTIALS_FILE.unlink()
        logger.info("Cleared QuickCall credentials")

    def is_authenticated(self) -> bool:
        """Check if we have QuickCall credentials."""
        return self._stored is not None

    def get_stored_credentials(self) -> Optional[StoredCredentials]:
        """Get locally stored QuickCall credentials (device token, etc)."""
        return self._stored

    # ========================================================================
    # GitHub PAT Methods
    # ========================================================================

    def save_github_pat(self, token: str, username: str):
        """
        Save GitHub PAT credentials.

        Args:
            token: GitHub Personal Access Token
            username: GitHub username
        """
        self._github_pat = GitHubPATCredentials(
            token=token,
            username=username,
            configured_at=datetime.utcnow().isoformat() + "Z",
        )
        self._save_to_file()
        logger.info(f"Saved GitHub PAT for user {username}")

    def get_github_pat_credentials(self) -> Optional[GitHubPATCredentials]:
        """Get stored GitHub PAT credentials."""
        return self._github_pat

    def clear_github_pat(self):
        """Clear only GitHub PAT credentials, keep QuickCall if configured."""
        self._github_pat = None
        if self._stored:
            self._save_to_file()
        elif CREDENTIALS_FILE.exists():
            CREDENTIALS_FILE.unlink()
        logger.info("Cleared GitHub PAT credentials")

    def has_github_pat(self) -> bool:
        """Check if GitHub PAT is configured."""
        return self._github_pat is not None

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
        result = {
            "credentials_file": str(CREDENTIALS_FILE),
            "file_exists": CREDENTIALS_FILE.exists(),
        }

        # QuickCall status
        if self._stored:
            result["quickcall_authenticated"] = True
            result["user_id"] = self._stored.user_id
            result["email"] = self._stored.email
            result["username"] = self._stored.username
            result["authenticated_at"] = self._stored.authenticated_at

            # Fetch fresh API credentials for integration status
            api_creds = self.get_api_credentials(force_refresh=True)
            result["github"] = {
                "connected": api_creds.github_connected if api_creds else False,
                "mode": (
                    "github_app" if (api_creds and api_creds.github_connected) else None
                ),
                "username": api_creds.github_username if api_creds else None,
            }
            result["slack"] = {
                "connected": api_creds.slack_connected if api_creds else False,
                "team_name": api_creds.slack_team_name if api_creds else None,
            }
        else:
            result["quickcall_authenticated"] = False
            result["github"] = {"connected": False, "mode": None, "username": None}
            result["slack"] = {"connected": False, "team_name": None}

        # GitHub PAT status (independent of QuickCall)
        if self._github_pat:
            result["github_pat"] = {
                "configured": True,
                "username": self._github_pat.username,
                "configured_at": self._github_pat.configured_at,
            }
            # If QuickCall GitHub not connected, PAT takes over
            if not result["github"]["connected"]:
                result["github"]["connected"] = True
                result["github"]["mode"] = "pat"
                result["github"]["username"] = self._github_pat.username
        else:
            result["github_pat"] = {"configured": False}

        # Legacy compatibility
        result["authenticated"] = result["quickcall_authenticated"]

        return result


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


# ============================================================================
# GitHub PAT Fallback Support
# ============================================================================


def _parse_env_file(file_path: Path) -> Dict[str, str]:
    """
    Parse a simple .env file into a dictionary.

    Supports:
    - KEY=value
    - KEY="value"
    - KEY='value'
    - # comments
    - Empty lines
    """
    result = {}
    if not file_path.exists():
        return result

    try:
        with open(file_path) as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                # Parse KEY=value
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()

                    # Remove surrounding quotes
                    if (value.startswith('"') and value.endswith('"')) or (
                        value.startswith("'") and value.endswith("'")
                    ):
                        value = value[1:-1]

                    result[key] = value
    except Exception as e:
        logger.debug(f"Failed to parse {file_path}: {e}")

    return result


def _find_project_root() -> Optional[Path]:
    """
    Find the project root by looking for common markers.

    Walks up from cwd looking for .git, pyproject.toml, package.json, etc.
    Returns None if no project root is found.
    """
    markers = [".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod"]

    try:
        current = Path.cwd().resolve()
    except Exception:
        return None

    # Walk up the directory tree
    while current != current.parent:
        for marker in markers:
            if (current / marker).exists():
                return current
        current = current.parent

    return None


def get_github_pat() -> Tuple[Optional[str], Optional[str]]:
    """
    Get GitHub Personal Access Token from various sources.

    Search order (first found wins):
    1. Stored credentials file (via connect_github_via_pat command)
    2. Environment variable: GITHUB_TOKEN
    3. Environment variable: GITHUB_PAT
    4. Project root: .quickcall.env or quickcall.env
    5. Home directory: ~/.quickcall.env or ~/quickcall.env

    Returns:
        Tuple of (token, source) where source describes where the token was found.
        Returns (None, None) if no PAT is configured.
    """
    # 1. Check stored credentials (from connect_github_via_pat command)
    store = get_credential_store()
    pat_creds = store.get_github_pat_credentials()
    if pat_creds:
        logger.debug("Found GitHub PAT in stored credentials")
        return (pat_creds.token, "credentials file")

    # 2. Check environment variables
    for env_var in ["GITHUB_TOKEN", "GITHUB_PAT"]:
        token = os.environ.get(env_var)
        if token:
            logger.debug(f"Found GitHub PAT in environment variable {env_var}")
            return (token, f"environment variable {env_var}")

    # 3. Check project root config files
    project_root = _find_project_root()
    if project_root:
        for filename in PAT_CONFIG_FILENAMES:
            config_path = project_root / filename
            if config_path.exists():
                env_vars = _parse_env_file(config_path)
                for key in ["GITHUB_TOKEN", "GITHUB_PAT"]:
                    if key in env_vars:
                        logger.debug(f"Found GitHub PAT in {config_path}")
                        return (env_vars[key], f"{config_path}")

    # 4. Check home directory config files
    home = Path.home()
    for filename in PAT_CONFIG_FILENAMES:
        config_path = home / filename
        if config_path.exists():
            env_vars = _parse_env_file(config_path)
            for key in ["GITHUB_TOKEN", "GITHUB_PAT"]:
                if key in env_vars:
                    logger.debug(f"Found GitHub PAT in {config_path}")
                    return (env_vars[key], f"{config_path}")

    return (None, None)


def get_github_pat_username() -> Optional[str]:
    """
    Get the GitHub username for PAT authentication.

    Checks:
    1. Stored credentials (from connect_github_via_pat command)
    2. Environment variable: GITHUB_USERNAME
    3. Config files (same search order as get_github_pat)

    Returns:
        GitHub username or None if not configured.
    """
    # Check stored credentials first
    store = get_credential_store()
    pat_creds = store.get_github_pat_credentials()
    if pat_creds:
        return pat_creds.username

    # Check environment variable
    username = os.environ.get("GITHUB_USERNAME")
    if username:
        return username

    # Check project root config files
    project_root = _find_project_root()
    if project_root:
        for filename in PAT_CONFIG_FILENAMES:
            config_path = project_root / filename
            if config_path.exists():
                env_vars = _parse_env_file(config_path)
                if "GITHUB_USERNAME" in env_vars:
                    return env_vars["GITHUB_USERNAME"]

    # Check home directory config files
    home = Path.home()
    for filename in PAT_CONFIG_FILENAMES:
        config_path = home / filename
        if config_path.exists():
            env_vars = _parse_env_file(config_path)
            if "GITHUB_USERNAME" in env_vars:
                return env_vars["GITHUB_USERNAME"]

    return None
