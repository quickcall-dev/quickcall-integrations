"""
Authentication tools for QuickCall MCP.

Provides tools for users to connect, check status, and disconnect
their QuickCall account from the CLI.
"""

import os
import logging
import webbrowser
from typing import Dict, Any

import httpx
from fastmcp import FastMCP

from mcp_server.auth import (
    get_credential_store,
    is_authenticated,
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
        - Whether you're connected
        - Your account info
        - GitHub connection status
        - Slack connection status

        Returns:
            Current authentication and integration status
        """
        store = get_credential_store()

        if not store.is_authenticated():
            return {
                "connected": False,
                "message": "Not connected to QuickCall",
                "hint": "Use connect_quickcall to authenticate.",
            }

        status = store.get_status()

        return {
            "connected": True,
            "user": {
                "id": status.get("user_id"),
                "email": status.get("email"),
                "username": status.get("username"),
            },
            "authenticated_at": status.get("authenticated_at"),
            "integrations": {
                "github": {
                    "connected": status.get("github", {}).get("connected", False),
                    "username": status.get("github", {}).get("username"),
                },
                "slack": {
                    "connected": status.get("slack", {}).get("connected", False),
                    "team_name": status.get("slack", {}).get("team_name"),
                },
            },
            "credentials_file": status.get("credentials_file"),
        }

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
