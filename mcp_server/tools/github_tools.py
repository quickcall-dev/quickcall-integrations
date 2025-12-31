"""
GitHub Tools - Pull requests and commits via GitHub API.

These tools require authentication via QuickCall.
Connect using connect_quickcall tool first.
"""

from typing import Optional
import logging

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from mcp_server.auth import get_credential_store, is_authenticated
from mcp_server.api_clients.github_client import GitHubClient

logger = logging.getLogger(__name__)


def _get_client() -> GitHubClient:
    """Get the GitHub client, raising error if not configured."""
    store = get_credential_store()

    if not store.is_authenticated():
        raise ToolError(
            "Not connected to QuickCall. "
            "Run connect_quickcall to authenticate and enable GitHub tools."
        )

    # Fetch fresh credentials from API
    creds = store.get_api_credentials()

    if not creds or not creds.github_connected:
        raise ToolError(
            "GitHub not connected. "
            "Connect GitHub at quickcall.dev/assistant to enable GitHub tools."
        )

    if not creds.github_token:
        raise ToolError(
            "Could not fetch GitHub token. "
            "Try reconnecting GitHub at quickcall.dev/assistant."
        )

    # Create client with fresh token and installation ID
    return GitHubClient(
        token=creds.github_token,
        default_owner=creds.github_username,
        installation_id=creds.github_installation_id,
    )


