"""
OAuth Device Flow Authentication for QuickCall MCP.

Implements RFC 8628 device authorization flow:
1. CLI calls init to get device_code + user_code
2. User visits quickcall.dev/cli/setup?code={user_code}
3. User signs in with Google (Clerk)
4. CLI polls until complete, receives device_token
5. Device token stored locally for future API calls
"""

import os
import time
import logging
import webbrowser
from typing import Optional, Tuple
from datetime import datetime, timezone

import httpx

from mcp_server.auth.credentials import (
    CredentialStore,
    StoredCredentials,
    get_credential_store,
)

logger = logging.getLogger(__name__)

# QuickCall URLs - configurable via environment for local testing
# Set QUICKCALL_API_URL=http://localhost:8000 for local backend
# Set QUICKCALL_WEB_URL=http://localhost:3000 for local frontend
QUICKCALL_API_URL = os.getenv("QUICKCALL_API_URL", "https://api.quickcall.dev")
QUICKCALL_WEB_URL = os.getenv("QUICKCALL_WEB_URL", "https://quickcall.dev")


class DeviceFlowAuth:
    """
    Handles OAuth device flow authentication.

    Usage:
        auth = DeviceFlowAuth()

        # Start flow (opens browser)
        success = auth.authenticate()

        if success:
            print("Authenticated!")
            # Credentials are now stored in ~/.quickcall/credentials.json
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        web_url: Optional[str] = None,
        credential_store: Optional[CredentialStore] = None,
    ):
        """
        Initialize device flow authentication.

        Args:
            api_url: QuickCall API URL (defaults to production)
            web_url: QuickCall web URL (defaults to production)
            credential_store: Credential store instance (defaults to global)
        """
        self.api_url = api_url or QUICKCALL_API_URL
        self.web_url = web_url or QUICKCALL_WEB_URL
        self.credential_store = credential_store or get_credential_store()

    def init_flow(self) -> Tuple[str, str, str, int, int]:
        """
        Initialize device authorization flow.

        Returns:
            Tuple of (device_code, user_code, verification_url, expires_in, interval)

        Raises:
            Exception if initialization fails
        """
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{self.api_url}/api/device/init")
            response.raise_for_status()
            data = response.json()

            return (
                data["device_code"],
                data["user_code"],
                data["verification_url"],
                data["expires_in"],
                data["interval"],
            )

    def poll_for_completion(
        self,
        device_code: str,
        interval: int = 5,
        timeout: int = 900,
        on_poll: Optional[callable] = None,
    ) -> Optional[StoredCredentials]:
        """
        Poll for device authorization completion.

        Args:
            device_code: Device code from init_flow
            interval: Polling interval in seconds
            timeout: Maximum time to wait in seconds
            on_poll: Optional callback called on each poll (for progress indication)

        Returns:
            StoredCredentials if successful, None if expired/cancelled
        """
        start_time = time.time()

        with httpx.Client(timeout=30.0) as client:
            while time.time() - start_time < timeout:
                if on_poll:
                    on_poll()

                try:
                    response = client.get(
                        f"{self.api_url}/api/device/status",
                        params={"device_code": device_code},
                    )
                    response.raise_for_status()
                    data = response.json()

                    status = data["status"]

                    if status == "complete":
                        # Success! Save credentials
                        credentials = StoredCredentials(
                            device_token=data["device_token"],
                            user_id=data["user_id"],
                            authenticated_at=datetime.now(timezone.utc)
                            .isoformat()
                            .replace("+00:00", "Z"),
                        )
                        self.credential_store.save(credentials)
                        return credentials

                    elif status == "expired":
                        logger.warning("Authorization code expired")
                        return None

                    elif status == "revoked":
                        logger.warning("Authorization was revoked")
                        return None

                    # Status is "pending", continue polling
                    time.sleep(interval)

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        logger.error("Device code not found")
                        return None
                    raise

        logger.warning("Polling timeout exceeded")
        return None

    def authenticate(
        self,
        open_browser: bool = True,
        print_instructions: bool = True,
    ) -> bool:
        """
        Run the full device flow authentication.

        This is the main entry point for CLI authentication:
        1. Initializes the flow
        2. Opens browser (or prints URL)
        3. Polls until complete
        4. Saves credentials

        Args:
            open_browser: Whether to automatically open browser
            print_instructions: Whether to print user instructions

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            # Initialize flow
            device_code, user_code, verification_url, expires_in, interval = (
                self.init_flow()
            )

            # Build URL with code
            auth_url = f"{verification_url}?code={user_code}"

            if print_instructions:
                print("\n" + "=" * 50)
                print("QuickCall Authentication")
                print("=" * 50)
                print(f"\nYour code: {user_code}")
                print(f"\nVisit: {auth_url}")
                print("\nSign in with Google to connect your CLI.")
                print(f"This code expires in {expires_in // 60} minutes.")
                print("=" * 50 + "\n")

            # Open browser
            if open_browser:
                try:
                    webbrowser.open(auth_url)
                    if print_instructions:
                        print("Browser opened. Waiting for authorization...")
                except Exception as e:
                    logger.warning(f"Could not open browser: {e}")
                    if print_instructions:
                        print("Could not open browser. Please visit the URL manually.")

            # Poll for completion
            def on_poll():
                if print_instructions:
                    print(".", end="", flush=True)

            credentials = self.poll_for_completion(
                device_code=device_code,
                interval=interval,
                on_poll=on_poll,
            )

            if credentials:
                if print_instructions:
                    print("\n\nAuthentication successful!")
                    print(f"Connected as: {credentials.email or credentials.user_id}")
                return True
            else:
                if print_instructions:
                    print("\n\nAuthentication failed or timed out.")
                return False

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            if print_instructions:
                print(f"\nAuthentication error: {e}")
            return False

    def disconnect(self) -> bool:
        """
        Disconnect the current device (logout).

        This clears local credentials. The device token remains valid
        on the server until explicitly revoked from the web UI.

        Returns:
            True if cleared successfully
        """
        try:
            self.credential_store.clear()
            return True
        except Exception as e:
            logger.error(f"Failed to disconnect: {e}")
            return False
