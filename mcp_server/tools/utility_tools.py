"""
Utility tools for common operations.

Provides datetime helpers useful for constructing queries:
- Get current datetime
- Calculate date ranges (e.g., "last 7 days")
- Add/subtract time from dates
- Get MCP server version
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastmcp import FastMCP
from pydantic import Field

from mcp_server import __version__


def create_utility_tools(mcp: FastMCP) -> None:
    """
    Add utility tools to the MCP server.

    Args:
        mcp: FastMCP instance to add tools to
    """

    @mcp.tool(tags={"utility", "datetime"})
    def get_current_datetime(
        format: str = Field(
            default="iso",
            description="Output format: 'iso' for ISO 8601, 'unix' for Unix timestamp",
        ),
    ) -> dict:
        """
        Get the current date and time in UTC.

        Returns:
            Current datetime in the specified format
        """
        now = datetime.now(timezone.utc)

        if format == "unix":
            return {
                "datetime": int(now.timestamp()),
                "format": "Unix timestamp",
            }
        else:
            return {
                "datetime": now.isoformat().replace("+00:00", "Z"),
                "format": "ISO 8601",
            }

    @mcp.tool(tags={"utility", "datetime"})
    def calculate_date_range(
        days_ago: int = Field(
            ...,
            description="Days ago to start. Use 7 for 'last week', 1 for 'yesterday', 0 for 'today'.",
        ),
    ) -> dict:
        """
        Calculate a date range from N days ago until now.

        Use this to get the 'since' parameter for list_commits.

        Common mappings:
        - "last week" = days_ago=7
        - "yesterday" = days_ago=1
        - "today" = days_ago=0

        Returns:
            Dictionary with 'since' ISO datetime string
        """
        now = datetime.now(timezone.utc)

        # Calculate start date (N days ago at midnight UTC)
        start = now - timedelta(days=days_ago)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)

        return {
            "since": start.isoformat().replace("+00:00", "Z"),
            "now": now.isoformat().replace("+00:00", "Z"),
            "days_ago": days_ago,
        }

    @mcp.tool(tags={"utility", "datetime"})
    def calculate_date_offset(
        days: int = Field(
            default=0,
            description="Number of days to add (negative to subtract)",
        ),
        hours: int = Field(
            default=0,
            description="Number of hours to add (negative to subtract)",
        ),
        base_date: Optional[str] = Field(
            default=None,
            description="Base date in ISO format. If not provided, uses current time.",
        ),
    ) -> dict:
        """
        Calculate a new date by adding/subtracting time.

        Returns:
            New datetime after applying the offset
        """
        if base_date:
            base = datetime.fromisoformat(base_date.replace("Z", "+00:00"))
        else:
            base = datetime.now(timezone.utc)

        result = base + timedelta(days=days, hours=hours)

        return {
            "datetime": result.isoformat().replace("+00:00", "Z"),
            "base_date": base.isoformat().replace("+00:00", "Z"),
            "offset": f"{days} days, {hours} hours",
        }

    @mcp.tool(tags={"utility", "version"})
    def get_mcp_version() -> dict:
        """
        Get the QuickCall MCP server version.

        Returns the version from pyproject.toml (single source of truth).
        Useful for debugging and verifying which version is running.

        Returns:
            Version info including version string and package name
        """
        return {
            "package": "quickcall-integrations",
            "version": __version__,
        }