def create_github_tools(mcp: FastMCP) -> None:
    """Add GitHub tools to the MCP server."""

    @mcp.tool(tags={"github", "repos"})
    def list_repos(
        limit: int = Field(
            default=20,
            description="Maximum number of repositories to return (default: 20)",
        ),
    ) -> dict:
        """
        List GitHub repositories accessible to the authenticated user.

        Returns repositories sorted by last updated.
        Requires QuickCall authentication with GitHub connected.
        """
        try:
            client = _get_client()
            repos = client.list_repos(limit=limit)

            return {
                "count": len(repos),
                "repos": [repo.model_dump() for repo in repos],
            }
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to list repositories: {str(e)}")

    @mcp.tool(tags={"github", "prs"})
    def list_prs(
        owner: Optional[str] = Field(
            default=None,
            description="Repository owner (username or org). Uses your GitHub username if not specified.",
        ),
        repo: Optional[str] = Field(
            default=None,
            description="Repository name. Required.",
        ),
        state: str = Field(
            default="open",
            description="PR state: 'open', 'closed', or 'all' (default: 'open')",
        ),
        limit: int = Field(
            default=20,
            description="Maximum number of PRs to return (default: 20)",
        ),
    ) -> dict:
        """
        List pull requests for a GitHub repository.

        Returns PRs sorted by last updated.
        Requires QuickCall authentication with GitHub connected.
        """
        try:
            client = _get_client()
            prs = client.list_prs(owner=owner, repo=repo, state=state, limit=limit)

            return {
                "count": len(prs),
                "prs": [pr.model_dump() for pr in prs],
            }
        except ToolError:
            raise
        except ValueError as e:
            raise ToolError(
                f"Repository not specified: {str(e)}. "
                f"Please provide both owner and repo parameters."
            )
        except Exception as e:
            raise ToolError(f"Failed to list pull requests: {str(e)}")

    @mcp.tool(tags={"github", "prs"})
    def get_pr(
        pr_number: int = Field(..., description="Pull request number", gt=0),
        owner: Optional[str] = Field(
            default=None,
            description="Repository owner. Uses your GitHub username if not specified.",
        ),
        repo: Optional[str] = Field(
            default=None,
            description="Repository name. Required.",
        ),
    ) -> dict:
        """
        Get detailed information about a specific pull request.

        Includes title, description, status, files changed, and review status.
        Requires QuickCall authentication with GitHub connected.
        """
        try:
            client = _get_client()
            pr = client.get_pr(pr_number, owner=owner, repo=repo)

            if not pr:
                raise ToolError(f"Pull request #{pr_number} not found")

            return {"pr": pr.model_dump()}
        except ToolError:
            raise
        except ValueError as e:
            raise ToolError(
                f"Repository not specified: {str(e)}. "
                f"Please provide both owner and repo parameters."
            )
        except Exception as e:
            raise ToolError(f"Failed to get pull request #{pr_number}: {str(e)}")

    @mcp.tool(tags={"github", "commits"})
    def list_commits(
        owner: Optional[str] = Field(
            default=None,
            description="Repository owner. Uses your GitHub username if not specified.",
        ),
        repo: Optional[str] = Field(
            default=None,
            description="Repository name. Required.",
        ),
        branch: Optional[str] = Field(
            default=None,
            description="Branch name to list commits from. Defaults to default branch.",
        ),
        author: Optional[str] = Field(
            default=None,
            description="Filter by author username",
        ),
        since: Optional[str] = Field(
            default=None,
            description="ISO datetime - only commits after this date (e.g., '2024-01-01T00:00:00Z')",
        ),
        limit: int = Field(
            default=20,
            description="Maximum number of commits to return (default: 20)",
        ),
    ) -> dict:
        """
        List commits for a GitHub repository.

        Returns commits sorted by date (newest first).
        Requires QuickCall authentication with GitHub connected.
        """
        try:
            client = _get_client()
            commits = client.list_commits(
                owner=owner,
                repo=repo,
                sha=branch,
                author=author,
                since=since,
                limit=limit,
            )

            return {
                "count": len(commits),
                "commits": [commit.model_dump() for commit in commits],
            }
        except ToolError:
            raise
        except ValueError as e:
            raise ToolError(
                f"Repository not specified: {str(e)}. "
                f"Please provide both owner and repo parameters."
            )
        except Exception as e:
            raise ToolError(f"Failed to list commits: {str(e)}")

    @mcp.tool(tags={"github", "commits"})
    def get_commit(
        sha: str = Field(..., description="Commit SHA (full or abbreviated)"),
        owner: Optional[str] = Field(
            default=None,
            description="Repository owner. Uses your GitHub username if not specified.",
        ),
        repo: Optional[str] = Field(
            default=None,
            description="Repository name. Required.",
        ),
    ) -> dict:
        """
        Get detailed information about a specific commit.

        Includes commit message, author, stats, and file changes.
        Requires QuickCall authentication with GitHub connected.
        """
        try:
            client = _get_client()
            commit = client.get_commit(sha, owner=owner, repo=repo)

            if not commit:
                raise ToolError(f"Commit {sha} not found")

            return {"commit": commit}
        except ToolError:
            raise
        except ValueError as e:
            raise ToolError(
                f"Repository not specified: {str(e)}. "
                f"Please provide both owner and repo parameters."
            )
        except Exception as e:
            raise ToolError(f"Failed to get commit {sha}: {str(e)}")

    @mcp.tool(tags={"github", "branches"})
    def list_branches(
        owner: Optional[str] = Field(
            default=None,
            description="Repository owner. Uses your GitHub username if not specified.",
        ),
        repo: Optional[str] = Field(
            default=None,
            description="Repository name. Required.",
        ),
        limit: int = Field(
            default=30,
            description="Maximum number of branches to return (default: 30)",
        ),
    ) -> dict:
        """
        List branches for a GitHub repository.

        Returns branch names with their latest commit SHA and protection status.
        Requires QuickCall authentication with GitHub connected.
        """
        try:
            client = _get_client()
            branches = client.list_branches(owner=owner, repo=repo, limit=limit)

            return {
                "count": len(branches),
                "branches": branches,
            }
        except ToolError:
            raise
        except ValueError as e:
            raise ToolError(
                f"Repository not specified: {str(e)}. "
                f"Please provide both owner and repo parameters."
            )
        except Exception as e:
            raise ToolError(f"Failed to list branches: {str(e)}")

    @mcp.tool(tags={"github", "status"})
    def check_github_connection() -> dict:
        """
        Check if GitHub is connected and working.

        Tests the GitHub connection by fetching your account info.
        Use this to verify your GitHub integration is working.
        """
        store = get_credential_store()

        if not store.is_authenticated():
            return {
                "connected": False,
                "error": "Not connected to QuickCall. Run connect_quickcall first.",
            }

        creds = store.get_api_credentials()

        if not creds:
            return {
                "connected": False,
                "error": "Could not fetch credentials from QuickCall.",
            }

        if not creds.github_connected:
            return {
                "connected": False,
                "error": "GitHub not connected. Connect at quickcall.dev/assistant.",
            }

        try:
            client = _get_client()
            username = client.get_authenticated_user()

            return {
                "connected": True,
                "username": username,
                "installation_id": creds.github_installation_id,
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }
