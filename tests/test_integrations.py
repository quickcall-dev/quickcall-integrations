#!/usr/bin/env python3
"""
QuickCall MCP Server Integration Tests.

Starts the MCP server and tests all integrations via MCP protocol:

1. QuickCall Auth - Device flow authentication
2. GitHub - App installation, list repos
3. Slack - OAuth, list channels, read messages, fuzzy matching
4. MCP Resources - slack://channels resource

Usage:
    python tests/test_integrations.py
"""

import asyncio
import json
import os
from pathlib import Path
import webbrowser
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rich.console import Console

console = Console()


async def call_tool(session: ClientSession, tool_name: str, arguments: dict = None):
    """Call an MCP tool and return the result."""
    if arguments is None:
        arguments = {}

    result = await session.call_tool(tool_name, arguments=arguments)

    # Parse the result
    if result.content:
        for content in result.content:
            if hasattr(content, "text"):
                try:
                    return json.loads(content.text)
                except json.JSONDecodeError:
                    return {"raw": content.text}
    return None


def print_result(data: dict, indent: int = 0):
    """Pretty print result data."""
    prefix = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            console.print(f"{prefix}{key}:")
            print_result(value, indent + 1)
        elif isinstance(value, list):
            console.print(f"{prefix}{key}:")
            for item in value:
                if isinstance(item, dict):
                    print_result(item, indent + 1)
                else:
                    console.print(f"{prefix}  - {item}")
        else:
            console.print(f"{prefix}{key}: {value}")


async def test_connect_quickcall(session: ClientSession):
    """Test QuickCall device flow authentication."""
    console.print("\n[bold cyan]TEST 1: Connect to QuickCall[/bold cyan]\n")

    # Check status first
    console.print("Checking current status...")
    status = await call_tool(session, "check_quickcall_status")

    if status and status.get("connected"):
        console.print("[green]PASS: Already connected to QuickCall[/green]")
        print_result(status, indent=1)
        return True

    console.print("Starting device flow authentication...")
    result = await call_tool(session, "connect_quickcall")

    if not result:
        console.print("[red]FAIL: No response from connect_quickcall[/red]")
        return False

    print_result(result)

    if result.get("status") == "already_connected":
        console.print("\n[green]PASS: Already connected[/green]")
        return True

    if result.get("status") != "pending":
        console.print(f"\n[red]FAIL: Unexpected status: {result.get('status')}[/red]")
        return False

    # Extract device code and user code
    device_code = result.get("_device_code")
    user_code = result.get("code")
    url = result.get("url")

    console.print(f"\nCode: [bold]{user_code}[/bold]")
    console.print(f"URL: {url}")

    # Open browser
    console.print("\nOpening browser...")
    webbrowser.open(url)

    console.print("\nWaiting for you to sign in...")

    # Poll for completion
    complete_result = await call_tool(
        session,
        "complete_quickcall_auth",
        {"device_code": device_code, "timeout_seconds": 300},
    )

    if complete_result and complete_result.get("status") == "success":
        console.print("\n[green]PASS: Successfully connected to QuickCall![/green]")
        print_result(complete_result, indent=1)
        return True
    else:
        console.print("\n[red]FAIL: Authentication failed[/red]")
        if complete_result:
            print_result(complete_result, indent=1)
        return False


async def test_connect_github(session: ClientSession):
    """Test GitHub App installation."""
    console.print("\n[bold cyan]TEST 2: Connect GitHub[/bold cyan]\n")

    result = await call_tool(session, "connect_github", {"open_browser": True})

    if not result:
        console.print("[red]FAIL: No response from connect_github[/red]")
        return False

    print_result(result)

    if result.get("status") == "already_connected":
        console.print("\n[green]PASS: GitHub already connected[/green]")
        return True

    if result.get("status") == "pending":
        console.print(
            "\n[bold]Please complete GitHub App installation in your browser:[/bold]"
        )
        if "instructions" in result:
            for instruction in result["instructions"]:
                console.print(f"  {instruction}")

        input("\nPress ENTER after completing installation...")

        # Verify
        console.print("\nVerifying connection...")
        time.sleep(2)

        status = await call_tool(session, "check_quickcall_status")
        if status and status.get("integrations", {}).get("github", {}).get("connected"):
            console.print("[green]PASS: GitHub connected successfully![/green]")
            return True
        else:
            console.print("[red]FAIL: GitHub not connected yet[/red]")
            return False

    console.print(f"\n[red]FAIL: Unexpected status: {result.get('status')}[/red]")
    return False


