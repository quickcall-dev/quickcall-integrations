"""
QuickCall Integrations MCP Server

Git tools for developers - view commits, diffs, and changes.
"""

import os

from fastmcp import FastMCP

from mcp_server.tools.git_tools import create_git_tools
from mcp_server.tools.utility_tools import create_utility_tools


def create_server() -> FastMCP:
    """Create and configure the MCP server."""
    mcp = FastMCP("quickcall-integrations")

    create_git_tools(mcp)
    create_utility_tools(mcp)

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
