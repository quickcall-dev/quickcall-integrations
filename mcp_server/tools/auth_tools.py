"""
Authentication tools for QuickCall MCP.

Provides tools for users to connect, check status, and disconnect
their QuickCall account from the CLI.

Also provides GitHub PAT authentication for users who can't install the GitHub App.
"""

import os
import logging
import webbrowser
from typing import Dict, Any

import httpx
from github import Github, Auth, GithubException
from fastmcp import FastMCP
from pydantic import Field

from mcp_server.auth import (
    get_credential_store,
    DeviceFlowAuth,
)

logger = logging.getLogger(__name__)

# QuickCall API URL - configurable for local dev
QUICKCALL_API_URL = os.getenv("QUICKCALL_API_URL", "https://api.quickcall.dev")


def create_auth_tools(mcp: FastMCP):
    """Register authentication tools with the MCP server."""

    @mcp.tool(tags={"auth", "quickcall"})
    def connect_quickcall() -> Dict[str, Any]:
        """
        Connect your CLI to QuickCall.

        This starts the OAuth device flow authentication:
        1. Opens your browser to quickcall.dev
        2. You sign in with Google
        3. Your CLI is linked to your account

        After connecting, you can use GitHub and Slack tools
        with your configured integrations from quickcall.dev.

        Returns:
            Authentication result with status and instructions
        """
        store = get_credential_store()

        # Check if already authenticated
        if store.is_authenticated():
            status = store.get_status()
            return {
                "status": "already_connected",
                "message": "You're already connected to QuickCall!",
                "user": status.get("username") or status.get("email"),
                "github_connected": status.get("github", {}).get("connected", False),
                "slack_connected": status.get("slack", {}).get("connected", False),
                "hint": "Use check_quickcall_status for details or disconnect_quickcall to logout.",
            }

        # Start device flow
        auth = DeviceFlowAuth()

        try:
            # Initialize flow
            device_code, user_code, verification_url, expires_in, interval = (
                auth.init_flow()
            )

            # Build URL with code
            auth_url = f"{verification_url}?code={user_code}"

            return {
                "status": "pending",
                "message": "Authentication started! Complete the following steps:",
                "code": user_code,
                "url": auth_url,
                "instructions": [
                    f"1. Open this URL in your browser: {auth_url}",
                    "2. Sign in with Google",
                    "3. Your CLI will be connected automatically",
                ],
                "expires_in_minutes": expires_in // 60,
                "hint": "The browser should open automatically. If not, copy the URL above.",
                "_device_code": device_code,
                "_interval": interval,
            }

        except Exception as e:
            logger.error(f"Failed to start authentication: {e}")
            return {
                "status": "error",
                "message": f"Failed to start authentication: {e}",
                "hint": "Check your internet connection and try again.",
            }

    @mcp.tool(tags={"auth", "quickcall"})
    def check_quickcall_status() -> Dict[str, Any]:
        """
        Check your QuickCall connection status.

        Shows:
        - Whether you're connected to QuickCall
        - Your account info
        - GitHub connection status (via App or PAT)
        - Slack connection status

        Returns:
            Current authentication and integration status
        """
        store = get_credential_store()
        status = store.get_status()

        # Build result with both QuickCall and PAT status
        result = {
            "quickcall_connected": status.get("quickcall_authenticated", False),
            "credentials_file": status.get("credentials_file"),
        }

        # QuickCall user info
        if status.get("quickcall_authenticated"):
            result["user"] = {
                "id": status.get("user_id"),
                "email": status.get("email"),
                "username": status.get("username"),
            }
            result["authenticated_at"] = status.get("authenticated_at")

        # GitHub status (can be via App or PAT)
        github_status = status.get("github", {})
        result["github"] = {
            "connected": github_status.get("connected", False),
            "mode": github_status.get("mode"),  # "github_app" or "pat"
            "username": github_status.get("username"),
        }

        # PAT-specific info if configured
        github_pat = status.get("github_pat", {})
        if github_pat.get("configured"):
            result["github_pat"] = {
                "configured": True,
                "username": github_pat.get("username"),
                "configured_at": github_pat.get("configured_at"),
            }

        # Slack status (requires QuickCall)
        slack_status = status.get("slack", {})
        result["slack"] = {
            "connected": slack_status.get("connected", False),
            "team_name": slack_status.get("team_name"),
        }

        # Add helpful message based on status
        if not status.get("quickcall_authenticated") and not github_pat.get(
            "configured"
        ):
            result["message"] = "Not connected to QuickCall or GitHub"
            result["hint"] = (
                "Use connect_quickcall for full access, or connect_github_via_pat for GitHub only."
            )
        elif not status.get("quickcall_authenticated") and github_pat.get("configured"):
            result["message"] = "GitHub connected via PAT (QuickCall not connected)"
            result["hint"] = "Use connect_quickcall to also access Slack tools."
        elif status.get("quickcall_authenticated"):
            result["message"] = "Connected to QuickCall"

        # Legacy compatibility
        result["connected"] = status.get("quickcall_authenticated", False)

        return result

    @mcp.tool(tags={"auth", "quickcall"})
    def disconnect_quickcall() -> Dict[str, Any]:
        """
        Disconnect your CLI from QuickCall.

        This removes your local credentials. You'll need to
        run connect_quickcall again to use GitHub and Slack tools.

        Note: This doesn't revoke the device from your QuickCall
        account. To fully revoke access, visit quickcall.dev/settings.

        Returns:
            Disconnection result
        """
        store = get_credential_store()

        if not store.is_authenticated():
            return {
                "status": "not_connected",
                "message": "You're not connected to QuickCall.",
            }

        try:
            # Get user info before clearing
            status = store.get_status()
            user = (
                status.get("username") or status.get("email") or status.get("user_id")
            )

            # Clear credentials
            store.clear()

            return {
                "status": "disconnected",
                "message": f"Disconnected from QuickCall ({user})",
                "hint": "To fully revoke access, visit quickcall.dev/settings. Use connect_quickcall to reconnect.",
            }

        except Exception as e:
            logger.error(f"Failed to disconnect: {e}")
            return {
                "status": "error",
                "message": f"Failed to disconnect: {e}",
            }

    @mcp.tool(tags={"auth", "quickcall"})
    def complete_quickcall_auth(
        device_code: str, timeout_seconds: int = 300
    ) -> Dict[str, Any]:
        """
        Complete QuickCall authentication after browser sign-in.

        This polls for the authentication result after you've signed
        in via the browser. Usually called automatically after connect_quickcall.

        Args:
            device_code: The device code from connect_quickcall
            timeout_seconds: How long to wait for authentication (default: 5 minutes)

        Returns:
            Authentication result
        """
        auth = DeviceFlowAuth()

        try:
            credentials = auth.poll_for_completion(
                device_code=device_code,
                timeout=timeout_seconds,
            )

            if credentials:
                return {
                    "status": "success",
                    "message": "Successfully connected to QuickCall!",
                    "user_id": credentials.user_id,
                    "email": credentials.email,
                    "hint": "You can now use GitHub and Slack tools. Run check_quickcall_status to see your integrations.",
                }
            else:
                return {
                    "status": "failed",
                    "message": "Authentication failed or timed out.",
                    "hint": "Try running connect_quickcall again.",
                }

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return {
                "status": "error",
                "message": f"Authentication error: {e}",
            }

    @mcp.tool(tags={"auth", "github", "quickcall"})
    def connect_github(open_browser: bool = True) -> Dict[str, Any]:
        """
        Connect GitHub to your QuickCall account.

        This opens your browser to install the QuickCall GitHub App.
        After installation, you'll be able to use GitHub tools like
        list_repos, create_issue, etc.

        Args:
            open_browser: Automatically open the install URL in browser (default: True)

        Returns:
            Install URL and instructions
        """
        store = get_credential_store()

        if not store.is_authenticated():
            return {
                "status": "error",
                "message": "Not connected to QuickCall",
                "hint": "Run connect_quickcall first to authenticate.",
            }

        stored = store.get_stored_credentials()
        if not stored:
            return {
                "status": "error",
                "message": "No stored credentials found",
                "hint": "Run connect_quickcall to authenticate.",
            }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{QUICKCALL_API_URL}/api/cli/github/install-url",
                    headers={"Authorization": f"Bearer {stored.device_token}"},
                )
                response.raise_for_status()
                data = response.json()

            if data.get("already_connected"):
                return {
                    "status": "already_connected",
                    "message": f"GitHub is already connected (username: {data.get('username')})",
                    "hint": "You can use GitHub tools like list_repos, create_issue, etc.",
                }

            install_url = data.get("install_url")

            if open_browser and install_url:
                try:
                    webbrowser.open(install_url)
                except Exception as e:
                    logger.warning(f"Failed to open browser: {e}")

            return {
                "status": "pending",
                "message": "Please complete GitHub App installation in your browser.",
                "install_url": install_url,
                "instructions": [
                    f"1. Open this URL: {install_url}",
                    "2. Select the organization/account to install",
                    "3. Choose which repositories to grant access",
                    "4. Click 'Install'",
                ],
                "hint": "After installation, run check_quickcall_status to verify.",
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return {
                    "status": "error",
                    "message": "Session expired. Please reconnect.",
                    "hint": "Run disconnect_quickcall then connect_quickcall again.",
                }
            return {
                "status": "error",
                "message": f"API error: {e.response.status_code}",
            }
        except Exception as e:
            logger.error(f"Failed to get GitHub install URL: {e}")
            return {
                "status": "error",
                "message": f"Failed to connect GitHub: {e}",
            }

    @mcp.tool(tags={"auth", "slack", "quickcall"})
    def connect_slack(open_browser: bool = True, force: bool = False) -> Dict[str, Any]:
        """
        Connect Slack to your QuickCall account.

        This opens your browser to authorize the QuickCall Slack App.
        After authorization, you'll be able to use Slack tools like
        list_channels, send_message, etc.

        Args:
            open_browser: Automatically open the install URL in browser (default: True)
            force: Force re-authorization even if already connected (use to get new permissions)

        Returns:
            Install URL and instructions
        """
        store = get_credential_store()

        if not store.is_authenticated():
            return {
                "status": "error",
                "message": "Not connected to QuickCall",
                "hint": "Run connect_quickcall first to authenticate.",
            }

        stored = store.get_stored_credentials()
        if not stored:
            return {
                "status": "error",
                "message": "No stored credentials found",
                "hint": "Run connect_quickcall to authenticate.",
            }

        try:
            with httpx.Client(timeout=30.0) as client:
                params = {"force": "true"} if force else {}
                response = client.get(
                    f"{QUICKCALL_API_URL}/api/cli/slack/install-url",
                    params=params,
                    headers={"Authorization": f"Bearer {stored.device_token}"},
                )
                response.raise_for_status()
                data = response.json()

            if data.get("already_connected") and not force:
                return {
                    "status": "already_connected",
                    "message": f"Slack is already connected (workspace: {data.get('team_name')})",
                    "hint": "Use force=True to re-authorize with updated permissions.",
                }

            install_url = data.get("install_url")

            if open_browser and install_url:
                try:
                    webbrowser.open(install_url)
                except Exception as e:
                    logger.warning(f"Failed to open browser: {e}")

            return {
                "status": "pending",
                "message": "Please complete Slack authorization in your browser.",
                "install_url": install_url,
                "instructions": [
                    f"1. Open this URL: {install_url}",
                    "2. Select the Slack workspace",
                    "3. Review permissions and click 'Allow'",
                ],
                "hint": "After authorization, run check_quickcall_status to verify.",
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return {
                    "status": "error",
                    "message": "Session expired. Please reconnect.",
                    "hint": "Run disconnect_quickcall then connect_quickcall again.",
                }
            if e.response.status_code == 503:
                return {
                    "status": "error",
                    "message": "Slack integration is not configured on the server.",
                }
            return {
                "status": "error",
                "message": f"API error: {e.response.status_code}",
            }
        except Exception as e:
            logger.error(f"Failed to get Slack install URL: {e}")
            return {
                "status": "error",
                "message": f"Failed to connect Slack: {e}",
            }

    @mcp.tool(tags={"auth", "slack", "quickcall"})
    def reconnect_slack(open_browser: bool = True) -> Dict[str, Any]:
        """
        Reconnect Slack to get updated permissions.

        Use this when the Slack app has new scopes/permissions that
        require re-authorization. This forces a fresh OAuth flow
        even if Slack is already connected.

        Args:
            open_browser: Automatically open the OAuth URL in browser (default: True)

        Returns:
            OAuth URL and instructions
        """
        store = get_credential_store()

        if not store.is_authenticated():
            return {
                "status": "error",
                "message": "Not connected to QuickCall",
                "hint": "Run connect_quickcall first to authenticate.",
            }

        stored = store.get_stored_credentials()
        if not stored:
            return {
                "status": "error",
                "message": "No stored credentials found",
                "hint": "Run connect_quickcall to authenticate.",
            }

        try:
            with httpx.Client(timeout=30.0) as client:
                # Force reconnect by passing force=true
                response = client.get(
                    f"{QUICKCALL_API_URL}/api/cli/slack/install-url",
                    params={"force": "true"},
                    headers={"Authorization": f"Bearer {stored.device_token}"},
                )
                response.raise_for_status()
                data = response.json()

            install_url = data.get("install_url")

            if open_browser and install_url:
                try:
                    webbrowser.open(install_url)
                except Exception as e:
                    logger.warning(f"Failed to open browser: {e}")

            return {
                "status": "pending",
                "message": "Please re-authorize Slack in your browser to get updated permissions.",
                "install_url": install_url,
                "instructions": [
                    f"1. Open this URL: {install_url}",
                    "2. Select your Slack workspace",
                    "3. Review the NEW permissions and click 'Allow'",
                ],
                "hint": "This will update your Slack permissions with any new scopes.",
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return {
                    "status": "error",
                    "message": "Session expired. Please reconnect.",
                    "hint": "Run disconnect_quickcall then connect_quickcall again.",
                }
            return {
                "status": "error",
                "message": f"API error: {e.response.status_code}",
            }
        except Exception as e:
            logger.error(f"Failed to get Slack install URL: {e}")
            return {
                "status": "error",
                "message": f"Failed to reconnect Slack: {e}",
            }

    # ========================================================================
    # GitHub PAT Authentication (alternative to QuickCall GitHub App)
    # ========================================================================

    @mcp.tool(tags={"auth", "github"})
    def connect_github_via_pat(
        token: str = Field(
            ...,
            description="GitHub Personal Access Token (ghp_xxx or github_pat_xxx)",
        ),
    ) -> Dict[str, Any]:
        """
        Connect GitHub using a Personal Access Token (PAT).

        Use this if your organization can't install the QuickCall GitHub App.
        This is an alternative to the standard connect_github flow.

        This command:
        1. Validates your PAT by calling GitHub API
        2. Auto-detects your GitHub username
        3. Stores the PAT securely in ~/.quickcall/credentials.json

        After connecting, you can use GitHub tools like list_repos, list_prs, etc.

        Create a PAT at: https://github.com/settings/tokens
        Required scopes:
        - repo (full access to private repos)
        - OR public_repo (public repos only)

        Note: PAT mode works independently of QuickCall. You don't need
        to run connect_quickcall first. However, Slack tools still require
        QuickCall authentication.
        """
        store = get_credential_store()

        # Check if already configured via stored PAT
        if store.has_github_pat():
            pat_creds = store.get_github_pat_credentials()
            return {
                "status": "already_connected",
                "message": f"GitHub PAT is already configured (username: {pat_creds.username})",
                "configured_at": pat_creds.configured_at,
                "hint": "Use disconnect_github_pat to remove it, then connect again with a new token.",
            }

        # Validate token format
        if not token.startswith(("ghp_", "github_pat_")):
            return {
                "status": "error",
                "message": "Invalid token format. GitHub PATs start with 'ghp_' or 'github_pat_'",
                "hint": "Create a new token at https://github.com/settings/tokens",
            }

        # Validate token by calling GitHub API
        try:
            auth = Auth.Token(token)
            gh = Github(auth=auth)
            user = gh.get_user()
            username = user.login
            gh.close()
        except GithubException as e:
            if e.status == 401:
                return {
                    "status": "error",
                    "message": "Invalid or expired token.",
                    "hint": "Check your token at https://github.com/settings/tokens",
                }
            return {
                "status": "error",
                "message": f"GitHub API error: {e.data.get('message', str(e))}",
            }
        except Exception as e:
            logger.error(f"Failed to validate GitHub PAT: {e}")
            return {
                "status": "error",
                "message": f"Failed to validate token: {e}",
            }

        # Store the PAT
        try:
            store.save_github_pat(token=token, username=username)
        except Exception as e:
            logger.error(f"Failed to save GitHub PAT: {e}")
            return {
                "status": "error",
                "message": f"Failed to save token: {e}",
            }

        return {
            "status": "success",
            "message": f"Successfully connected GitHub as {username}!",
            "username": username,
            "mode": "pat",
            "hint": "You can now use GitHub tools. Run check_github_connection to verify.",
        }

    @mcp.tool(tags={"auth", "github"})
    def disconnect_github_pat() -> Dict[str, Any]:
        """
        Disconnect GitHub PAT authentication.

        This removes only the stored PAT. If you also have QuickCall
        connected, that connection remains intact.

        After disconnecting:
        - If you have QuickCall GitHub App connected, it will be used instead
        - Otherwise, GitHub tools will be unavailable until you reconnect
        """
        store = get_credential_store()

        if not store.has_github_pat():
            return {
                "status": "not_connected",
                "message": "No GitHub PAT is configured.",
                "hint": "Use connect_github_via_pat to set up PAT authentication.",
            }

        try:
            pat_creds = store.get_github_pat_credentials()
            username = pat_creds.username if pat_creds else "unknown"

            store.clear_github_pat()

            return {
                "status": "disconnected",
                "message": f"Disconnected GitHub PAT ({username})",
                "hint": "Use connect_github_via_pat to reconnect, or connect_github to use the QuickCall GitHub App instead.",
            }
        except Exception as e:
            logger.error(f"Failed to disconnect GitHub PAT: {e}")
            return {
                "status": "error",
                "message": f"Failed to disconnect: {e}",
            }