async def test_connect_slack(session: ClientSession):
    """Test Slack OAuth authorization."""
    console.print("\n[bold cyan]TEST 3: Connect Slack[/bold cyan]\n")

    result = await call_tool(session, "connect_slack", {"open_browser": True})

    if not result:
        console.print("[red]FAIL: No response from connect_slack[/red]")
        return False

    print_result(result)

    if result.get("status") == "already_connected":
        console.print("\n[green]PASS: Slack already connected[/green]")
        return True

    if result.get("status") == "pending":
        console.print(
            "\n[bold]Please complete Slack authorization in your browser:[/bold]"
        )
        if "instructions" in result:
            for instruction in result["instructions"]:
                console.print(f"  {instruction}")

        input("\nPress ENTER after completing authorization...")

        # Verify
        console.print("\nVerifying connection...")
        time.sleep(2)

        status = await call_tool(session, "check_quickcall_status")
        if status and status.get("integrations", {}).get("slack", {}).get("connected"):
            console.print("[green]PASS: Slack connected successfully![/green]")
            return True
        else:
            console.print("[red]FAIL: Slack not connected yet[/red]")
            return False

    console.print(f"\n[red]FAIL: Unexpected status: {result.get('status')}[/red]")
    return False


async def test_list_repos(session: ClientSession):
    """Test listing GitHub repositories."""
    console.print("\n[bold cyan]TEST 4: List GitHub Repositories[/bold cyan]\n")

    try:
        result = await call_tool(session, "list_repos", {"limit": 10})

        # Result is a dict with 'count' and 'repos' keys
        if result and isinstance(result, dict) and "repos" in result:
            repos = result["repos"]
            console.print(f"[green]PASS: Found {len(repos)} repositories[/green]\n")
            for repo in repos:
                if isinstance(repo, dict):
                    full_name = repo.get("full_name", repo.get("name", "Unknown"))
                    private = repo.get("private", False)
                    visibility = "[Private]" if private else "[Public]"
                    console.print(f"  {visibility} {full_name}")
                    if repo.get("description"):
                        console.print(f"      {repo['description'][:80]}")
                    console.print()
            return True
        else:
            console.print(
                "[red]FAIL: No repositories returned or unexpected format[/red]"
            )
            if result:
                print_result(result)
            return False

    except Exception as e:
        console.print(f"[red]FAIL: Error: {e}[/red]")
        return False


async def test_list_slack_channels(session: ClientSession):
    """Test listing Slack channels."""
    console.print("\n[bold cyan]TEST 5: List Slack Channels[/bold cyan]\n")

    try:
        result = await call_tool(session, "list_slack_channels", {"limit": 10})

        # Result is a dict with 'count' and 'channels' keys
        if result and isinstance(result, dict) and "channels" in result:
            channels = result["channels"]
            console.print(f"[green]PASS: Found {len(channels)} channels[/green]\n")
            for channel in channels:
                if isinstance(channel, dict):
                    name = channel.get("name", "Unknown")
                    is_private = channel.get("is_private", False)
                    visibility = "[Private]" if is_private else "[Public]"
                    console.print(f"  {visibility} #{name}")
                    if channel.get("topic"):
                        console.print(f"      {channel['topic'][:80]}")
                    console.print()
            return True
        else:
            console.print("[red]FAIL: No channels returned or unexpected format[/red]")
            if result:
                print_result(result)
            return False

    except Exception as e:
        console.print(f"[red]FAIL: Error: {e}[/red]")
        return False


async def test_slack_resources(session: ClientSession):
    """Test Slack MCP resources."""
    console.print("\n[bold cyan]TEST 6: Slack MCP Resources[/bold cyan]\n")

    try:
        # List all resources
        console.print("Listing MCP resources...")
        resources_result = await session.list_resources()

        if not resources_result.resources:
            console.print(
                "[yellow]No resources available (Slack may not be connected)[/yellow]"
            )
            return True  # Not a failure if Slack isn't connected

        console.print(
            f"[green]Found {len(resources_result.resources)} resources:[/green]"
        )
        for resource in resources_result.resources:
            console.print(f"  - {resource.uri}: {resource.name}")

        # Try to read slack://channels resource
        slack_resource = None
        for resource in resources_result.resources:
            if "slack" in str(resource.uri).lower():
                slack_resource = resource
                break

        if slack_resource:
            console.print(f"\nReading resource: {slack_resource.uri}")
            content = await session.read_resource(slack_resource.uri)

            if content and content.contents:
                console.print("[green]PASS: Resource content:[/green]")
                for item in content.contents:
                    if hasattr(item, "text"):
                        # Print first 500 chars
                        text = (
                            item.text[:500] + "..."
                            if len(item.text) > 500
                            else item.text
                        )
                        console.print(f"\n{text}")
                return True
            else:
                console.print("[red]FAIL: No content in resource[/red]")
                return False
        else:
            console.print("[yellow]No Slack resource found[/yellow]")
            return True

    except Exception as e:
        console.print(f"[red]FAIL: Error: {e}[/red]")
        import traceback

        traceback.print_exc()
        return False


