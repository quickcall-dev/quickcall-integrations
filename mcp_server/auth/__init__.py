"""
QuickCall Authentication Module

Handles OAuth device flow authentication for CLI/MCP clients.
Stores credentials locally and fetches fresh tokens from quickcall.dev API.
"""

from mcp_server.auth.credentials import (
    CredentialStore,
    get_credential_store,
    is_authenticated,
    get_credentials,
    clear_credentials,
)
from mcp_server.auth.device_flow import DeviceFlowAuth

__all__ = [
    "CredentialStore",
    "get_credential_store",
    "is_authenticated",
    "get_credentials",
    "clear_credentials",
    "DeviceFlowAuth",
]
