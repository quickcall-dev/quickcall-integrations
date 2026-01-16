"""
QuickCall Integrations MCP Server

Developer integrations for Claude Code and Cursor:
- Local git tools (always available)
- GitHub API tools (requires QuickCall authentication + GitHub connected)
- Slack tools (requires QuickCall authentication + Slack connected)

Authentication:
- Run connect_quickcall to authenticate via OAuth
- Credentials stored locally in ~/.quickcall/credentials.json
- GitHub and Slack tokens fetched from quickcall.dev API
"""

import os
import logging

from fastmcp import FastMCP

from mcp_server.auth import get_credential_store
from mcp_server.tools.git_tools import create_git_tools
from mcp_server.tools.utility_tools import create_utility_tools
from mcp_server.tools.github_tools import create_github_tools
from mcp_server.tools.slack_tools import create_slack_tools
from mcp_server.tools.auth_tools import create_auth_tools
from mcp_server.resources.slack_resources import create_slack_resources
from mcp_server.resources.github_resources import create_github_resources

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_server() -> FastMCP:
    """Create and configure the MCP server with graceful degradation."""
    mcp = FastMCP("quickcall-integrations")

    # Check authentication status
    store = get_credential_store()
    is_authenticated = store.is_authenticated()

    # Always register local git tools (no credentials needed)
    create_git_tools(mcp)
    create_utility_tools(mcp)

    # Register authentication tools (always available)
    create_auth_tools(mcp)
    logger.info(
        "Auth tools: enabled (connect_quickcall, check_quickcall_status, disconnect_quickcall)"
    )

    # Register GitHub and Slack tools (check credentials at runtime)
    create_github_tools(mcp)
    create_slack_tools(mcp)

    # Register resources (available in Claude's context)
    create_slack_resources(mcp)
    create_github_resources(mcp)

    # Log current status
    if is_authenticated:
        logger.info("QuickCall: authenticated")
        creds = store.get_api_credentials()
        if creds:
            logger.info(
                f"GitHub: {'connected' if creds.github_connected else 'not connected'}"
            )
            logger.info(
                f"Slack: {'connected' if creds.slack_connected else 'not connected'}"
            )
    else:
        logger.info("QuickCall: not authenticated")
        logger.info(
            "Run connect_quickcall to authenticate and enable GitHub/Slack tools"
        )

    return mcp


mcp = create_server()


def main():
    """Entry point for the CLI."""
    transport = os.getenv("MCP_TRANSPORT", "stdio")

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "8001"))
        print(f"Starting server: http://{host}:{port}/mcp (transport: {transport})")
        mcp.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    main()
