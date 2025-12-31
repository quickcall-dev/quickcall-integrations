#!/usr/bin/env python3
"""
Test QuickCall Integrations MCP Server.

Tests all git tools by connecting to the running server.
No authentication required - just uses local git commands.

Usage:
    1. Start the server: cd mcp_server && python server.py
    2. Run this test: python tests/test_tools.py
"""

import asyncio
import json
import os
import httpx
from rich.console import Console

console = Console()

# MCP server endpoint
MCP_URL = "http://localhost:8001"

# Test repository path (this repo)
TEST_REPO_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_server():
    """Check if server is running."""
    try:
        response = httpx.get(f"{MCP_URL}/mcp", timeout=2)
        # SSE endpoint returns 200 even without proper SSE headers
        console.print(f"[green]✅ Server is running at {MCP_URL}[/green]")
        return True
    except Exception:
        pass

    console.print("[red]❌ Server is not running![/red]")
    console.print("   Start it with: cd mcp_server && python server.py")
    return False


async def test_with_fastmcp():
    """Test using FastMCP client."""
    from fastmcp import Client

    console.print("\n[bold]Testing with FastMCP Client[/bold]\n")

    client = Client(f"{MCP_URL}/mcp")

    async with client:
        console.print("[green]✅ Connected to MCP server[/green]\n")

        # List available tools
        console.print("[bold]Available Tools:[/bold]")
        tools = await client.list_tools()
        for tool in tools:
            console.print(f"  - {tool.name}: {tool.description[:60]}...")

        console.print("\n" + "=" * 60 + "\n")

        # Test 1: get_updates
        console.print("[bold cyan]Test 1: get_updates[/bold cyan]")
        console.print(f"Testing on repo: {TEST_REPO_PATH}\n")

        try:
            result = await client.call_tool(
                "get_updates", {"path": TEST_REPO_PATH, "days": 7}
            )

            if isinstance(result, list) and len(result) > 0:
                data = json.loads(result[0].text)
                console.print(f"[green]✅ Repository: {data['repository']}[/green]")
                console.print(f"   Branch: {data['branch']}")
                console.print(f"   Period: {data['period']}")
                console.print(f"   Commits: {data['commit_count']}")

                if data.get("diff"):
                    diff = data["diff"]
                    console.print(f"   Files changed: {diff['files_changed']}")
                    console.print(f"   Additions: +{diff['additions']}")
                    console.print(f"   Deletions: -{diff['deletions']}")

                    if diff.get("patch"):
                        lines = diff["patch"].split("\n")[:10]
                        console.print("\n   Diff preview:")
                        for line in lines:
                            if line.startswith("+") and not line.startswith("+++"):
                                console.print(f"   [green]{line[:80]}[/green]")
                            elif line.startswith("-") and not line.startswith("---"):
                                console.print(f"   [red]{line[:80]}[/red]")
                            else:
                                console.print(f"   {line[:80]}")

                if data.get("uncommitted"):
                    uncommitted = data["uncommitted"]
                    console.print(
                        f"\n   Uncommitted - Staged: {len(uncommitted.get('staged', []))}"
                    )
                    console.print(
                        f"   Uncommitted - Unstaged: {len(uncommitted.get('unstaged', []))}"
                    )

                if data.get("commits"):
                    console.print("\n   Recent commits:")
                    for commit in data["commits"][:3]:
                        msg = (
                            commit["message"][:50] + "..."
                            if len(commit["message"]) > 50
                            else commit["message"]
                        )
                        console.print(f"   - {commit['sha']} {msg}")

        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")

        console.print("\n" + "=" * 60 + "\n")

        # Test 2: Utility tools
        console.print("[bold cyan]Test 2: Utility Tools[/bold cyan]")

        try:
            result = await client.call_tool("get_current_datetime", {})
            if isinstance(result, list) and len(result) > 0:
                data = json.loads(result[0].text)
                console.print(f"[green]✅ Current time: {data['datetime']}[/green]")

            result = await client.call_tool("calculate_date_range", {"days_ago": 7})
            if isinstance(result, list) and len(result) > 0:
                data = json.loads(result[0].text)
                console.print(f"[green]✅ Last 7 days: since {data['since']}[/green]")

        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")

        console.print("\n" + "=" * 60 + "\n")
        console.print("[green]✅ All tests completed![/green]")


async def main():
    """Run tests."""
    console.print("\n[bold]QuickCall Integrations - MCP Server Test[/bold]\n")

    if not check_server():
        return

    await test_with_fastmcp()


if __name__ == "__main__":
    asyncio.run(main())