async def test_fuzzy_channel_match(session: ClientSession):
    """Test fuzzy channel matching via read_slack_messages."""
    console.print("\n[bold cyan]TEST 7: Fuzzy Channel Matching[/bold cyan]\n")

    try:
        # First get the actual channel names (use high limit to get all channels)
        result = await call_tool(session, "list_slack_channels", {"limit": 100})

        if not result or "channels" not in result:
            console.print("[yellow]No channels available to test[/yellow]")
            return True

        channels = result["channels"]

        # Debug: print all channels with their is_member status
        console.print("Channel membership status:")
        for ch in channels:
            console.print(f"  #{ch.get('name')}: is_member={ch.get('is_member')}")

        member_channels = [ch for ch in channels if ch.get("is_member")]

        if not member_channels:
            console.print("[yellow]Bot is not a member of any channels[/yellow]")
            return True

        # Pick a channel to test fuzzy matching
        test_channel = member_channels[0]
        channel_name = test_channel["name"]

        console.print(f"Testing fuzzy match on channel: #{channel_name}")

        # Create fuzzy variations
        fuzzy_names = [
            channel_name,  # Exact match
            channel_name.replace("-", " "),  # Spaces instead of hyphens
            channel_name.replace("-", ""),  # No separators
        ]

        for fuzzy_name in fuzzy_names:
            console.print(f"\n  Trying: '{fuzzy_name}'")
            try:
                result = await call_tool(
                    session,
                    "read_slack_messages",
                    {"channel": fuzzy_name, "days": 1, "limit": 1},
                )
                if result and "channel" in result:
                    console.print(f"  [green]PASS: Matched![/green]")
                else:
                    console.print(f"  [red]FAIL: No match[/red]")
            except Exception as e:
                console.print(f"  [red]FAIL: {e}[/red]")

        return True

    except Exception as e:
        console.print(f"[red]FAIL: Error: {e}[/red]")
        return False


async def main():
    """Run all tests."""
    console.print("\n[bold]QuickCall MCP Server - Authentication Flow Test[/bold]\n")

    # Get the project root
    project_root = Path(__file__).parent.parent

    console.print(f"Project: {project_root}")
    console.print(f"API URL: http://localhost:8000")
    console.print(f"Web URL: http://localhost:3000")

    # MCP server parameters
    server_params = StdioServerParameters(
        command="uv",
        args=[
            "run",
            "--directory",
            str(project_root),
            "python",
            "-m",
            "mcp_server.server",
        ],
        env={
            "QUICKCALL_API_URL": "http://localhost:8000",
            "QUICKCALL_WEB_URL": "http://localhost:3000",
        },
    )

    console.print("\nStarting MCP server...")

    results = {}

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()

            console.print("[green]MCP server started[/green]\n")

            # List available tools
            tools_result = await session.list_tools()
            console.print(f"[bold]Available tools:[/bold] {len(tools_result.tools)}")
            tool_names = [tool.name for tool in tools_result.tools]
            console.print(f"   {', '.join(tool_names)}\n")

            console.print("=" * 60)

            # Test 1: Connect to QuickCall
            results["quickcall"] = await test_connect_quickcall(session)

            if not results["quickcall"]:
                console.print(
                    "\n[red]QuickCall authentication failed. Stopping tests.[/red]"
                )
                return

            console.print("\n" + "=" * 60)

            # Test 2: Connect GitHub
            results["github"] = await test_connect_github(session)

            console.print("\n" + "=" * 60)

            # Test 3: Connect Slack
            results["slack"] = await test_connect_slack(session)

            console.print("\n" + "=" * 60)

            # Test 4: List repos (if GitHub connected)
            if results.get("github"):
                results["list_repos"] = await test_list_repos(session)

            console.print("\n" + "=" * 60)

            # Test 5: List Slack channels (if Slack connected)
            if results.get("slack"):
                results["list_slack_channels"] = await test_list_slack_channels(session)

            console.print("\n" + "=" * 60)

            # Test 6: Slack MCP Resources
            if results.get("slack"):
                results["slack_resources"] = await test_slack_resources(session)

            console.print("\n" + "=" * 60)

            # Test 7: Fuzzy channel matching
            if results.get("slack"):
                results["fuzzy_match"] = await test_fuzzy_channel_match(session)

    # Summary
    console.print("\n" + "=" * 60)
    console.print("\n[bold]Test Results Summary[/bold]\n")
    for test_name, passed in results.items():
        if passed:
            console.print(f"  [green]PASS[/green] - {test_name}")
        else:
            console.print(f"  [red]FAIL[/red] - {test_name}")

    console.print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n\n[red]Tests cancelled by user[/red]\n")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback

        traceback.print_exc()
