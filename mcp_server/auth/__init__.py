"""
QuickCall Authentication Module

Handles OAuth device flow authentication for CLI/MCP clients.
Stores credentials locally and fetches fresh tokens from quickcall.dev API.

Also supports GitHub PAT fallback for users without GitHub App access.
"""

from mcp_server.auth.credentials import (
    CredentialStore,
    GitHubPATCredentials,
    get_credential_store,
    is_authenticated,
    get_credentials,
    clear_credentials,
    get_github_pat,
    get_github_pat_username,
)
from mcp_server.auth.device_flow import DeviceFlowAuth

__all__ = [
    "CredentialStore",
    "GitHubPATCredentials",
    "get_credential_store",
    "is_authenticated",
    "get_credentials",
    "clear_credentials",
    "get_github_pat",
    "get_github_pat_username",
    "DeviceFlowAuth",
]
